from rest_framework import serializers
from decimal import Decimal
from .models import Currency, Transaction, PromoLink, CommissionSetting, ExchangeRate


class CurrencySerializer(serializers.ModelSerializer):
    """Serializer for Currency model"""
    
    class Meta:
        model = Currency
        fields = [
            'code', 'name', 'symbol', 'is_crypto', 
            'is_active', 'decimal_places'
        ]


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Serializer for Exchange Rate model"""
    
    from_currency = serializers.CharField(source='from_currency.code')
    to_currency = serializers.CharField(source='to_currency.code')
    
    class Meta:
        model = ExchangeRate
        fields = ['from_currency', 'to_currency', 'rate', 'timestamp', 'source']


class CreatePaymentSerializer(serializers.Serializer):
    """Serializer for creating payments"""
    
    amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    from_currency = serializers.CharField(max_length=10)
    to_currency = serializers.CharField(max_length=10)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_telegram = serializers.CharField(max_length=100, required=False, allow_blank=True)
    provider_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate_amount(self, value):
        """Validate payment amount"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        
        from django.conf import settings
        min_amount = Decimal(str(settings.UCPG_SETTINGS['MIN_TRANSACTION_AMOUNT']))
        max_amount = Decimal(str(settings.UCPG_SETTINGS['MAX_TRANSACTION_AMOUNT']))
        
        if value < min_amount:
            raise serializers.ValidationError(f"Amount must be at least {min_amount}")
        
        if value > max_amount:
            raise serializers.ValidationError(f"Amount cannot exceed {max_amount}")
        
        return value

    def validate(self, data):
        """Validate currency codes"""
        from .models import Currency
        
        # Validate currencies exist and are active
        try:
            Currency.objects.get(code=data['from_currency'].upper(), is_active=True)
        except Currency.DoesNotExist:
            raise serializers.ValidationError({
                'from_currency': f"Currency {data['from_currency']} not supported"
            })
        
        try:
            Currency.objects.get(code=data['to_currency'].upper(), is_active=True)
        except Currency.DoesNotExist:
            raise serializers.ValidationError({
                'to_currency': f"Currency {data['to_currency']} not supported"
            })
        
        # Validate provider if provided
        if data.get('provider_id'):
            from apps.providers.models import Provider
            try:
                Provider.objects.get(id=data['provider_id'], is_active=True)
            except Provider.DoesNotExist:
                raise serializers.ValidationError({
                    'provider_id': 'Invalid or inactive provider'
                })
        
        return data


class PaymentResponseSerializer(serializers.Serializer):
    """Serializer for payment creation response"""
    
    transaction_id = serializers.UUIDField()
    original_amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    original_currency = serializers.CharField()
    converted_amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    converted_currency = serializers.CharField()
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=4)
    commission_amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    net_amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    expires_at = serializers.DateTimeField()
    promo_code = serializers.CharField()
    promo_url = serializers.URLField()
    qr_code = serializers.CharField()  # Base64 encoded QR code
    status = serializers.CharField()


class TransactionStatusSerializer(serializers.ModelSerializer):
    """Serializer for transaction status"""
    
    original_currency = serializers.CharField(source='original_currency.code')
    converted_currency = serializers.CharField(source='converted_currency.code')
    is_expired = serializers.BooleanField()
    time_remaining = serializers.CharField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'status', 'original_amount', 'original_currency',
            'converted_amount', 'converted_currency', 'net_amount',
            'created_at', 'expires_at', 'completed_at', 
            'is_expired', 'time_remaining'
        ]


class ClaimPromoSerializer(serializers.Serializer):
    """Serializer for claiming promo codes"""
    
    promo_code = serializers.CharField(max_length=100)
    recipient_wallet = serializers.CharField(max_length=255, required=False, allow_blank=True)
    recipient_email = serializers.EmailField(required=False, allow_blank=True)
    recipient_telegram = serializers.CharField(max_length=100, required=False, allow_blank=True)
    payout_method = serializers.ChoiceField(
        choices=['crypto', 'email', 'telegram'],
        default='crypto'
    )

    def validate(self, data):
        """Validate that at least one recipient method is provided"""
        if not any([
            data.get('recipient_wallet'),
            data.get('recipient_email'),
            data.get('recipient_telegram')
        ]):
            raise serializers.ValidationError(
                "At least one recipient method (wallet, email, or telegram) must be provided"
            )
        return data


class PromoInfoSerializer(serializers.Serializer):
    """Serializer for promo code information"""
    
    valid = serializers.BooleanField()
    promo_code = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=8, required=False)
    currency = serializers.CharField(required=False)
    is_used = serializers.BooleanField(required=False)
    is_expired = serializers.BooleanField(required=False)
    expires_at = serializers.DateTimeField(required=False)
    time_remaining = serializers.CharField(required=False)
    message = serializers.CharField()


