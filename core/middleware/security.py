import logging
import time
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Rate limiting middleware for API endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check rate limit before processing request
        if self._is_rate_limited(request):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.'
            }, status=429)
        
        response = self.get_response(request)
        return response
    
    def _is_rate_limited(self, request):
        """Check if request should be rate limited"""
        # Skip rate limiting for admin users
        if request.user.is_authenticated and request.user.is_staff:
            return False
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Different limits for different endpoints
        if request.path.startswith('/api/v1/payments/create/'):
            return self._check_limit(client_id, 'payment_create', 10, 300)  # 10 per 5 minutes
        elif request.path.startswith('/api/v1/promo/claim/'):
            return self._check_limit(client_id, 'promo_claim', 5, 300)  # 5 per 5 minutes
        elif request.path.startswith('/api/v1/'):
            return self._check_limit(client_id, 'api_general', 100, 60)  # 100 per minute
        
        return False
    
    def _get_client_id(self, request):
        """Get client identifier for rate limiting"""
        # Try to get API key first (for providers)
        api_key = request.META.get('HTTP_X_API_KEY')
        if api_key:
            return f"api_key:{api_key}"
        
        # Fall back to IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        
        return f"ip:{ip}"
    
    def _check_limit(self, client_id, endpoint, limit, window):
        """Check if client has exceeded rate limit"""
        cache_key = f"rate_limit:{endpoint}:{client_id}"
        
        # Get current count
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit:
            return True
        
        # Increment counter
        cache.set(cache_key, current_count + 1, window)
        return False


class SecurityHeadersMiddleware:
    """Add security headers to responses"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Add HSTS header for HTTPS
        if request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response


class RequestLoggingMiddleware:
    """Log API requests for security and debugging"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Record start time
        start_time = time.time()
        
        # Get request info
        client_ip = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        api_key = request.META.get('HTTP_X_API_KEY', '')
        
        # Process request
        response = self.get_response(request)
        
        # Calculate response time
        response_time = int((time.time() - start_time) * 1000)  # milliseconds
        
        # Log API requests (but not admin or static files)
        if (request.path.startswith('/api/') and 
            not request.path.startswith('/api/admin/') and
            response.status_code != 404):
            
            log_data = {
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'response_time_ms': response_time,
                'client_ip': client_ip,
                'user_agent': user_agent[:200],  # Truncate long user agents
                'has_api_key': bool(api_key),
                'timestamp': timezone.now().isoformat()
            }
            
            if response.status_code >= 400:
                logger.warning(f"API Error: {log_data}")
            else:
                logger.info(f"API Request: {log_data}")
        
        return response
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        return ip


class APIKeyValidationMiddleware:
    """Validate API keys for provider endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check if this is a provider API endpoint
        if request.path.startswith('/api/v1/providers/api/'):
            api_key = request.META.get('HTTP_X_API_KEY')
            
            if not api_key:
                return JsonResponse({
                    'error': 'API key required',
                    'message': 'X-API-Key header is required for provider endpoints'
                }, status=401)
            
            # Validate API key format (basic check)
            if not api_key.startswith('ucpg_') or len(api_key) < 37:
                return JsonResponse({
                    'error': 'Invalid API key format',
                    'message': 'API key format is invalid'
                }, status=401)
            
            # The actual validation is done in the view
            # This middleware just does basic format checking
        
        response = self.get_response(request)
        return response


class MaintenanceModeMiddleware:
    """Handle maintenance mode"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check if maintenance mode is enabled
        maintenance_mode = cache.get('maintenance_mode', False)
        
        if maintenance_mode:
            # Allow admin users and health checks
            if (request.user.is_authenticated and request.user.is_staff) or \
               request.path in ['/health/', '/api/v1/health/']:
                pass  # Allow these requests
            else:
                return JsonResponse({
                    'error': 'Service temporarily unavailable',
                    'message': 'The service is currently under maintenance. Please try again later.',
                    'maintenance_mode': True
                }, status=503)
        
        response = self.get_response(request)
        return response
