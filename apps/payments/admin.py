from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Currency, ExchangeRate, Transaction, PromoLink, CommissionSetting, 
    TransactionLog, EscrowAccount, PayoutRequest
)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'is_crypto', 'is_active', 'decimal_places']
    list_filter = ['is_crypto', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['from_currency', 'to_currency', 'rate', 'source', 'timestamp']
    list_filter = ['source', 'from_currency', 'to_currency', 'timestamp']
    search_fields = ['from_currency__code', 'to_currency__code']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'original_amount', 'original_currency', 
        'net_amount', 'converted_currency', 'status', 
        'created_at', 'expires_at'
    ]
    list_filter = ['status', 'original_currency', 'converted_currency', 'created_at']
    search_fields = ['id', 'contact_email', 'payment_reference']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'commission_amount', 
        'net_amount', 'time_remaining_display'
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        ('Transaction Details', {
            'fields': (
                'id', 'status', 'payment_method', 'payment_reference'
            )
        }),
        ('Payment Amounts', {
            'fields': (
                ('original_amount', 'original_currency'),
                ('converted_amount', 'converted_currency'),
                ('commission_rate', 'commission_amount'),
                'net_amount'
            )
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_telegram'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at', 'updated_at', 'expires_at', 
                'completed_at', 'time_remaining_display'
            )
        })
    )

    def time_remaining_display(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">Expired</span>')
        remaining = obj.time_remaining
        return f"{remaining.days}d {remaining.seconds//3600}h {(remaining.seconds//60)%60}m"
    time_remaining_display.short_description = 'Time Remaining'


@admin.register(PromoLink)
class PromoLinkAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'transaction_amount', 'is_used', 'is_expired', 
        'created_at', 'used_at'
    ]
    list_filter = ['is_used', 'created_at']
    search_fields = ['code', 'transaction__id']
    readonly_fields = [
        'id', 'qr_code_data', 'created_at', 'used_at', 
        'transaction_amount', 'is_expired'
    ]
    ordering = ['-created_at']

    def transaction_amount(self, obj):
        return f"{obj.transaction.net_amount} {obj.transaction.converted_currency.code}"
    transaction_amount.short_description = 'Amount'

    def is_expired(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    is_expired.boolean = True


@admin.register(CommissionSetting)
class CommissionSettingAdmin(admin.ModelAdmin):
    list_display = [
        'commission_type', 'rate_percentage', 'is_active', 
        'created_at', 'updated_at'
    ]
    list_filter = ['is_global', 'is_active', 'currency', 'provider']
    search_fields = ['currency__code', 'provider__name']
    ordering = ['-is_global', 'currency__code']

    def commission_type(self, obj):
        if obj.is_global:
            return "Global"
        elif obj.currency and obj.provider:
            return f"{obj.currency.code} + {obj.provider.name}"
        elif obj.currency:
            return obj.currency.code
        elif obj.provider:
            return obj.provider.name
        return "Unknown"
    commission_type.short_description = 'Type'

    def rate_percentage(self, obj):
        return f"{obj.rate * 100:.2f}%"
    rate_percentage.short_description = 'Rate'


@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'action', 'old_status', 'new_status', 'timestamp']
    list_filter = ['action', 'old_status', 'new_status', 'timestamp']
    search_fields = ['transaction__id', 'action']
    readonly_fields = ['transaction', 'action', 'old_status', 'new_status', 'details', 'timestamp']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False  # Logs should only be created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Logs should be read-only


@admin.register(EscrowAccount)
class EscrowAccountAdmin(admin.ModelAdmin):
    list_display = [
        'account_type', 'currency', 'total_balance', 'available_balance', 
        'reserved_balance', 'status', 'created_at'
    ]
    list_filter = ['account_type', 'currency', 'status']
    readonly_fields = ['id', 'created_at', 'updated_at']
    search_fields = ['account_reference']
    
    fieldsets = (
        ('Account Details', {
            'fields': ('id', 'account_type', 'account_reference', 'currency', 'status')
        }),
        ('Balance Information', {
            'fields': ('total_balance', 'available_balance', 'reserved_balance')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'payout_method', 'payout_amount', 'payout_currency', 
        'status', 'created_at', 'completed_at'
    ]
    list_filter = ['payout_method', 'status', 'payout_currency', 'created_at']
    readonly_fields = [
        'id', 'promo_link', 'external_payout_id', 'created_at', 
        'processed_at', 'completed_at'
    ]
    search_fields = ['id', 'external_payout_id', 'recipient_email']
    
    fieldsets = (
        ('Payout Details', {
            'fields': (
                'id', 'promo_link', 'payout_method', 'payout_amount', 
                'payout_currency', 'status'
            )
        }),
        ('Recipient Information', {
            'fields': (
                'recipient_crypto_address', 'recipient_email', 'recipient_bank_details'
            ),
            'classes': ('collapse',)
        }),
        ('Processing Details', {
            'fields': (
                'external_payout_id', 'failure_reason', 'processing_fee'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at', 'completed_at'),
            'classes': ('collapse',)
        })
    )
    
    def has_add_permission(self, request):
        return False  # Payouts should only be created through the system
