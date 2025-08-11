import logging
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Count, Sum, Q
from datetime import timedelta, datetime

from .models import Currency, Transaction, PromoLink, CommissionSetting, ExchangeRate
from .serializers import (
    CurrencySerializer, CreatePaymentSerializer, PaymentResponseSerializer,
    TransactionStatusSerializer, ClaimPromoSerializer, PromoInfoSerializer,
    AdminTransactionSerializer, AdminPromoLinkSerializer, CommissionSettingSerializer,
    CreateCommissionSettingSerializer, DashboardStatsSerializer, TestCommissionSerializer,
    ExchangeRateSerializer
)
from .services import PaymentService, ExchangeRateService, PromoLinkService, CommissionService

logger = logging.getLogger(__name__)


# Public API Views

class CurrencyListView(APIView):
    """List all supported currencies"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Get list of supported currencies"""
        try:
            currencies = Currency.objects.filter(is_active=True).order_by('code')
            serializer = CurrencySerializer(currencies, many=True)
            return Response({
                'success': True,
                'currencies': serializer.data
            })
        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error fetching currencies'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExchangeRateView(APIView):
    """Get current exchange rates"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Get current exchange rates"""
        try:
            from_currency = request.query_params.get('from')
            to_currency = request.query_params.get('to')
            
            if from_currency and to_currency:
                # Get specific rate
                exchange_service = ExchangeRateService()
                from_curr = Currency.objects.get(code=from_currency.upper(), is_active=True)
                to_curr = Currency.objects.get(code=to_currency.upper(), is_active=True)
                
                rate = exchange_service.get_exchange_rate(from_curr, to_curr)
                
                return Response({
                    'success': True,
                    'from_currency': from_currency.upper(),
                    'to_currency': to_currency.upper(),
                    'rate': rate,
                    'timestamp': timezone.now().isoformat()
                })
            else:
                # Get recent rates
                recent_rates = ExchangeRate.objects.filter(
                    timestamp__gte=timezone.now() - timedelta(hours=1)
                ).order_by('-timestamp')[:50]
                
                serializer = ExchangeRateSerializer(recent_rates, many=True)
                return Response({
                    'success': True,
                    'rates': serializer.data
                })
                
        except Currency.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Currency not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching exchange rates: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error fetching exchange rates'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreatePaymentView(APIView):
    """Create a new payment"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Create a new payment transaction"""
        try:
            serializer = CreatePaymentSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid payment data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create payment using service
            payment_service = PaymentService()
            result = payment_service.create_payment(serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Payment created successfully',
                'data': result
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransactionStatusView(APIView):
    """Get transaction status"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, transaction_id):
        """Get current status of a transaction"""
        try:
            payment_service = PaymentService()
            result = payment_service.get_transaction_status(transaction_id)
            
            return Response({
                'success': True,
                'data': result
            })
            
        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting transaction status: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error retrieving transaction status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PromoInfoView(APIView):
    """Get promo code information"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, promo_code):
        """Get information about a promo code"""
        try:
            promo_service = PromoLinkService()
            result = promo_service.get_promo_link_info(promo_code)
            
            return Response({
                'success': True,
                'data': result
            })
            
        except Exception as e:
            logger.error(f"Error getting promo info: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error retrieving promo information'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClaimPromoView(APIView):
    """Claim a promo code with real payout"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Claim a promo code and receive real funds"""
        try:
            serializer = ClaimPromoSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid claim data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get client IP
            ip_address = self._get_client_ip(request)
            
            # Process claim with real payout
            payment_service = PaymentService()
            result = payment_service.process_promo_claim_with_payout(
                promo_code=serializer.validated_data['promo_code'],
                recipient_data={
                    'wallet': serializer.validated_data.get('recipient_wallet'),
                    'email': serializer.validated_data.get('recipient_email'),
                    'telegram': serializer.validated_data.get('recipient_telegram'),
                    'payout_method': serializer.validated_data['payout_method'],
                    'bank_details': request.data.get('bank_details', {})  # For bank transfers
                },
                ip_address=ip_address
            )
            
            if result['success']:
                return Response({
                    'success': True,
                    'message': result['message'],
                    'data': {
                        'payout_id': result['payout_id'],
                        'payout_method': result['payout_method'],
                        'amount': result['amount'],
                        'currency': result['currency'],
                        'estimated_delivery': result['estimated_delivery'],
                        'reference': result['reference']
                    }
                })
            else:
                return Response({
                    'success': False,
                    'message': result['message'],
                    'error_code': result.get('error_code')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error claiming promo: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error processing claim'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Real Payment Processing Views

class CreateCardPaymentView(APIView):
    """Create Stripe payment intent for card payment"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, transaction_id):
        """Create payment intent for card payment"""
        try:
            payment_service = PaymentService()
            result = payment_service.create_card_payment_intent(
                transaction_id=transaction_id,
                card_data=request.data
            )
            
            if result['success']:
                return Response({
                    'success': True,
                    'data': {
                        'payment_intent_id': result['payment_intent_id'],
                        'client_secret': result['client_secret'],
                        'amount': result['amount'],
                        'currency': result['currency'],
                        'status': result['status']
                    }
                })
            else:
                return Response({
                    'success': False,
                    'message': result.get('error', 'Payment intent creation failed'),
                    'error_code': result.get('error_code')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating card payment: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error creating payment intent'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmCardPaymentView(APIView):
    """Confirm card payment with payment method"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, transaction_id):
        """Confirm card payment"""
        try:
            payment_method_id = request.data.get('payment_method_id')
            if not payment_method_id:
                return Response({
                    'success': False,
                    'message': 'Payment method ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            payment_service = PaymentService()
            result = payment_service.confirm_card_payment(
                transaction_id=transaction_id,
                payment_method_id=payment_method_id
            )
            
            return Response({
                'success': result['success'],
                'message': result.get('message', ''),
                'data': result if result['success'] else None,
                'error': result.get('error') if not result['success'] else None
            }, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)
            
        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error confirming card payment: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error confirming payment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateCryptoPaymentView(APIView):
    """Create crypto payment address"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, transaction_id):
        """Generate crypto deposit address"""
        try:
            payment_service = PaymentService()
            result = payment_service.process_crypto_payment(
                transaction_id=transaction_id,
                crypto_data=request.data
            )
            
            return Response({
                'success': result.get('success', True),
                'data': result
            })
            
        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating crypto payment: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error creating crypto payment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckCryptoPaymentView(APIView):
    """Check crypto payment confirmation"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, transaction_id):
        """Check crypto payment confirmation status"""
        try:
            payment_service = PaymentService()
            result = payment_service.process_crypto_payment(
                transaction_id=transaction_id,
                crypto_data={}  # Just checking status
            )
            
            return Response({
                'success': result.get('success', True),
                'data': result
            })
            
        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error checking crypto payment: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error checking crypto payment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PayoutStatusView(APIView):
    """Check payout status"""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, payout_id):
        """Get payout status"""
        try:
            payment_service = PaymentService()
            result = payment_service.check_payout_status(payout_id)
            
            if result['success']:
                return Response({
                    'success': True,
                    'data': result
                })
            else:
                return Response({
                    'success': False,
                    'message': result['message'],
                    'error_code': result.get('error_code')
                }, status=status.HTTP_404_NOT_FOUND if result.get('error_code') == 'PAYOUT_NOT_FOUND' else status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Error checking payout status: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error checking payout status'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StripeWebhookView(APIView):
    """Handle Stripe webhooks"""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Process Stripe webhook"""
        try:
            payload = request.body
            sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
            
            if not sig_header:
                return Response({
                    'error': 'Missing Stripe signature'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            from .services.stripe_service import StripePaymentService
            stripe_service = StripePaymentService()
            
            result = stripe_service.handle_webhook(payload, sig_header)
            
            if result['success']:
                return Response({'received': True})
            else:
                return Response({
                    'error': result.get('error', 'Webhook processing failed')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error processing Stripe webhook: {str(e)}")
            return Response({
                'error': 'Webhook processing failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Admin API Views

class AdminDashboardView(APIView):
    """Admin dashboard statistics"""
    
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get(self, request):
        """Get dashboard statistics"""
        try:
            today = timezone.now().date()
            
            # Today's statistics
            today_transactions = Transaction.objects.filter(
                created_at__date=today
            ).aggregate(
                count=Count('id'),
                volume=Sum('original_amount'),
                commission=Sum('commission_amount')
            )
            
            # Promo link statistics
            promo_stats = {
                'active': PromoLink.objects.filter(
                    is_used=False,
                    expires_at__gt=timezone.now()
                ).count(),
                'used': PromoLink.objects.filter(is_used=True).count(),
                'expired': PromoLink.objects.filter(
                    is_used=False,
                    expires_at__lte=timezone.now()
                ).count()
            }
            
            # Provider statistics
            from apps.providers.models import Provider
            provider_stats = {
                'total': Provider.objects.count(),
                'active': Provider.objects.filter(is_active=True).count()
            }
            
            # Recent transactions
            recent_transactions = Transaction.objects.select_related(
                'original_currency', 'converted_currency', 'provider'
            ).order_by('-created_at')[:10]
            
            dashboard_data = {
                'today_transactions': today_transactions['count'] or 0,
                'today_volume': today_transactions['volume'] or 0,
                'today_commission': today_transactions['commission'] or 0,
                'active_promo_links': promo_stats['active'],
                'used_promo_links': promo_stats['used'],
                'expired_promo_links': promo_stats['expired'],
                'total_providers': provider_stats['total'],
                'active_providers': provider_stats['active'],
                'recent_transactions': AdminTransactionSerializer(recent_transactions, many=True).data
            }
            
            return Response({
                'success': True,
                'data': dashboard_data
            })
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error retrieving dashboard statistics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin transaction management"""
    
    queryset = Transaction.objects.select_related(
        'original_currency', 'converted_currency', 'provider'
    ).order_by('-created_at')
    serializer_class = AdminTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'original_currency__code', 'converted_currency__code', 'provider']
    search_fields = ['id', 'contact_email', 'payment_reference']
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a transaction (admin only)"""
        try:
            transaction = self.get_object()
            
            if transaction.status not in ['pending', 'processing']:
                return Response({
                    'success': False,
                    'message': 'Can only cancel pending or processing transactions'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            transaction.status = 'cancelled'
            transaction.save()
            
            return Response({
                'success': True,
                'message': 'Transaction cancelled successfully'
            })
            
        except Exception as e:
            logger.error(f"Error cancelling transaction: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error cancelling transaction'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPromoLinkViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin promo link management"""
    
    queryset = PromoLink.objects.select_related(
        'transaction', 'transaction__converted_currency'
    ).order_by('-created_at')
    serializer_class = AdminPromoLinkSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_used']
    search_fields = ['code', 'transaction__id']


class CommissionSettingViewSet(viewsets.ModelViewSet):
    """Commission settings management"""
    
    queryset = CommissionSetting.objects.select_related(
        'currency', 'provider'
    ).filter(is_active=True).order_by('-is_global', 'currency__code')
    serializer_class = CommissionSettingSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def create(self, request):
        """Create new commission setting"""
        try:
            serializer = CreateCommissionSettingSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid commission data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            commission_service = CommissionService()
            result = commission_service.update_commission_setting(serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Commission setting created successfully',
                'data': result
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating commission setting: {str(e)}")
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def test_calculation(self, request):
        """Test commission calculation"""
        try:
            serializer = TestCommissionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            commission_service = CommissionService()
            result = commission_service.test_commission_calculation(serializer.validated_data)
            
            return Response({
                'success': True,
                'data': result
            })
            
        except Exception as e:
            logger.error(f"Error testing commission: {str(e)}")
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


# Utility API Views

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'version': '1.0.0'
    })
