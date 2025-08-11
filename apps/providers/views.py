import logging
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Count, Sum, Avg
from datetime import timedelta

from .models import Provider, ProviderTransaction, ProviderSettings
from .serializers import (
    ProviderSerializer, CreateProviderSerializer, ProviderTransactionSerializer,
    ProviderSettingsSerializer, ProviderStatsSerializer, ProviderPaymentRequestSerializer
)
from apps.payments.services import PaymentService

logger = logging.getLogger(__name__)


class ProviderAuthentication:
    """Custom authentication for provider API requests"""
    
    @staticmethod
    def authenticate_provider(request):
        """Authenticate provider using API key"""
        api_key = request.META.get('HTTP_X_API_KEY')
        if not api_key:
            return None, "API key required"
        
        try:
            provider = Provider.objects.get(api_key=api_key, is_active=True)
            return provider, None
        except Provider.DoesNotExist:
            return None, "Invalid API key"


# Admin Provider Management Views

class AdminProviderViewSet(viewsets.ModelViewSet):
    """Admin provider management"""
    
    queryset = Provider.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['provider_type', 'is_active', 'is_verified']
    search_fields = ['name', 'contact_email', 'website_url']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateProviderSerializer
        return ProviderSerializer
    
    def create(self, request):
        """Create new provider"""
        try:
            serializer = CreateProviderSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid provider data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create provider
            provider = serializer.save()
            
            # Generate API key
            provider.generate_api_key()
            provider.save()
            
            # Create default settings
            ProviderSettings.objects.create(provider=provider)
            
            return Response({
                'success': True,
                'message': 'Provider created successfully',
                'data': ProviderSerializer(provider).data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating provider: {str(e)}")
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def regenerate_api_key(self, request, pk=None):
        """Regenerate API key for provider"""
        try:
            provider = self.get_object()
            old_key = provider.api_key
            new_key = provider.generate_api_key()
            provider.save()
            
            logger.info(f"API key regenerated for provider {provider.name}")
            
            return Response({
                'success': True,
                'message': 'API key regenerated successfully',
                'new_api_key': new_key
            })
            
        except Exception as e:
            logger.error(f"Error regenerating API key: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error regenerating API key'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get provider statistics"""
        try:
            provider = self.get_object()
            
            # Calculate statistics
            transactions = ProviderTransaction.objects.filter(provider=provider)
            
            total_transactions = transactions.count()
            successful_transactions = transactions.filter(
                transaction__status='completed'
            ).count()
            
            total_volume = sum(
                pt.transaction.original_amount 
                for pt in transactions.select_related('transaction')
            )
            
            total_commission = sum(
                pt.transaction.commission_amount 
                for pt in transactions.select_related('transaction')
            )
            
            # Last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_transactions = transactions.filter(created_at__gte=thirty_days_ago)
            
            recent_count = recent_transactions.count()
            recent_volume = sum(
                pt.transaction.original_amount 
                for pt in recent_transactions.select_related('transaction')
            )
            
            # Webhook success rate
            webhook_sent = transactions.filter(webhook_sent=True).count()
            webhook_success = transactions.filter(
                webhook_sent=True,
                webhook_response_code__range=(200, 299)
            ).count()
            
            stats = {
                'total_transactions': total_transactions,
                'total_volume': total_volume,
                'total_commission': total_commission,
                'success_rate': (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0,
                'average_transaction': total_volume / total_transactions if total_transactions > 0 else 0,
                'last_30_days_transactions': recent_count,
                'last_30_days_volume': recent_volume,
                'webhook_success_rate': (webhook_success / webhook_sent * 100) if webhook_sent > 0 else 0
            }
            
            return Response({
                'success': True,
                'data': stats
            })
            
        except Exception as e:
            logger.error(f"Error getting provider statistics: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error retrieving statistics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminProviderTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin provider transaction management"""
    
    queryset = ProviderTransaction.objects.select_related(
        'provider', 'transaction'
    ).order_by('-created_at')
    serializer_class = ProviderTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['provider', 'webhook_sent', 'redirect_completed']
    search_fields = ['provider__name', 'transaction__id', 'provider_transaction_id']


# Provider API Views (for external providers)

class ProviderPaymentView(APIView):
    """Create payment through provider"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Create payment via provider API"""
        try:
            # Authenticate provider
            provider, error = ProviderAuthentication.authenticate_provider(request)
            if not provider:
                return Response({
                    'success': False,
                    'message': error
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Validate request data
            serializer = ProviderPaymentRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid payment data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check provider limits
            amount = serializer.validated_data['amount']
            if amount < provider.min_transaction_amount or amount > provider.max_transaction_amount:
                return Response({
                    'success': False,
                    'message': f'Amount must be between {provider.min_transaction_amount} and {provider.max_transaction_amount}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create payment
            payment_service = PaymentService()
            payment_data = {
                'amount': amount,
                'from_currency': serializer.validated_data['currency'],
                'to_currency': 'USDT',  # Default to USDT for providers
                'provider_id': str(provider.id),
                'contact_email': serializer.validated_data.get('customer_email', ''),
                'contact_telegram': serializer.validated_data.get('customer_telegram', ''),
                'payment_method': 'provider_api'
            }
            
            result = payment_service.create_payment(payment_data)
            
            # Create provider transaction record
            provider_transaction = ProviderTransaction.objects.create(
                provider=provider,
                transaction_id=result['transaction_id'],
                provider_transaction_id=serializer.validated_data.get('provider_transaction_id', ''),
                service_data=serializer.validated_data.get('service_data', {})
            )
            
            # Return provider-specific response
            response_data = {
                'transaction_id': result['transaction_id'],
                'provider_transaction_id': provider_transaction.id,
                'amount': result['original_amount'],
                'currency': result['original_currency'],
                'net_amount': result['net_amount'],
                'converted_currency': result['converted_currency'],
                'commission_amount': result['commission_amount'],
                'promo_code': result['promo_code'],
                'promo_url': result['promo_url'],
                'qr_code': result['qr_code'],
                'expires_at': result['expires_at'],
                'status': result['status']
            }
            
            return Response({
                'success': True,
                'message': 'Payment created successfully',
                'data': response_data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating provider payment: {str(e)}")
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProviderTransactionStatusView(APIView):
    """Get transaction status via provider API"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, transaction_id):
        """Get transaction status"""
        try:
            # Authenticate provider
            provider, error = ProviderAuthentication.authenticate_provider(request)
            if not provider:
                return Response({
                    'success': False,
                    'message': error
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Get provider transaction
            try:
                provider_transaction = ProviderTransaction.objects.select_related(
                    'transaction'
                ).get(
                    provider=provider,
                    transaction__id=transaction_id
                )
            except ProviderTransaction.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Transaction not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            transaction = provider_transaction.transaction
            
            return Response({
                'success': True,
                'data': {
                    'transaction_id': str(transaction.id),
                    'provider_transaction_id': provider_transaction.provider_transaction_id,
                    'status': transaction.status,
                    'amount': transaction.original_amount,
                    'currency': transaction.original_currency.code,
                    'net_amount': transaction.net_amount,
                    'converted_currency': transaction.converted_currency.code,
                    'created_at': transaction.created_at.isoformat(),
                    'expires_at': transaction.expires_at.isoformat(),
                    'completed_at': transaction.completed_at.isoformat() if transaction.completed_at else None,
                    'is_expired': transaction.is_expired,
                    'webhook_sent': provider_transaction.webhook_sent,
                    'redirect_completed': provider_transaction.redirect_completed
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting provider transaction status: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error retrieving transaction status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProviderWebhookTestView(APIView):
    """Test webhook delivery"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Test webhook endpoint"""
        try:
            # Authenticate provider
            provider, error = ProviderAuthentication.authenticate_provider(request)
            if not provider:
                return Response({
                    'success': False,
                    'message': error
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # This would send a test webhook to the provider's webhook URL
            # For now, we'll just return success
            
            return Response({
                'success': True,
                'message': 'Webhook test completed',
                'webhook_url': provider.webhook_url,
                'test_timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error testing webhook: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error testing webhook'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Provider Settings Management

class ProviderSettingsView(APIView):
    """Provider settings management"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request, provider_id):
        """Get provider settings"""
        try:
            provider = Provider.objects.get(id=provider_id)
            settings_obj, created = ProviderSettings.objects.get_or_create(provider=provider)
            
            serializer = ProviderSettingsSerializer(settings_obj)
            return Response({
                'success': True,
                'data': serializer.data
            })
            
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Provider not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request, provider_id):
        """Update provider settings"""
        try:
            provider = Provider.objects.get(id=provider_id)
            settings_obj, created = ProviderSettings.objects.get_or_create(provider=provider)
            
            serializer = ProviderSettingsSerializer(settings_obj, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Settings updated successfully',
                'data': serializer.data
            })
            
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Provider not found'
            }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def provider_health_check(request):
    """Provider API health check"""
    return Response({
        'status': 'healthy',
        'service': 'provider_api',
        'timestamp': timezone.now().isoformat(),
        'version': '1.0.0'
    })
