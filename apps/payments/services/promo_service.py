import logging
import secrets
import string
import qrcode
import base64
from io import BytesIO
from django.conf import settings
from django.utils import timezone
from django.urls import reverse

from ..models import PromoLink, Transaction

logger = logging.getLogger(__name__)


class PromoLinkService:
    """Service for handling promo links and QR codes"""
    
    def __init__(self):
        self.code_length = settings.UCPG_SETTINGS['PROMO_CODE_LENGTH']

    def create_promo_link(self, transaction):
        """
        Create a promo link and QR code for a transaction
        
        Args:
            transaction (Transaction): Transaction object
            
        Returns:
            PromoLink: Created promo link object
        """
        try:
            # Generate unique promo code
            promo_code = self._generate_promo_code()
            
            # Ensure code is unique
            while PromoLink.objects.filter(code=promo_code).exists():
                promo_code = self._generate_promo_code()
            
            # Create full URL for the promo link
            link_url = self._build_promo_url(promo_code)
            
            # Generate QR code
            qr_code_data = self._generate_qr_code(link_url)
            
            # Create promo link object
            promo_link = PromoLink.objects.create(
                transaction=transaction,
                code=promo_code,
                qr_code_data=qr_code_data,
                link_url=link_url,
                expires_at=transaction.expires_at
            )
            
            logger.info(f"Created promo link {promo_code} for transaction {transaction.id}")
            return promo_link
            
        except Exception as e:
            logger.error(f"Error creating promo link: {str(e)}")
            raise

    def claim_promo_link(self, promo_code, recipient_data, ip_address=None):
        """
        Claim a promo link and transfer funds
        
        Args:
            promo_code (str): Promo code to claim
            recipient_data (dict): Recipient information
            ip_address (str, optional): IP address of claimant
            
        Returns:
            dict: Claim result
        """
        try:
            # Get promo link
            promo_link = PromoLink.objects.select_related('transaction').get(
                code=promo_code
            )
            
            # Validate promo link
            validation_result = self._validate_promo_link(promo_link)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'message': validation_result['message'],
                    'error_code': validation_result['error_code']
                }
            
            # Process the claim
            claim_result = self._process_claim(promo_link, recipient_data, ip_address)
            
            if claim_result['success']:
                # Mark promo link as used
                promo_link.mark_as_used(ip_address, recipient_data)
                
                # Update transaction status
                transaction = promo_link.transaction
                if transaction.status == 'completed':
                    transaction.status = 'claimed'
                    transaction.save()
                
                logger.info(f"Promo link {promo_code} claimed successfully")
            
            return claim_result
            
        except PromoLink.DoesNotExist:
            return {
                'success': False,
                'message': 'Promo code not found',
                'error_code': 'PROMO_NOT_FOUND'
            }
        except Exception as e:
            logger.error(f"Error claiming promo link {promo_code}: {str(e)}")
            return {
                'success': False,
                'message': 'An error occurred while processing your claim',
                'error_code': 'CLAIM_ERROR'
            }

    def get_promo_link_info(self, promo_code):
        """
        Get information about a promo link without claiming it
        
        Args:
            promo_code (str): Promo code to check
            
        Returns:
            dict: Promo link information
        """
        try:
            promo_link = PromoLink.objects.select_related('transaction').get(
                code=promo_code
            )
            
            validation_result = self._validate_promo_link(promo_link)
            
            return {
                'valid': validation_result['valid'],
                'promo_code': promo_code,
                'amount': promo_link.transaction.net_amount,
                'currency': promo_link.transaction.converted_currency.code,
                'is_used': promo_link.is_used,
                'is_expired': promo_link.is_expired,
                'expires_at': promo_link.expires_at.isoformat(),
                'time_remaining': str(promo_link.transaction.time_remaining),
                'message': validation_result['message']
            }
            
        except PromoLink.DoesNotExist:
            return {
                'valid': False,
                'message': 'Promo code not found',
                'error_code': 'PROMO_NOT_FOUND'
            }

    def expire_old_promo_links(self):
        """Expire promo links that have exceeded their expiry time"""
        expired_count = 0
        
        expired_links = PromoLink.objects.filter(
            is_used=False,
            expires_at__lt=timezone.now()
        )
        
        for promo_link in expired_links:
            # Don't actually delete, just let the is_expired property handle it
            # But we could mark transactions as expired here
            transaction = promo_link.transaction
            if transaction.status in ['pending', 'completed']:
                transaction.status = 'expired'
                transaction.save()
            
            expired_count += 1
        
        logger.info(f"Processed {expired_count} expired promo links")
        return expired_count

    def get_promo_link_statistics(self, days=30):
        """Get promo link usage statistics"""
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Q
        
        start_date = timezone.now() - timedelta(days=days)
        
        total_links = PromoLink.objects.filter(created_at__gte=start_date).count()
        used_links = PromoLink.objects.filter(
            created_at__gte=start_date,
            is_used=True
        ).count()
        expired_links = PromoLink.objects.filter(
            created_at__gte=start_date,
            expires_at__lt=timezone.now(),
            is_used=False
        ).count()
        
        return {
            'period_days': days,
            'total_created': total_links,
            'total_used': used_links,
            'total_expired': expired_links,
            'usage_rate': (used_links / total_links * 100) if total_links > 0 else 0,
            'active_links': total_links - used_links - expired_links
        }

    def _generate_promo_code(self):
        """Generate a random promo code"""
        # Use alphanumeric characters excluding confusing ones
        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('0', '').replace('O', '').replace('1', '').replace('I')
        
        return ''.join(secrets.choice(chars) for _ in range(self.code_length))

    def _build_promo_url(self, promo_code):
        """Build full URL for promo link"""
        # This would be the frontend URL where users claim promo codes
        # For now, we'll use a placeholder
        base_url = getattr(settings, 'FRONTEND_URL', 'https://ucpg.com')
        return f"{base_url}/claim/{promo_code}"

    def _generate_qr_code(self, url):
        """Generate QR code for the promo URL"""
        try:
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_data = buffer.getvalue()
            buffer.close()
            
            # Encode as base64 string
            qr_code_b64 = base64.b64encode(img_data).decode('utf-8')
            return f"data:image/png;base64,{qr_code_b64}"
            
        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            return ""

    def _validate_promo_link(self, promo_link):
        """Validate if promo link can be used"""
        if promo_link.is_used:
            return {
                'valid': False,
                'message': 'This promo code has already been used',
                'error_code': 'ALREADY_USED'
            }
        
        if promo_link.is_expired:
            return {
                'valid': False,
                'message': 'This promo code has expired',
                'error_code': 'EXPIRED'
            }
        
        # Check if underlying transaction is valid
        transaction = promo_link.transaction
        if transaction.status not in ['completed', 'pending']:
            return {
                'valid': False,
                'message': 'This promo code is no longer valid',
                'error_code': 'INVALID_TRANSACTION'
            }
        
        return {
            'valid': True,
            'message': 'Promo code is valid and ready to claim'
        }

    def _process_claim(self, promo_link, recipient_data, ip_address=None):
        """Process the actual claiming of funds"""
        try:
            transaction = promo_link.transaction
            
            # Validate recipient data
            if not self._validate_recipient_data(recipient_data):
                return {
                    'success': False,
                    'message': 'Invalid recipient information provided',
                    'error_code': 'INVALID_RECIPIENT_DATA'
                }
            
            # In a real implementation, this would:
            # 1. Transfer crypto to recipient wallet
            # 2. Or process fiat transfer to recipient account
            # 3. Handle different payout methods
            
            # For now, we'll simulate successful processing
            payout_result = self._simulate_payout(transaction, recipient_data)
            
            if payout_result['success']:
                return {
                    'success': True,
                    'message': 'Funds claimed successfully',
                    'amount': transaction.net_amount,
                    'currency': transaction.converted_currency.code,
                    'transaction_id': str(transaction.id),
                    'payout_reference': payout_result.get('reference', ''),
                    'estimated_delivery': payout_result.get('estimated_delivery', '')
                }
            else:
                return {
                    'success': False,
                    'message': payout_result.get('message', 'Payout processing failed'),
                    'error_code': 'PAYOUT_FAILED'
                }
                
        except Exception as e:
            logger.error(f"Error processing claim: {str(e)}")
            return {
                'success': False,
                'message': 'An error occurred during payout processing',
                'error_code': 'PROCESSING_ERROR'
            }

    def _validate_recipient_data(self, recipient_data):
        """Validate recipient data"""
        if not recipient_data:
            return False
        
        # Must have at least one contact method or wallet
        has_contact = bool(
            recipient_data.get('email') or 
            recipient_data.get('telegram') or 
            recipient_data.get('wallet')
        )
        
        return has_contact

    def _simulate_payout(self, transaction, recipient_data):
        """Simulate payout processing (replace with real implementation)"""
        try:
            # This would integrate with actual payment processors
            # For different payout methods:
            
            if recipient_data.get('wallet'):
                # Crypto payout
                return {
                    'success': True,
                    'reference': f"crypto_payout_{transaction.id}",
                    'estimated_delivery': '10-30 minutes'
                }
            elif recipient_data.get('email'):
                # Email-based payout (e.g., PayPal)
                return {
                    'success': True,
                    'reference': f"email_payout_{transaction.id}",
                    'estimated_delivery': '1-2 business days'
                }
            else:
                # Other payout method
                return {
                    'success': True,
                    'reference': f"payout_{transaction.id}",
                    'estimated_delivery': '1-3 business days'
                }
                
        except Exception as e:
            logger.error(f"Payout simulation error: {str(e)}")
            return {
                'success': False,
                'message': f"Payout processing failed: {str(e)}"
            }