# Admin Serializers

class AdminTransactionSerializer(serializers.ModelSerializer):
    """Admin serializer for transactions"""
    
    original_currency = serializers.CharField(source='original_currency.code')
    converted_currency = serializers.CharField(source='converted_currency.code')
    provider_name = serializers.CharField(source='provider.name', allow_null=True)
    is_expired = serializers.BooleanField()
    time_remaining = serializers.CharField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'status', 'original_amount', 'original_currency',
            'converted_amount', 'converted_currency', 'commission_rate',
            'commission_amount', 'net_amount', 'payment_method',
            'payment_reference', 'contact_email', 'contact_telegram',
            'provider_name', 'created_at', 'updated_at', 'expires_at',
            'completed_at', 'is_expired', 'time_remaining'
        ]


class AdminPromoLinkSerializer(serializers.ModelSerializer):
    """Admin serializer for promo links"""
    
    transaction_amount = serializers.DecimalField(
        source='transaction.net_amount', 
        max_digits=20, 
        decimal_places=8
    )
    transaction_currency = serializers.CharField(source='transaction.converted_currency.code')
    is_expired = serializers.BooleanField()
    is_available = serializers.BooleanField()
    
    class Meta:
        model = PromoLink
        fields = [
            'id', 'code', 'transaction_amount', 'transaction_currency',
            'is_used', 'is_expired', 'is_available', 'created_at',
            'used_at', 'expires_at', 'recipient_wallet', 'recipient_email'
        ]


class CommissionSettingSerializer(serializers.ModelSerializer):
    """Serializer for commission settings"""
    
    currency_code = serializers.CharField(source='currency.code', allow_null=True)
    provider_name = serializers.CharField(source='provider.name', allow_null=True)
    rate_percentage = serializers.SerializerMethodField()
    setting_type = serializers.SerializerMethodField()
    
    class Meta:
        model = CommissionSetting
        fields = [
            'id', 'rate', 'rate_percentage', 'currency_code', 
            'provider_name', 'is_active', 'is_global', 'setting_type',
            'created_at', 'updated_at'
        ]
    
    def get_rate_percentage(self, obj):
        return float(obj.rate * 100)
    
    def get_setting_type(self, obj):
        if obj.is_global:
            return 'Global'
        elif obj.currency and obj.provider:
            return f'{obj.currency.code} + {obj.provider.name}'
        elif obj.currency:
            return f'{obj.currency.code} Currency'
        elif obj.provider:
            return f'{obj.provider.name} Provider'
        return 'Unknown'


class CreateCommissionSettingSerializer(serializers.Serializer):
    """Serializer for creating/updating commission settings"""
    
    rate = serializers.DecimalField(max_digits=5, decimal_places=4)
    currency_code = serializers.CharField(max_length=10, required=False, allow_blank=True)
    provider_id = serializers.UUIDField(required=False, allow_null=True)
    is_global = serializers.BooleanField(default=False)

    def validate_rate(self, value):
        """Validate commission rate"""
        from django.conf import settings
        max_rate = Decimal(str(settings.UCPG_SETTINGS['MAX_COMMISSION_RATE']))
        
        if value < 0:
            raise serializers.ValidationError("Rate cannot be negative")
        
        if value > max_rate:
            raise serializers.ValidationError(f"Rate cannot exceed {max_rate * 100}%")
        
        return value

    def validate(self, data):
        """Validate commission setting data"""
        if data.get('is_global') and (data.get('currency_code') or data.get('provider_id')):
            raise serializers.ValidationError(
                "Global commission cannot have currency or provider specified"
            )
        
        if not data.get('is_global') and not data.get('currency_code') and not data.get('provider_id'):
            raise serializers.ValidationError(
                "Non-global commission must specify currency or provider"
            )
        
        return data


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    
    today_transactions = serializers.IntegerField()
    today_volume = serializers.DecimalField(max_digits=20, decimal_places=2)
    today_commission = serializers.DecimalField(max_digits=20, decimal_places=2)
    active_promo_links = serializers.IntegerField()
    used_promo_links = serializers.IntegerField()
    expired_promo_links = serializers.IntegerField()
    total_providers = serializers.IntegerField()
    active_providers = serializers.IntegerField()
    recent_transactions = AdminTransactionSerializer(many=True)


class TestCommissionSerializer(serializers.Serializer):
    """Serializer for testing commission calculations"""
    
    amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    currency_code = serializers.CharField(max_length=10)
    provider_id = serializers.UUIDField(required=False, allow_null=True)
