import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


class Currency(models.Model):
    """Model for supported currencies (both fiat and crypto)"""
    
    code = models.CharField(max_length=10, unique=True)  # USD, EUR, BTC, USDT
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10, blank=True)  # $, €, ₿
    is_crypto = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    decimal_places = models.IntegerField(default=2)  # Number of decimal places
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class ExchangeRate(models.Model):
    """Model for storing exchange rates between currencies"""
    
    from_currency = models.ForeignKey(
        Currency, 
        on_delete=models.CASCADE, 
        related_name='rates_from'
    )
    to_currency = models.ForeignKey(
        Currency, 
        on_delete=models.CASCADE, 
        related_name='rates_to'
    )
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, default='binance')  # binance, coingecko

    class Meta:
        unique_together = ['from_currency', 'to_currency', 'timestamp']
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.from_currency.code} -> {self.to_currency.code}: {self.rate}"


class Transaction(models.Model):
    """Model for payment transactions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('payment_processing', 'Processing Payment'),
        ('payment_confirmed', 'Payment Confirmed'),
        ('escrowed', 'Funds Escrowed'),
        ('ready_for_claim', 'Ready for Claim'),
        ('claim_processing', 'Processing Claim'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe_card', 'Credit/Debit Card (Stripe)'),
        ('crypto_deposit', 'Cryptocurrency Deposit'),
        ('bank_transfer', 'Bank Transfer'),
        ('paypal', 'PayPal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Original payment details
    original_amount = models.DecimalField(max_digits=20, decimal_places=8)
    original_currency = models.ForeignKey(
        Currency, 
        on_delete=models.PROTECT, 
        related_name='transactions_original'
    )
    
    # Converted payment details
    converted_amount = models.DecimalField(max_digits=20, decimal_places=8)
    converted_currency = models.ForeignKey(
        Currency, 
        on_delete=models.PROTECT, 
        related_name='transactions_converted'
    )
    
    # Commission details
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4)  # 0.0500 = 5%
    commission_amount = models.DecimalField(max_digits=20, decimal_places=8)
    net_amount = models.DecimalField(max_digits=20, decimal_places=8)
    
    # Transaction status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True)
    payment_reference = models.CharField(max_length=255, blank=True)  # External payment ID
    
    # Payment processing details
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    crypto_deposit_address = models.CharField(max_length=255, blank=True)
    crypto_tx_hash = models.CharField(max_length=255, blank=True)
    
    # Escrow details
    escrow_account_id = models.CharField(max_length=255, blank=True)  # Internal escrow reference
    escrow_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    escrow_currency = models.CharField(max_length=10, blank=True)
    
    # Payout details
    payout_method = models.CharField(max_length=50, blank=True)  # card, crypto, bank
    payout_reference = models.CharField(max_length=255, blank=True)  # Payout transaction ID
    payout_completed_at = models.DateTimeField(null=True, blank=True)
    
    # Contact info (optional for anonymity)
    contact_email = models.EmailField(blank=True)
    contact_telegram = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    # Provider reference (if used through a service provider)
    provider = models.ForeignKey(
        'providers.Provider', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                hours=settings.UCPG_SETTINGS['PROMO_LINK_EXPIRY_HOURS']
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transaction {self.id} - {self.original_amount} {self.original_currency.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def time_remaining(self):
        if self.is_expired:
            return timedelta(0)
        return self.expires_at - timezone.now()


class PromoLink(models.Model):
    """Model for one-time use promo links and QR codes"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.OneToOneField(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name='promo_link'
    )
    
    # Promo code and QR data
    code = models.CharField(max_length=100, unique=True, db_index=True)
    qr_code_data = models.TextField()  # Base64 encoded QR code image
    link_url = models.URLField(max_length=500)  # Full URL to claim the link
    
    # Usage tracking
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    used_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Recipient details (filled when claimed)
    recipient_wallet = models.CharField(max_length=255, blank=True)
    recipient_email = models.EmailField(blank=True)
    recipient_telegram = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.transaction.expires_at
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PromoLink {self.code} - {self.transaction.net_amount} {self.transaction.converted_currency.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_available(self):
        return not self.is_used and not self.is_expired

    def mark_as_used(self, ip_address=None, recipient_data=None):
        """Mark the promo link as used"""
        self.is_used = True
        self.used_at = timezone.now()
        self.used_ip = ip_address
        
        if recipient_data:
            self.recipient_wallet = recipient_data.get('wallet', '')
            self.recipient_email = recipient_data.get('email', '')
            self.recipient_telegram = recipient_data.get('telegram', '')
        
        self.save()


class CommissionSetting(models.Model):
    """Model for configurable commission rates"""
    
    # Commission can be global, per currency, or per provider
    currency = models.ForeignKey(
        Currency, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Leave blank for global rate"
    )
    provider = models.ForeignKey(
        'providers.Provider', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Leave blank for global rate"
    )
    
    rate = models.DecimalField(
        max_digits=5, 
        decimal_places=4,
        help_text="Commission rate as decimal (0.0500 = 5%)"
    )
    is_active = models.BooleanField(default=True)
    is_global = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ['currency', 'provider'],
        ]
        ordering = ['-is_global', 'currency__code', 'provider__name']

    def __str__(self):
        if self.is_global:
            return f"Global Commission: {self.rate * 100}%"
        elif self.currency and self.provider:
            return f"{self.currency.code} + {self.provider.name}: {self.rate * 100}%"
        elif self.currency:
            return f"{self.currency.code}: {self.rate * 100}%"
        elif self.provider:
            return f"{self.provider.name}: {self.rate * 100}%"
        return f"Commission: {self.rate * 100}%"

    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Ensure at least one of global, currency, or provider is set
        if not self.is_global and not self.currency and not self.provider:
            raise ValidationError("Commission must be global, currency-specific, or provider-specific")
        
        # Ensure global commission doesn't have currency or provider
        if self.is_global and (self.currency or self.provider):
            raise ValidationError("Global commission cannot have currency or provider specified")


