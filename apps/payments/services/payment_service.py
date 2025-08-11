import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from ..models import Transaction, Currency, TransactionLog, EscrowAccount, PayoutRequest
from .exchange_service import ExchangeRateService
from .commission_service import CommissionService
from .promo_service import PromoLinkService
from .stripe_service import StripePaymentService
from .crypto_service import CryptoWalletService

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for handling payment processing logic"""
    
    def __init__(self):
        self.exchange_service = ExchangeRateService()
        self.commission_service = CommissionService()
        self.promo_service = PromoLinkService()
        self.stripe_service = StripePaymentService()
        self.crypto_service = CryptoWalletService()

    def create_payment(self, payment_data):
        """
        Create a new payment transaction
        
        Args:
            payment_data (dict): {
                'amount': Decimal,
                'from_currency': str,
                'to_currency': str,
                'contact_email': str (optional),
                'contact_telegram': str (optional),
                'provider_id': str (optional),
                'payment_method': str (optional)
            }
            
        Returns:
            dict: Transaction data with promo link
        """
        try:
            with transaction.atomic():
                # Validate currencies
                from_currency = self._get_currency(payment_data['from_currency'])
                to_currency = self._get_currency(payment_data['to_currency'])
                
                # Validate amount
                amount = Decimal(str(payment_data['amount']))
                self._validate_amount(amount)
                
                # Get exchange rate and convert
                conversion_data = self.exchange_service.convert_currency(
                    amount, from_currency, to_currency
                )
                
                # Calculate commission
                commission_data = self.commission_service.calculate_commission(
                    amount=conversion_data['converted_amount'],
                    currency=to_currency,
                    provider_id=payment_data.get('provider_id')
                )
                
                # Create transaction
                transaction_obj = self._create_transaction(
                    original_amount=amount,
                    original_currency=from_currency,
                    converted_amount=conversion_data['converted_amount'],
                    converted_currency=to_currency,
                    commission_data=commission_data,
                    payment_data=payment_data
                )
                
                # Create promo link
                promo_link = self.promo_service.create_promo_link(transaction_obj)
                
                # Log transaction creation
                self._log_transaction_action(
                    transaction_obj, 
                    'created',
                    details=payment_data
                )
                
                return {
                    'transaction_id': str(transaction_obj.id),
                    'original_amount': transaction_obj.original_amount,
                    'original_currency': transaction_obj.original_currency.code,
                    'converted_amount': transaction_obj.converted_amount,
                    'converted_currency': transaction_obj.converted_currency.code,
                    'commission_rate': transaction_obj.commission_rate,
                    'commission_amount': transaction_obj.commission_amount,
                    'net_amount': transaction_obj.net_amount,
                    'expires_at': transaction_obj.expires_at.isoformat(),
                    'promo_code': promo_link.code,
                    'promo_url': promo_link.link_url,
                    'qr_code': promo_link.qr_code_data,
                    'status': transaction_obj.status
                }
                
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            raise

    def process_fiat_payment(self, transaction_id, payment_method_data):
        """
        Process fiat payment (Stripe, PayPal, etc.)
        
        Args:
            transaction_id (str): Transaction UUID
            payment_method_data (dict): Payment method specific data
            
        Returns:
            dict: Payment processing result
        """
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            
            if transaction_obj.status != 'pending':
                raise ValueError(f"Transaction {transaction_id} is not in pending status")
            
            # Update status to processing
            transaction_obj.status = 'processing'
            transaction_obj.save()
            
            self._log_transaction_action(
                transaction_obj,
                'status_changed',
                old_status='pending',
                new_status='processing'
            )
            
            # Process based on payment method
            if payment_method_data.get('method') == 'stripe':
                result = self._process_stripe_payment(transaction_obj, payment_method_data)
            else:
                raise ValueError(f"Unsupported payment method: {payment_method_data.get('method')}")
            
            if result['success']:
                transaction_obj.status = 'completed'
                transaction_obj.completed_at = timezone.now()
                transaction_obj.payment_reference = result.get('reference', '')
                transaction_obj.save()
                
                self._log_transaction_action(
                    transaction_obj,
                    'payment_completed',
                    details=result
                )
                
                # Notify provider if applicable
                if transaction_obj.provider:
                    self._notify_provider(transaction_obj, 'payment_completed')
            else:
                transaction_obj.status = 'failed'
                transaction_obj.save()
                
                self._log_transaction_action(
                    transaction_obj,
                    'payment_failed',
                    details=result
                )
            
            return {
                'success': result['success'],
                'transaction_id': str(transaction_obj.id),
                'status': transaction_obj.status,
                'reference': transaction_obj.payment_reference,
                'message': result.get('message', '')
            }
            
        except Transaction.DoesNotExist:
            raise ValueError(f"Transaction {transaction_id} not found")
        except Exception as e:
            logger.error(f"Error processing fiat payment: {str(e)}")
            raise

    def process_crypto_payment(self, transaction_id, crypto_data):
        """
        Process cryptocurrency payment
        
        Args:
            transaction_id (str): Transaction UUID
            crypto_data (dict): Crypto payment data
            
        Returns:
            dict: Payment processing result
        """
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            
            # Generate crypto deposit address
            if not transaction_obj.crypto_deposit_address:
                address_result = self.crypto_service.generate_deposit_address(transaction_obj)
                
                if not address_result['success']:
                    return address_result
                
                return {
                    'success': True,
                    'transaction_id': str(transaction_obj.id),
                    'deposit_address': address_result['address'],
                    'amount': address_result['amount'],
                    'currency': address_result['currency'],
                    'qr_code': address_result['qr_code'],
                    'message': 'Deposit address generated. Send crypto to this address.',
                    'status': 'awaiting_deposit'
                }
            else:
                # Check deposit confirmation
                confirmation_result = self.crypto_service.check_deposit_confirmation(transaction_obj)
                return confirmation_result
            
        except Transaction.DoesNotExist:
            raise ValueError(f"Transaction {transaction_id} not found")
        except Exception as e:
            logger.error(f"Error processing crypto payment: {str(e)}")
            raise
    
    def create_card_payment_intent(self, transaction_id, card_data):
        """
        Create Stripe Payment Intent for card payment
        
        Args:
            transaction_id (str): Transaction UUID
            card_data (dict): Card payment data
            
        Returns:
            dict: Payment intent result
        """
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            
            # Create Stripe Payment Intent
            intent_result = self.stripe_service.create_payment_intent(transaction_obj, card_data)
            
            if intent_result['success']:
                self._log_transaction_action(
                    transaction_obj,
                    'payment_intent_created',
                    details=intent_result
                )
            
            return intent_result
            
        except Transaction.DoesNotExist:
            raise ValueError(f"Transaction {transaction_id} not found")
        except Exception as e:
            logger.error(f"Error creating payment intent: {str(e)}")
            raise
    
    def confirm_card_payment(self, transaction_id, payment_method_id):
        """
        Confirm card payment with payment method
        
        Args:
            transaction_id (str): Transaction UUID
            payment_method_id (str): Stripe Payment Method ID
            
        Returns:
            dict: Confirmation result
        """
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            
            if not transaction_obj.stripe_payment_intent_id:
                raise ValueError("No payment intent found for this transaction")
            
            # Confirm payment
            confirm_result = self.stripe_service.confirm_payment_intent(
                transaction_obj.stripe_payment_intent_id,
                payment_method_id
            )
            
            if confirm_result['success']:
                if confirm_result['status'] == 'succeeded':
                    # Automatically capture payment
                    capture_result = self.stripe_service.capture_payment(transaction_obj)
                    
                    if capture_result['success']:
                        transaction_obj.status = 'escrowed'
                        transaction_obj.save()
                        
                        # Make promo link ready for claim
                        promo_link = transaction_obj.promo_link
                        transaction_obj.status = 'ready_for_claim'
                        transaction_obj.save()
                        
                        self._log_transaction_action(
                            transaction_obj,
                            'payment_captured_and_escrowed',
                            details=capture_result
                        )
                        
                        return {
                            'success': True,
                            'status': 'ready_for_claim',
                            'message': 'Payment successful! Promo link is ready to be claimed.',
                            'promo_code': promo_link.code,
                            'promo_url': promo_link.link_url
                        }
                    else:
                        return capture_result
                elif confirm_result['requires_action']:
                    return {
                        'success': True,
                        'requires_action': True,
                        'client_secret': confirm_result['client_secret'],
                        'message': 'Additional authentication required'
                    }
            
            return confirm_result
            
        except Transaction.DoesNotExist:
            raise ValueError(f"Transaction {transaction_id} not found")
        except Exception as e:
            logger.error(f"Error confirming card payment: {str(e)}")
            raise
    
    def process_promo_claim_with_payout(self, promo_code, recipient_data, ip_address=None):
        """
        Process promo claim and create real payout
        
        Args:
            promo_code (str): Promo code to claim
            recipient_data (dict): Recipient payout information
            ip_address (str): IP address of claimant
            
        Returns:
            dict: Claim and payout result
        """
        try:
            with transaction.atomic():
                # First, claim the promo link
                claim_result = self.promo_service.claim_promo_link(
                    promo_code, recipient_data, ip_address
                )
                
                if not claim_result['success']:
                    return claim_result
                
                # Get the promo link and transaction
                from ..models import PromoLink
                promo_link = PromoLink.objects.select_related('transaction').get(code=promo_code)
                transaction_obj = promo_link.transaction
                
                # Validate that funds are escrowed
                if transaction_obj.status != 'ready_for_claim':
                    return {
                        'success': False,
                        'message': 'Transaction is not ready for claim',
                        'error_code': 'NOT_READY'
                    }
                
                # Create payout request
                payout_request = self._create_payout_request(promo_link, recipient_data)
                
                # Process payout based on method
                payout_result = self._process_payout(payout_request)
                
                if payout_result['success']:
                    transaction_obj.status = 'claim_processing'
                    transaction_obj.save()
                    
                    self._log_transaction_action(
                        transaction_obj,
                        'payout_initiated',
                        details=payout_result
                    )
                    
                    return {
                        'success': True,
                        'message': 'Payout initiated successfully',
                        'payout_id': str(payout_request.id),
                        'payout_method': payout_request.payout_method,
                        'amount': payout_request.payout_amount,
                        'currency': payout_request.payout_currency.code,
                        'estimated_delivery': payout_result.get('estimated_delivery', 'Unknown'),
                        'reference': payout_result.get('reference', '')
                    }
                else:
                    # Revert promo link claim if payout fails
                    promo_link.is_used = False
                    promo_link.used_at = None
                    promo_link.save()
                    
                    transaction_obj.status = 'ready_for_claim'
                    transaction_obj.save()
                    
                    return payout_result
                    
        except Exception as e:
            logger.error(f"Error processing promo claim with payout: {str(e)}")
            return {
                'success': False,
                'message': 'Error processing payout',
                'error_code': 'PAYOUT_ERROR'
            }
    
    def check_payout_status(self, payout_id):
        """
        Check status of a payout request
        
        Args:
            payout_id (str): Payout request UUID
            
        Returns:
            dict: Payout status
        """
        try:
            payout_request = PayoutRequest.objects.select_related(
                'promo_link__transaction', 'payout_currency'
            ).get(id=payout_id)
            
            return {
                'success': True,
                'payout_id': str(payout_request.id),
                'status': payout_request.status,
                'payout_method': payout_request.payout_method,
                'amount': payout_request.payout_amount,
                'currency': payout_request.payout_currency.code,
                'processing_fee': payout_request.processing_fee,
                'created_at': payout_request.created_at.isoformat(),
                'processed_at': payout_request.processed_at.isoformat() if payout_request.processed_at else None,
                'completed_at': payout_request.completed_at.isoformat() if payout_request.completed_at else None,
                'failure_reason': payout_request.failure_reason,
                'external_reference': payout_request.external_payout_id
            }
            
        except PayoutRequest.DoesNotExist:
            return {
                'success': False,
                'message': 'Payout request not found',
                'error_code': 'PAYOUT_NOT_FOUND'
            }
        except Exception as e:
            logger.error(f"Error checking payout status: {str(e)}")
            return {
                'success': False,
                'message': 'Error retrieving payout status',
                'error_code': 'STATUS_ERROR'
            }

    def get_transaction_status(self, transaction_id):
        """Get current status of a transaction"""
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            
            return {
                'transaction_id': str(transaction_obj.id),
                'status': transaction_obj.status,
                'original_amount': transaction_obj.original_amount,
                'original_currency': transaction_obj.original_currency.code,
                'net_amount': transaction_obj.net_amount,
                'converted_currency': transaction_obj.converted_currency.code,
                'created_at': transaction_obj.created_at.isoformat(),
                'expires_at': transaction_obj.expires_at.isoformat(),
                'completed_at': transaction_obj.completed_at.isoformat() if transaction_obj.completed_at else None,
                'is_expired': transaction_obj.is_expired,
                'time_remaining': str(transaction_obj.time_remaining)
            }
            
        except Transaction.DoesNotExist:
            raise ValueError(f"Transaction {transaction_id} not found")

    def expire_old_transactions(self):
        """Expire transactions that have exceeded their expiry time"""
        expired_count = 0
        
        expired_transactions = Transaction.objects.filter(
            status='pending',
            expires_at__lt=timezone.now()
        )
        
        for transaction_obj in expired_transactions:
            transaction_obj.status = 'expired'
            transaction_obj.save()
            
            self._log_transaction_action(
                transaction_obj,
                'auto_expired'
            )
            
            expired_count += 1
        
        logger.info(f"Expired {expired_count} transactions")
        return expired_count

    def _get_currency(self, currency_code):
        """Get currency object by code"""
        try:
            return Currency.objects.get(code=currency_code.upper(), is_active=True)
        except Currency.DoesNotExist:
            raise ValueError(f"Currency {currency_code} not found or inactive")

    def _validate_amount(self, amount):
        """Validate transaction amount"""
        min_amount = Decimal(str(settings.UCPG_SETTINGS['MIN_TRANSACTION_AMOUNT']))
        max_amount = Decimal(str(settings.UCPG_SETTINGS['MAX_TRANSACTION_AMOUNT']))
        
        if amount < min_amount:
            raise ValueError(f"Amount {amount} is below minimum {min_amount}")
        
        if amount > max_amount:
            raise ValueError(f"Amount {amount} exceeds maximum {max_amount}")

    def _create_transaction(self, original_amount, original_currency, converted_amount, 
                          converted_currency, commission_data, payment_data):
        """Create transaction object"""
        
        # Calculate expiry time
        expiry_hours = settings.UCPG_SETTINGS['PROMO_LINK_EXPIRY_HOURS']
        expires_at = timezone.now() + timedelta(hours=expiry_hours)
        
        transaction_obj = Transaction.objects.create(
            original_amount=original_amount,
            original_currency=original_currency,
            converted_amount=converted_amount,
            converted_currency=converted_currency,
            commission_rate=commission_data['rate'],
            commission_amount=commission_data['amount'],
            net_amount=commission_data['net_amount'],
            expires_at=expires_at,
            contact_email=payment_data.get('contact_email', ''),
            contact_telegram=payment_data.get('contact_telegram', ''),
            payment_method=payment_data.get('payment_method', ''),
            provider_id=payment_data.get('provider_id')
        )
        
        return transaction_obj

    def _process_stripe_payment(self, transaction_obj, payment_data):
        """Process payment via Stripe"""
        try:
            # This would integrate with actual Stripe API
            # For now, we'll simulate a successful payment
            
            return {
                'success': True,
                'reference': f"stripe_{transaction_obj.id}",
                'message': 'Payment processed successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Stripe payment failed: {str(e)}"
            }

    def _notify_provider(self, transaction_obj, event):
        """Send webhook notification to provider"""
        if not transaction_obj.provider:
            return
        
        # This would be handled by a separate webhook service
        # For now, we'll just log it
        logger.info(f"Provider notification: {transaction_obj.provider.name} - {event}")

    def _create_payout_request(self, promo_link, recipient_data):
        """Create payout request from recipient data"""
        transaction_obj = promo_link.transaction
        
        # Determine payout method and currency
        payout_method = recipient_data.get('payout_method', 'crypto_wallet')
        payout_currency = transaction_obj.converted_currency
        
        # Create payout request
        payout_request = PayoutRequest.objects.create(
            promo_link=promo_link,
            payout_method=payout_method,
            payout_amount=transaction_obj.net_amount,
            payout_currency=payout_currency,
            recipient_crypto_address=recipient_data.get('wallet', ''),
            recipient_email=recipient_data.get('email', ''),
            # Note: In production, encrypt sensitive data like bank details
            recipient_bank_details=recipient_data.get('bank_details', {}),
            status='pending'
        )
        
        return payout_request
    
    def _process_payout(self, payout_request):
        """Process payout based on method"""
        try:
            if payout_request.payout_method in ['stripe_card', 'bank_transfer']:
                return self.stripe_service.create_payout(payout_request)
            elif payout_request.payout_method == 'crypto_wallet':
                return self.crypto_service.create_crypto_payout(payout_request)
            else:
                return {
                    'success': False,
                    'error': f'Payout method {payout_request.payout_method} not supported'
                }
        except Exception as e:
            logger.error(f"Error processing payout: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _log_transaction_action(self, transaction_obj, action, old_status=None, 
                               new_status=None, details=None):
        """Log transaction action for audit trail"""
        TransactionLog.objects.create(
            transaction=transaction_obj,
            action=action,
            old_status=old_status or '',
            new_status=new_status or transaction_obj.status,
            details=details or {}
        )
