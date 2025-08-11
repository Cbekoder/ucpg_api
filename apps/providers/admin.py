from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Provider, ProviderTransaction, ProviderApiLog, 
    ProviderWebhook, ProviderSettings
)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'provider_type', 'is_active', 'is_verified',
        'total_transactions', 'total_volume', 'commission_percentage',
        'created_at'
    ]
    list_filter = [
        'provider_type', 'is_active', 'is_verified', 
        'auto_approve_payments', 'created_at'
    ]
    search_fields = ['name', 'slug', 'contact_email', 'api_key']
    readonly_fields = [
        'id', 'api_key', 'total_transactions', 'total_volume',
        'total_commission_earned', 'last_activity', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name', 'slug', 'description', 'provider_type'
            )
        }),
        ('API Configuration', {
            'fields': (
                'api_key', 'api_secret', 'webhook_url', 'redirect_url'
            )
        }),
        ('Business Information', {
            'fields': (
                'contact_email', 'contact_person', 'website_url', 'logo_url'
            )
        }),
        ('Settings', {
            'fields': (
                'commission_rate', 'is_active', 'is_verified', 'auto_approve_payments'
            )
        }),
        ('Limits', {
            'fields': (
                'min_transaction_amount', 'max_transaction_amount', 'daily_transaction_limit'
            ),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': (
                'total_transactions', 'total_volume', 'total_commission_earned', 'last_activity'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    actions = ['generate_new_api_key', 'activate_providers', 'deactivate_providers']

    def generate_new_api_key(self, request, queryset):
        for provider in queryset:
            provider.generate_api_key()
            provider.save()
        self.message_user(request, f"Generated new API keys for {queryset.count()} providers.")
    generate_new_api_key.short_description = "Generate new API keys"

    def activate_providers(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} providers.")
    activate_providers.short_description = "Activate selected providers"

    def deactivate_providers(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} providers.")
    deactivate_providers.short_description = "Deactivate selected providers"

    def commission_percentage(self, obj):
        return f"{obj.commission_rate * 100:.2f}%"
    commission_percentage.short_description = 'Commission %'


@admin.register(ProviderTransaction)
class ProviderTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'transaction_id', 'webhook_sent', 'webhook_attempts',
        'redirect_completed', 'created_at'
    ]
    list_filter = [
        'provider', 'webhook_sent', 'redirect_completed', 
        'webhook_response_code', 'created_at'
    ]
    search_fields = [
        'provider__name', 'transaction__id', 'provider_transaction_id'
    ]
    readonly_fields = [
        'transaction', 'provider', 'created_at', 'updated_at',
        'last_webhook_attempt'
    ]

    def transaction_id(self, obj):
        return str(obj.transaction.id)[:8] + "..."
    transaction_id.short_description = 'Transaction'


@admin.register(ProviderApiLog)
class ProviderApiLogAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'method', 'endpoint', 'response_code',
        'response_time_ms', 'timestamp'
    ]
    list_filter = [
        'provider', 'method', 'response_code', 'timestamp'
    ]
    search_fields = ['provider__name', 'endpoint', 'ip_address']
    readonly_fields = [
        'provider', 'endpoint', 'method', 'request_data',
        'response_code', 'response_data', 'response_time_ms',
        'ip_address', 'user_agent', 'timestamp'
    ]
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProviderWebhook)
class ProviderWebhookAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'event', 'transaction_short', 'delivered',
        'delivery_attempts', 'last_attempt', 'next_retry'
    ]
    list_filter = [
        'provider', 'event', 'delivered', 'delivery_attempts',
        'response_code', 'created_at'
    ]
    search_fields = ['provider__name', 'transaction__id']
    readonly_fields = [
        'provider', 'transaction', 'event', 'payload',
        'created_at', 'delivered_at'
    ]

    def transaction_short(self, obj):
        return str(obj.transaction.id)[:8] + "..."
    transaction_short.short_description = 'Transaction'

    def has_add_permission(self, request):
        return False


class ProviderSettingsInline(admin.StackedInline):
    model = ProviderSettings
    extra = 0


@admin.register(ProviderSettings)
class ProviderSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'email_notifications', 'webhook_retries',
        'require_email', 'test_mode'
    ]
    list_filter = [
        'email_notifications', 'require_email', 'require_telegram',
        'test_mode'
    ]
    search_fields = ['provider__name']
