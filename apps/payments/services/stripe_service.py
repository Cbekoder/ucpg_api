import logging
import stripe
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from typing import Dict, Optional

from ..models import Transaction, EscrowAccount, PayoutRequest, Currency

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripePaymentService:
    """Service for handling Stripe payments and payouts"""
    
    def __init__(self):
        self.stripe = stripe
        self.webhook_endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    
    def create_payment_intent(self, transaction: Transaction, card_data: Dict) -> Dict:
        """
        Create a Stripe Payment Intent for card payment
        
        Args:
            transaction: Transaction object
            card_data: Card payment data
            
        Returns:
            dict: Payment intent result
        """
        try:
            # Convert amount to cents (Stripe uses smallest currency unit)
            amount_cents = int(transaction.original_amount * 100)
            
            # Create payment intent
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=transaction.original_currency.code.lower(),
                payment_method_types=['card'],
                metadata={
                    'transaction_id': str(transaction.id),
                    'ucpg_payment': 'true',
                    'original_amount': str(transaction.original_amount),
                    'net_amount': str(transaction.net_amount),
                },
                description=f'UCPG Payment - {transaction.original_amount} {transaction.original_currency.code}',
                receipt_email=transaction.contact_email if transaction.contact_email else None,
                capture_method='manual',  # Manual capture for escrow
            )
            
            # Update transaction with Stripe details
            transaction.stripe_payment_intent_id = intent.id
            transaction.payment_method = 'stripe_card'
            transaction.status = 'payment_processing'
            transaction.save()
            
            logger.info(f"Created Stripe Payment Intent {intent.id} for transaction {transaction.id}")
            
            return {
                'success': True,
                'payment_intent_id': intent.id,
                'client_secret': intent.client_secret,
                'status': intent.status,
                'amount': intent.amount,
                'currency': intent.currency,
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payment intent: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.code if hasattr(e, 'code') else 'stripe_error'
            }
        except Exception as e:
            logger.error(f"Unexpected error creating payment intent: {str(e)}")
            return {
                'success': False,
                'error': 'An unexpected error occurred',
                'error_code': 'internal_error'
            }
    
    def confirm_payment_intent(self, payment_intent_id: str, payment_method_id: str) -> Dict:
        """
        Confirm a payment intent with payment method
        
        Args:
            payment_intent_id: Stripe Payment Intent ID
            payment_method_id: Stripe Payment Method ID
            
        Returns:
            dict: Confirmation result
        """
        try:
            intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id,
                return_url='https://ucpg.com/payment/return'  # For 3D Secure
            )
            
            return {
                'success': True,
                'status': intent.status,
                'payment_intent_id': intent.id,
                'requires_action': intent.status == 'requires_action',
                'client_secret': intent.client_secret if intent.status == 'requires_action' else None
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error confirming payment: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.code if hasattr(e, 'code') else 'stripe_error'
            }
    
    def capture_payment(self, transaction: Transaction) -> Dict:
        """
        Capture a confirmed payment and move funds to escrow
        
        Args:
            transaction: Transaction object
            
        Returns:
            dict: Capture result
        """
        try:
            if not transaction.stripe_payment_intent_id:
                return {
                    'success': False,
                    'error': 'No Stripe Payment Intent ID found'
                }
            
            # Capture the payment
            intent = stripe.PaymentIntent.capture(transaction.stripe_payment_intent_id)
            
            if intent.status == 'succeeded':
                # Move funds to escrow
                escrow_result = self._move_to_escrow(transaction, intent)
                
                if escrow_result['success']:
                    transaction.status = 'escrowed'
                    transaction.escrow_account_id = escrow_result['escrow_account_id']
                    transaction.escrow_amount = transaction.net_amount
                    transaction.escrow_currency = transaction.converted_currency.code
                    transaction.save()
                    
                    logger.info(f"Payment captured and escrowed for transaction {transaction.id}")
                    
                    return {
                        'success': True,
                        'status': 'escrowed',
                        'escrow_account_id': escrow_result['escrow_account_id']
                    }
                else:
                    # Refund if escrow fails
                    self.refund_payment(transaction, 'Escrow failed')
                    return escrow_result
            else:
                return {
                    'success': False,
                    'error': f'Payment capture failed with status: {intent.status}'
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error capturing payment: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.code if hasattr(e, 'code') else 'stripe_error'
            }
    
    def create_payout(self, payout_request: PayoutRequest) -> Dict:
        """
        Create a payout to recipient's card/account
        
        Args:
            payout_request: PayoutRequest object
            
        Returns:
            dict: Payout result
        """
        try:
            # Get the transaction
            transaction = payout_request.promo_link.transaction
            
            if payout_request.payout_method == 'stripe_card':
                return self._create_card_payout(payout_request)
            elif payout_request.payout_method == 'bank_transfer':
                return self._create_bank_payout(payout_request)
            else:
                return {
                    'success': False,
                    'error': f'Payout method {payout_request.payout_method} not supported via Stripe'
                }
                
        except Exception as e:
            logger.error(f"Error creating payout: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def refund_payment(self, transaction: Transaction, reason: str = '') -> Dict:
        """
        Refund a payment
        
        Args:
            transaction: Transaction object
            reason: Refund reason
            
        Returns:
            dict: Refund result
        """
        try:
            if not transaction.stripe_payment_intent_id:
                return {
                    'success': False,
                    'error': 'No Stripe Payment Intent ID found'
                }
            
            # Create refund
            refund = stripe.Refund.create(
                payment_intent=transaction.stripe_payment_intent_id,
                reason='requested_by_customer',
                metadata={
                    'transaction_id': str(transaction.id),
                    'refund_reason': reason
                }
            )
            
            if refund.status == 'succeeded':
                transaction.status = 'refunded'
                transaction.save()
                
                logger.info(f"Payment refunded for transaction {transaction.id}")
                
                return {
                    'success': True,
                    'refund_id': refund.id,
                    'amount': refund.amount / 100,  # Convert from cents
                    'status': refund.status
                }
            else:
                return {
                    'success': False,
                    'error': f'Refund failed with status: {refund.status}'
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating refund: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.code if hasattr(e, 'code') else 'stripe_error'
            }
    
    def handle_webhook(self, payload: str, sig_header: str) -> Dict:
        """
        Handle Stripe webhook events
        
        Args:
            payload: Webhook payload
            sig_header: Stripe signature header
            
        Returns:
            dict: Webhook processing result
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_endpoint_secret
            )
            
            event_type = event['type']
            event_data = event['data']['object']
            
            logger.info(f"Processing Stripe webhook: {event_type}")
            
            if event_type == 'payment_intent.succeeded':
                return self._handle_payment_succeeded(event_data)
            elif event_type == 'payment_intent.payment_failed':
                return self._handle_payment_failed(event_data)
            elif event_type == 'transfer.created':
                return self._handle_transfer_created(event_data)
            elif event_type == 'payout.paid':
                return self._handle_payout_paid(event_data)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                return {'success': True, 'message': 'Event not handled'}
                
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {str(e)}")
            return {
                'success': False,
                'error': 'Invalid signature'
            }
        except Exception as e:
            logger.error(f"Error processing Stripe webhook: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _move_to_escrow(self, transaction: Transaction, payment_intent) -> Dict:
        """Move captured funds to escrow account"""
        try:
            # Get or create escrow account for this currency
            currency = transaction.converted_currency
            escrow_account, created = EscrowAccount.objects.get_or_create(
                account_type='stripe',
                currency=currency,
                defaults={
                    'account_reference': f'stripe_escrow_{currency.code.lower()}',
                    'total_balance': Decimal('0'),
                    'available_balance': Decimal('0'),
                    'reserved_balance': Decimal('0')
                }
            )
            
            # Add funds to escrow
            net_amount = transaction.net_amount
            escrow_account.total_balance += net_amount
            escrow_account.available_balance += net_amount
            escrow_account.save()
            
            return {
                'success': True,
                'escrow_account_id': str(escrow_account.id)
            }
            
        except Exception as e:
            logger.error(f"Error moving funds to escrow: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_card_payout(self, payout_request: PayoutRequest) -> Dict:
        """Create payout to recipient's card"""
        try:
            # Note: Direct card payouts are complex and may require additional verification
            # This is a simplified implementation - in production, you'd need proper recipient verification
            
            amount_cents = int(payout_request.payout_amount * 100)
            
            # Create a transfer (this would typically go to a connected account)
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency=payout_request.payout_currency.code.lower(),
                destination='acct_connected_account_id',  # This would be recipient's connected account
                metadata={
                    'payout_request_id': str(payout_request.id),
                    'transaction_id': str(payout_request.promo_link.transaction.id)
                }
            )
            
            payout_request.external_payout_id = transfer.id
            payout_request.status = 'processing'
            payout_request.processed_at = timezone.now()
            payout_request.save()
            
            return {
                'success': True,
                'transfer_id': transfer.id,
                'status': 'processing'
            }
            
        except stripe.error.StripeError as e:
            payout_request.status = 'failed'
            payout_request.failure_reason = str(e)
            payout_request.save()
            
            logger.error(f"Stripe error creating card payout: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_bank_payout(self, payout_request: PayoutRequest) -> Dict:
        """Create bank transfer payout"""
        try:
            # Bank transfers would require recipient bank account setup
            # This is a placeholder implementation
            
            amount_cents = int(payout_request.payout_amount * 100)
            
            payout = stripe.Payout.create(
                amount=amount_cents,
                currency=payout_request.payout_currency.code.lower(),
                method='standard',
                metadata={
                    'payout_request_id': str(payout_request.id)
                }
            )
            
            payout_request.external_payout_id = payout.id
            payout_request.status = 'processing'
            payout_request.processed_at = timezone.now()
            payout_request.save()
            
            return {
                'success': True,
                'payout_id': payout.id,
                'status': 'processing'
            }
            
        except stripe.error.StripeError as e:
            payout_request.status = 'failed'
            payout_request.failure_reason = str(e)
            payout_request.save()
            
            logger.error(f"Stripe error creating bank payout: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _handle_payment_succeeded(self, payment_intent_data) -> Dict:
        """Handle successful payment webhook"""
        try:
            payment_intent_id = payment_intent_data['id']
            
            # Find transaction
            transaction = Transaction.objects.filter(
                stripe_payment_intent_id=payment_intent_id
            ).first()
            
            if transaction:
                # Automatically capture if not already captured
                if transaction.status == 'payment_processing':
                    capture_result = self.capture_payment(transaction)
                    return capture_result
                
            return {'success': True, 'message': 'Payment already processed'}
            
        except Exception as e:
            logger.error(f"Error handling payment succeeded webhook: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _handle_payment_failed(self, payment_intent_data) -> Dict:
        """Handle failed payment webhook"""
        try:
            payment_intent_id = payment_intent_data['id']
            
            # Find and update transaction
            transaction = Transaction.objects.filter(
                stripe_payment_intent_id=payment_intent_id
            ).first()
            
            if transaction:
                transaction.status = 'failed'
                transaction.save()
                
                logger.info(f"Payment failed for transaction {transaction.id}")
            
            return {'success': True, 'message': 'Payment failure processed'}
            
        except Exception as e:
            logger.error(f"Error handling payment failed webhook: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _handle_transfer_created(self, transfer_data) -> Dict:
        """Handle transfer created webhook"""
        try:
            transfer_id = transfer_data['id']
            
            # Find payout request
            payout_request = PayoutRequest.objects.filter(
                external_payout_id=transfer_id
            ).first()
            
            if payout_request:
                payout_request.status = 'processing'
                payout_request.save()
            
            return {'success': True, 'message': 'Transfer processed'}
            
        except Exception as e:
            logger.error(f"Error handling transfer webhook: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _handle_payout_paid(self, payout_data) -> Dict:
        """Handle payout paid webhook"""
        try:
            payout_id = payout_data['id']
            
            # Find payout request
            payout_request = PayoutRequest.objects.filter(
                external_payout_id=payout_id
            ).first()
            
            if payout_request:
                payout_request.status = 'completed'
                payout_request.completed_at = timezone.now()
                payout_request.save()
                
                # Update promo link transaction
                transaction = payout_request.promo_link.transaction
                transaction.status = 'completed'
                transaction.payout_completed_at = timezone.now()
                transaction.save()
            
            return {'success': True, 'message': 'Payout completed'}
            
        except Exception as e:
            logger.error(f"Error handling payout webhook: {str(e)}")
            return {'success': False, 'error': str(e)}
