from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for viewsets
router = DefaultRouter()
router.register(r'admin/providers', views.AdminProviderViewSet, basename='admin-providers')
router.register(r'admin/provider-transactions', views.AdminProviderTransactionViewSet, basename='admin-provider-transactions')

app_name = 'providers'

urlpatterns = [
    # Provider API endpoints (for external providers)
    path('api/payment/', views.ProviderPaymentView.as_view(), name='provider-payment'),
    path('api/transaction/<uuid:transaction_id>/status/', views.ProviderTransactionStatusView.as_view(), name='provider-transaction-status'),
    path('api/webhook/test/', views.ProviderWebhookTestView.as_view(), name='provider-webhook-test'),
    
    # Admin provider management
    path('admin/providers/<uuid:provider_id>/settings/', views.ProviderSettingsView.as_view(), name='provider-settings'),
    
    # Include router URLs
    path('', include(router.urls)),
    
    # Utility endpoints
    path('health/', views.provider_health_check, name='provider-health-check'),
]
