from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for viewsets
router = DefaultRouter()
router.register(r'admin/transactions', views.AdminTransactionViewSet, basename='admin-transactions')
router.register(r'admin/promo-links', views.AdminPromoLinkViewSet, basename='admin-promo-links')
router.register(r'admin/commission', views.CommissionSettingViewSet, basename='admin-commission')

app_name = 'payments'

urlpatterns = [
    # Public API endpoints
    path('currencies/', views.CurrencyListView.as_view(), name='currencies'),
    path('exchange-rates/', views.ExchangeRateView.as_view(), name='exchange-rates'),
    path('payments/create/', views.CreatePaymentView.as_view(), name='create-payment'),
    path('payments/<uuid:transaction_id>/status/', views.TransactionStatusView.as_view(), name='transaction-status'),
    path('promo/<str:promo_code>/info/', views.PromoInfoView.as_view(), name='promo-info'),
    path('promo/claim/', views.ClaimPromoView.as_view(), name='claim-promo'),
    
    # Real Payment Processing endpoints
    path('payments/<uuid:transaction_id>/card/create/', views.CreateCardPaymentView.as_view(), name='create-card-payment'),
    path('payments/<uuid:transaction_id>/card/confirm/', views.ConfirmCardPaymentView.as_view(), name='confirm-card-payment'),
    path('payments/<uuid:transaction_id>/crypto/create/', views.CreateCryptoPaymentView.as_view(), name='create-crypto-payment'),
    path('payments/<uuid:transaction_id>/crypto/check/', views.CheckCryptoPaymentView.as_view(), name='check-crypto-payment'),
    path('payouts/<uuid:payout_id>/status/', views.PayoutStatusView.as_view(), name='payout-status'),
    
    # Webhook endpoints
    path('webhooks/stripe/', views.StripeWebhookView.as_view(), name='stripe-webhook'),
    
    # Admin API endpoints
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    
    # Include router URLs
    path('', include(router.urls)),
    
    # Utility endpoints
    path('health/', views.health_check, name='health-check'),
]