class EscrowAccount(models.Model):
    """Model for escrow accounts that hold funds temporarily"""
    
    ACCOUNT_TYPES = [
        ('stripe', 'Stripe Connect Account'),
        ('crypto', 'Crypto Wallet'),
        ('bank', 'Bank Account'),
    ]
    
    ACCOUNT_STATUS = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    account_reference = models.CharField(max_length=255, unique=True)  # External account ID
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    
    # Balance tracking
    total_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    available_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    reserved_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    # Account details
    status = models.CharField(max_length=20, choices=ACCOUNT_STATUS, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.account_type} - {self.currency.code} - {self.total_balance}"
    
    def reserve_funds(self, amount):
        """Reserve funds for a transaction"""
        if self.available_balance >= amount:
            self.available_balance -= amount
            self.reserved_balance += amount
            self.save()
            return True
        return False
    
    def release_funds(self, amount):
        """Release reserved funds (complete transaction)"""
        if self.reserved_balance >= amount:
            self.reserved_balance -= amount
            self.total_balance -= amount
            self.save()
            return True
        return False
    
    def return_funds(self, amount):
        """Return reserved funds to available (cancel transaction)"""
        if self.reserved_balance >= amount:
            self.reserved_balance -= amount
            self.available_balance += amount
            self.save()
            return True
        return False


class PayoutRequest(models.Model):
    """Model for payout requests when promo links are claimed"""
    
    PAYOUT_METHODS = [
        ('stripe_card', 'Credit/Debit Card'),
        ('crypto_wallet', 'Crypto Wallet'),
        ('bank_transfer', 'Bank Transfer'),
        ('paypal', 'PayPal'),
    ]
    
    PAYOUT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    promo_link = models.OneToOneField(PromoLink, on_delete=models.CASCADE, related_name='payout_request')
    
    # Payout details
    payout_method = models.CharField(max_length=20, choices=PAYOUT_METHODS)
    payout_amount = models.DecimalField(max_digits=20, decimal_places=8)
    payout_currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    
    # Recipient details (encrypted)
    recipient_card_token = models.CharField(max_length=255, blank=True)  # Tokenized card data
    recipient_crypto_address = models.CharField(max_length=255, blank=True)
    recipient_bank_details = models.JSONField(default=dict, blank=True)  # Encrypted bank details
    recipient_email = models.EmailField(blank=True)
    
    # Processing details
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS, default='pending')
    external_payout_id = models.CharField(max_length=255, blank=True)  # Stripe transfer ID, etc.
    failure_reason = models.TextField(blank=True)
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payout {self.id} - {self.payout_amount} {self.payout_currency.code}"


class TransactionLog(models.Model):
    """Model for audit trail of transaction changes"""
    
    transaction = models.ForeignKey(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name='logs'
    )
    action = models.CharField(max_length=50)  # created, status_changed, expired, etc
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.transaction.id} - {self.action} at {self.timestamp}"
