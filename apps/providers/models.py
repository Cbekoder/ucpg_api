import uuid
from django.db import models
from django.core.validators import URLValidator
from django.utils import timezone


class Provider(models.Model):
    """Model for service providers that integrate with UCPG"""
    
    PROVIDER_TYPES = [
        ('vpn', 'VPN Service'),
        ('game', 'Gaming Service'),
        ('software', 'Software/SaaS'),
        ('digital_goods', 'Digital Goods'),
        ('sms', 'SMS Gateway'),
        ('hosting', 'Web Hosting'),
        ('other', 'Other Service'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_TYPES, default='other')
    
    # API Configuration
    api_key = models.CharField(max_length=255, unique=True)
    api_secret = models.CharField(max_length=255, blank=True)  # For webhook verification
    webhook_url = models.URLField(
        max_length=500,
        validators=[URLValidator()],
        help_text="URL to receive payment notifications"
    )
    redirect_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to redirect users after payment"
    )
    
    # Commission Configuration
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=4,
        default=0.0500,
        help_text="Default commission rate for this provider (0.0500 = 5%)"
    )
    
    # Contact and Business Info
    contact_email = models.EmailField()
    contact_person = models.CharField(max_length=100, blank=True)
    website_url = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    
    # Status and Settings
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    auto_approve_payments = models.BooleanField(default=False)
    
    # Limits and Restrictions
    min_transaction_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=1.00,
        help_text="Minimum transaction amount for this provider"
    )
    max_transaction_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=10000.00,
        help_text="Maximum transaction amount for this provider"
    )
    daily_transaction_limit = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=50000.00,
        help_text="Maximum daily transaction volume"
    )
    
    # Statistics
    total_transactions = models.IntegerField(default=0)
    total_volume = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_commission_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.provider_type})"

    def generate_api_key(self):
        """Generate a new API key for the provider"""
        import secrets
        self.api_key = f"ucpg_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(32))}"
        return self.api_key

    def update_statistics(self, transaction_amount, commission_amount):
        """Update provider statistics after a successful transaction"""
        self.total_transactions += 1
        self.total_volume += transaction_amount
        self.total_commission_earned += commission_amount
        self.last_activity = timezone.now()
        self.save()

    @property
    def is_healthy(self):
        """Check if provider is in good standing"""
        return self.is_active and self.is_verified

    @property
    def commission_percentage(self):
        """Get commission rate as percentage"""
        return self.commission_rate * 100


class ProviderTransaction(models.Model):
    """Model for tracking provider-specific transaction data"""
    
    provider = models.ForeignKey(
        Provider, 
        on_delete=models.CASCADE, 
        related_name='provider_transactions'
    )
    transaction = models.ForeignKey(
        'payments.Transaction', 
        on_delete=models.CASCADE, 
        related_name='provider_data'
    )
    
    # Provider-specific data
    provider_transaction_id = models.CharField(max_length=255, blank=True)
    service_data = models.JSONField(
        default=dict,
        help_text="Additional service-specific data"
    )
    
    # Webhook and notification status
    webhook_sent = models.BooleanField(default=False)
    webhook_response_code = models.IntegerField(null=True, blank=True)
    webhook_response = models.TextField(blank=True)
    webhook_attempts = models.IntegerField(default=0)
    last_webhook_attempt = models.DateTimeField(null=True, blank=True)
    
    # User redirection
    redirect_completed = models.BooleanField(default=False)
    redirect_timestamp = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['provider', 'transaction']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider.name} - {self.transaction.id}"

    def mark_webhook_sent(self, response_code, response_data=""):
        """Mark webhook as sent with response details"""
        self.webhook_sent = True
        self.webhook_response_code = response_code
        self.webhook_response = response_data
        self.webhook_attempts += 1
        self.last_webhook_attempt = timezone.now()
        self.save()

    def increment_webhook_attempts(self):
        """Increment webhook attempt counter"""
        self.webhook_attempts += 1
        self.last_webhook_attempt = timezone.now()
        self.save()


class ProviderApiLog(models.Model):
    """Model for logging API requests from providers"""
    
    provider = models.ForeignKey(
        Provider, 
        on_delete=models.CASCADE, 
        related_name='api_logs'
    )
    
    # Request details
    endpoint = models.CharField(max_length=200)
    method = models.CharField(max_length=10)  # GET, POST, etc
    request_data = models.JSONField(default=dict, blank=True)
    
    # Response details
    response_code = models.IntegerField()
    response_data = models.JSONField(default=dict, blank=True)
    response_time_ms = models.IntegerField(help_text="Response time in milliseconds")
    
    # Metadata
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.provider.name} - {self.method} {self.endpoint} - {self.response_code}"


class ProviderWebhook(models.Model):
    """Model for tracking webhook deliveries to providers"""
    
    WEBHOOK_EVENTS = [
        ('payment_created', 'Payment Created'),
        ('payment_completed', 'Payment Completed'),
        ('payment_failed', 'Payment Failed'),
        ('payment_expired', 'Payment Expired'),
    ]

    provider = models.ForeignKey(
        Provider, 
        on_delete=models.CASCADE, 
        related_name='webhooks'
    )
    transaction = models.ForeignKey(
        'payments.Transaction', 
        on_delete=models.CASCADE, 
        related_name='webhooks'
    )
    
    event = models.CharField(max_length=20, choices=WEBHOOK_EVENTS)
    payload = models.JSONField(default=dict)
    
    # Delivery tracking
    delivered = models.BooleanField(default=False)
    delivery_attempts = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(null=True, blank=True)
    next_retry = models.DateTimeField(null=True, blank=True)
    
    # Response tracking
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider.name} - {self.event} - {self.transaction.id}"

    def mark_delivered(self, response_code, response_body=""):
        """Mark webhook as successfully delivered"""
        self.delivered = True
        self.delivered_at = timezone.now()
        self.response_code = response_code
        self.response_body = response_body
        self.save()

    def mark_failed(self, error_message, response_code=None):
        """Mark webhook delivery as failed"""
        self.error_message = error_message
        self.response_code = response_code
        self.delivery_attempts += 1
        self.last_attempt = timezone.now()
        
        # Schedule next retry (exponential backoff)
        retry_delays = [300, 900, 1800, 3600, 7200]  # 5min, 15min, 30min, 1hr, 2hr
        if self.delivery_attempts <= len(retry_delays):
            delay = retry_delays[self.delivery_attempts - 1]
            self.next_retry = timezone.now() + timezone.timedelta(seconds=delay)
        
        self.save()


class ProviderSettings(models.Model):
    """Model for provider-specific configuration settings"""
    
    provider = models.OneToOneField(
        Provider, 
        on_delete=models.CASCADE, 
        related_name='settings'
    )
    
    # Notification settings
    email_notifications = models.BooleanField(default=True)
    webhook_retries = models.IntegerField(default=5)
    webhook_timeout = models.IntegerField(default=30, help_text="Webhook timeout in seconds")
    
    # Payment settings
    require_email = models.BooleanField(default=False)
    require_telegram = models.BooleanField(default=False)
    auto_expire_hours = models.IntegerField(
        default=24,
        help_text="Hours before payment expires (overrides global setting)"
    )
    
    # Custom fields
    custom_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom fields required by this provider"
    )
    
    # Integration settings
    test_mode = models.BooleanField(default=False)
    sandbox_webhook_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.provider.name}"
