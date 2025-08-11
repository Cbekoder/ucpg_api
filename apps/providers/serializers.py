from rest_framework import serializers
from .models import Provider, ProviderTransaction, ProviderSettings


class ProviderSerializer(serializers.ModelSerializer):
    """Serializer for Provider model"""
    
    commission_percentage = serializers.SerializerMethodField()
    is_healthy = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Provider
        fields = [
            'id', 'name', 'slug', 'description', 'provider_type',
            'commission_rate', 'commission_percentage', 'contact_email',
            'website_url', 'logo_url', 'is_active', 'is_verified',
            'min_transaction_amount', 'max_transaction_amount',
            'total_transactions', 'total_volume', 'is_healthy',
            'created_at', 'last_activity'
        ]
        read_only_fields = [
            'id', 'slug', 'total_transactions', 'total_volume',
            'total_commission_earned', 'created_at', 'last_activity'
        ]
    
    def get_commission_percentage(self, obj):
        return float(obj.commission_rate * 100)


class CreateProviderSerializer(serializers.ModelSerializer):
    """Serializer for creating providers"""
    
    class Meta:
        model = Provider
        fields = [
            'name', 'description', 'provider_type', 'webhook_url',
            'redirect_url', 'commission_rate', 'contact_email',
            'contact_person', 'website_url', 'logo_url',
            'min_transaction_amount', 'max_transaction_amount',
            'daily_transaction_limit'
        ]
    
    def validate_name(self, value):
        """Validate provider name is unique"""
        if Provider.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Provider with this name already exists")
        return value
    
    def validate_commission_rate(self, value):
        """Validate commission rate"""
        if value < 0 or value > 0.5:  # Max 50%
            raise serializers.ValidationError("Commission rate must be between 0% and 50%")
        return value


class ProviderTransactionSerializer(serializers.ModelSerializer):
    """Serializer for provider transactions"""
    
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    transaction_amount = serializers.DecimalField(
        source='transaction.original_amount',
        max_digits=20,
        decimal_places=8,
        read_only=True
    )
    transaction_status = serializers.CharField(source='transaction.status', read_only=True)
    
    class Meta:
        model = ProviderTransaction
        fields = [
            'id', 'provider_name', 'transaction_amount', 'transaction_status',
            'provider_transaction_id', 'webhook_sent', 'webhook_response_code',
            'webhook_attempts', 'redirect_completed', 'created_at'
        ]


class ProviderSettingsSerializer(serializers.ModelSerializer):
    """Serializer for provider settings"""
    
    class Meta:
        model = ProviderSettings
        fields = [
            'email_notifications', 'webhook_retries', 'webhook_timeout',
            'require_email', 'require_telegram', 'auto_expire_hours',
            'custom_fields', 'test_mode', 'sandbox_webhook_url'
        ]


class ProviderStatsSerializer(serializers.Serializer):
    """Serializer for provider statistics"""
    
    total_transactions = serializers.IntegerField()
    total_volume = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_commission = serializers.DecimalField(max_digits=20, decimal_places=2)
    success_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_transaction = serializers.DecimalField(max_digits=20, decimal_places=2)
    last_30_days_transactions = serializers.IntegerField()
    last_30_days_volume = serializers.DecimalField(max_digits=20, decimal_places=2)
    webhook_success_rate = serializers.DecimalField(max_digits=5, decimal_places=2)


class ProviderPaymentRequestSerializer(serializers.Serializer):
    """Serializer for provider payment requests"""
    
    amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    currency = serializers.CharField(max_length=10)
    service_data = serializers.JSONField(default=dict)
    customer_email = serializers.EmailField(required=False)
    customer_telegram = serializers.CharField(max_length=100, required=False)
    provider_transaction_id = serializers.CharField(max_length=255, required=False)
    redirect_url = serializers.URLField(required=False)
    
    def validate_amount(self, value):
        """Validate payment amount"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
