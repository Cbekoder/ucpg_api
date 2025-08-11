import logging
import requests
import hashlib
import secrets
from decimal import Decimal
from typing import Dict, Optional
from django.conf import settings
from django.utils import timezone

from ..models import Transaction, EscrowAccount, PayoutRequest, Currency

logger = logging.getLogger(__name__)


class CryptoWalletService:
    """Service for handling cryptocurrency transactions"""
    
    def __init__(self):
        self.btc_node_url = getattr(settings, 'BTC_NODE_URL', '')
        self.eth_node_url = getattr(settings, 'ETH_NODE_URL', '')
        self.usdt_contract_address = getattr(settings, 'USDT_CONTRACT_ADDRESS', '')
        self.master_wallet_address = getattr(settings, 'MASTER_WALLET_ADDRESS', '')
        self.master_wallet_private_key = getattr(settings, 'MASTER_WALLET_PRIVATE_KEY', '')
    
    def generate_deposit_address(self, transaction: Transaction) -> Dict:
        """
        Generate a unique deposit address for crypto payment
        
        Args:
            transaction: Transaction object
            
        Returns:
            dict: Deposit address details
        """
        try:
            currency_code = transaction.original_currency.code
            
            if currency_code == 'BTC':
                return self._generate_btc_address(transaction)
            elif currency_code in ['ETH', 'USDT', 'USDC']:
                return self._generate_eth_address(transaction)
            else:
                return {
                    'success': False,
                    'error': f'Cryptocurrency {currency_code} not supported'
                }
                
        except Exception as e:
            logger.error(f"Error generating deposit address: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_deposit_confirmation(self, transaction: Transaction) -> Dict:
        """
        Check if crypto deposit has been confirmed
        
        Args:
            transaction: Transaction object
            
        Returns:
            dict: Confirmation status
        """
        try:
            if not transaction.crypto_deposit_address:
                return {
                    'success': False,
                    'error': 'No deposit address found'
                }
            
            currency_code = transaction.original_currency.code
            
            if currency_code == 'BTC':
                return self._check_btc_deposit(transaction)
            elif currency_code in ['ETH', 'USDT', 'USDC']:
                return self._check_eth_deposit(transaction)
            else:
                return {
                    'success': False,
                    'error': f'Cryptocurrency {currency_code} not supported'
                }
                
        except Exception as e:
            logger.error(f"Error checking deposit confirmation: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_crypto_payout(self, payout_request: PayoutRequest) -> Dict:
        """
        Create cryptocurrency payout to recipient's wallet
        
        Args:
            payout_request: PayoutRequest object
            
        Returns:
            dict: Payout result
        """
        try:
            if not payout_request.recipient_crypto_address:
                return {
                    'success': False,
                    'error': 'No recipient crypto address provided'
                }
            
            currency_code = payout_request.payout_currency.code
            
            if currency_code == 'BTC':
                return self._create_btc_payout(payout_request)
            elif currency_code in ['ETH', 'USDT', 'USDC']:
                return self._create_eth_payout(payout_request)
            else:
                return {
                    'success': False,
                    'error': f'Cryptocurrency {currency_code} not supported for payout'
                }
                
        except Exception as e:
            logger.error(f"Error creating crypto payout: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_wallet_balance(self, currency_code: str, address: str) -> Dict:
        """
        Get wallet balance for specific address
        
        Args:
            currency_code: Currency code (BTC, ETH, etc.)
            address: Wallet address
            
        Returns:
            dict: Balance information
        """
        try:
            if currency_code == 'BTC':
                return self._get_btc_balance(address)
            elif currency_code in ['ETH', 'USDT', 'USDC']:
                return self._get_eth_balance(address, currency_code)
            else:
                return {
                    'success': False,
                    'error': f'Currency {currency_code} not supported'
                }
                
        except Exception as e:
            logger.error(f"Error getting wallet balance: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_crypto_address(self, address: str, currency_code: str) -> bool:
        """
        Validate cryptocurrency address format
        
        Args:
            address: Crypto address to validate
            currency_code: Currency code
            
        Returns:
            bool: True if valid
        """
        try:
            if currency_code == 'BTC':
                return self._validate_btc_address(address)
            elif currency_code in ['ETH', 'USDT', 'USDC']:
                return self._validate_eth_address(address)
            else:
                return False
                
        except Exception:
            return False
    
    def _generate_btc_address(self, transaction: Transaction) -> Dict:
        """Generate Bitcoin deposit address"""
        try:
            # In production, you'd use a proper HD wallet or Bitcoin Core RPC
            # This is a simplified implementation using deterministic generation
            
            # Generate deterministic address based on transaction ID
            seed = f"{transaction.id}{settings.SECRET_KEY}".encode()
            private_key = hashlib.sha256(seed).hexdigest()
            
            # This is a mock address generation - use proper Bitcoin libraries in production
            address_hash = hashlib.sha256(f"btc_{private_key}".encode()).hexdigest()[:34]
            deposit_address = f"bc1q{address_hash}"
            
            # Store address in transaction
            transaction.crypto_deposit_address = deposit_address
            transaction.payment_method = 'crypto_deposit'
            transaction.status = 'payment_processing'
            transaction.save()
            
            logger.info(f"Generated BTC deposit address {deposit_address} for transaction {transaction.id}")
            
            return {
                'success': True,
                'address': deposit_address,
                'currency': 'BTC',
                'amount': transaction.original_amount,
                'qr_code': self._generate_payment_qr(deposit_address, transaction.original_amount, 'BTC')
            }
            
        except Exception as e:
            logger.error(f"Error generating BTC address: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_eth_address(self, transaction: Transaction) -> Dict:
        """Generate Ethereum/ERC-20 deposit address"""
        try:
            # Generate deterministic Ethereum address
            seed = f"{transaction.id}{settings.SECRET_KEY}".encode()
            private_key = hashlib.sha256(seed).hexdigest()
            
            # Mock Ethereum address generation
            address_hash = hashlib.sha256(f"eth_{private_key}".encode()).hexdigest()[:40]
            deposit_address = f"0x{address_hash}"
            
            transaction.crypto_deposit_address = deposit_address
            transaction.payment_method = 'crypto_deposit'
            transaction.status = 'payment_processing'
            transaction.save()
            
            currency_code = transaction.original_currency.code
            logger.info(f"Generated {currency_code} deposit address {deposit_address} for transaction {transaction.id}")
            
            return {
                'success': True,
                'address': deposit_address,
                'currency': currency_code,
                'amount': transaction.original_amount,
                'contract_address': self.usdt_contract_address if currency_code in ['USDT', 'USDC'] else None,
                'qr_code': self._generate_payment_qr(deposit_address, transaction.original_amount, currency_code)
            }
            
        except Exception as e:
            logger.error(f"Error generating ETH address: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _check_btc_deposit(self, transaction: Transaction) -> Dict:
        """Check Bitcoin deposit confirmation"""
        try:
            # In production, use Bitcoin Core RPC or blockchain explorer API
            # This is a mock implementation
            
            address = transaction.crypto_deposit_address
            expected_amount = transaction.original_amount
            
            # Mock API call to check Bitcoin address
            # In reality, you'd call something like:
            # response = requests.get(f'https://blockstream.info/api/address/{address}')
            
            # For demo purposes, we'll simulate a confirmed transaction after some time
            time_elapsed = (timezone.now() - transaction.created_at).total_seconds()
            
            if time_elapsed > 300:  # 5 minutes for demo
                # Simulate confirmed transaction
                mock_tx_hash = hashlib.sha256(f"btc_tx_{transaction.id}".encode()).hexdigest()
                
                transaction.crypto_tx_hash = mock_tx_hash
                transaction.status = 'payment_confirmed'
                transaction.save()
                
                # Move to escrow
                self._move_crypto_to_escrow(transaction)
                
                return {
                    'success': True,
                    'confirmed': True,
                    'tx_hash': mock_tx_hash,
                    'confirmations': 6,  # Mock confirmations
                    'amount_received': expected_amount
                }
            else:
                return {
                    'success': True,
                    'confirmed': False,
                    'confirmations': 0,
                    'message': 'Waiting for payment confirmation'
                }
                
        except Exception as e:
            logger.error(f"Error checking BTC deposit: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _check_eth_deposit(self, transaction: Transaction) -> Dict:
        """Check Ethereum/ERC-20 deposit confirmation"""
        try:
            # Similar to BTC but for Ethereum network
            address = transaction.crypto_deposit_address
            expected_amount = transaction.original_amount
            currency_code = transaction.original_currency.code
            
            # Mock confirmation check
            time_elapsed = (timezone.now() - transaction.created_at).total_seconds()
            
            if time_elapsed > 180:  # 3 minutes for demo (ETH is faster)
                mock_tx_hash = hashlib.sha256(f"eth_tx_{transaction.id}".encode()).hexdigest()
                
                transaction.crypto_tx_hash = mock_tx_hash
                transaction.status = 'payment_confirmed'
                transaction.save()
                
                # Move to escrow
                self._move_crypto_to_escrow(transaction)
                
                return {
                    'success': True,
                    'confirmed': True,
                    'tx_hash': mock_tx_hash,
                    'confirmations': 12,  # Mock confirmations
                    'amount_received': expected_amount
                }
            else:
                return {
                    'success': True,
                    'confirmed': False,
                    'confirmations': 0,
                    'message': 'Waiting for payment confirmation'
                }
                
        except Exception as e:
            logger.error(f"Error checking ETH deposit: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_btc_payout(self, payout_request: PayoutRequest) -> Dict:
        """Create Bitcoin payout"""
        try:
            recipient_address = payout_request.recipient_crypto_address
            amount = payout_request.payout_amount
            
            # Validate recipient address
            if not self._validate_btc_address(recipient_address):
                return {
                    'success': False,
                    'error': 'Invalid Bitcoin address'
                }
            
            # In production, create actual Bitcoin transaction
            # Mock transaction creation
            mock_tx_hash = hashlib.sha256(f"btc_payout_{payout_request.id}".encode()).hexdigest()
            
            payout_request.external_payout_id = mock_tx_hash
            payout_request.status = 'processing'
            payout_request.processed_at = timezone.now()
            payout_request.save()
            
            # Simulate network fee
            network_fee = Decimal('0.0005')  # 0.0005 BTC
            payout_request.processing_fee = network_fee
            payout_request.save()
            
            logger.info(f"Created BTC payout {mock_tx_hash} for {amount} BTC")
            
            return {
                'success': True,
                'tx_hash': mock_tx_hash,
                'amount': amount,
                'network_fee': network_fee,
                'status': 'processing',
                'estimated_confirmation_time': '10-60 minutes'
            }
            
        except Exception as e:
            logger.error(f"Error creating BTC payout: {str(e)}")
            payout_request.status = 'failed'
            payout_request.failure_reason = str(e)
            payout_request.save()
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_eth_payout(self, payout_request: PayoutRequest) -> Dict:
        """Create Ethereum/ERC-20 payout"""
        try:
            recipient_address = payout_request.recipient_crypto_address
            amount = payout_request.payout_amount
            currency_code = payout_request.payout_currency.code
            
            # Validate recipient address
            if not self._validate_eth_address(recipient_address):
                return {
                    'success': False,
                    'error': 'Invalid Ethereum address'
                }
            
            # Mock transaction creation
            mock_tx_hash = hashlib.sha256(f"eth_payout_{payout_request.id}".encode()).hexdigest()
            
            payout_request.external_payout_id = mock_tx_hash
            payout_request.status = 'processing'
            payout_request.processed_at = timezone.now()
            payout_request.save()
            
            # Simulate gas fee
            if currency_code == 'ETH':
                gas_fee = Decimal('0.005')  # 0.005 ETH
            else:  # ERC-20 tokens
                gas_fee = Decimal('0.01')   # Higher gas for token transfers
            
            payout_request.processing_fee = gas_fee
            payout_request.save()
            
            logger.info(f"Created {currency_code} payout {mock_tx_hash} for {amount} {currency_code}")
            
            return {
                'success': True,
                'tx_hash': mock_tx_hash,
                'amount': amount,
                'gas_fee': gas_fee,
                'status': 'processing',
                'estimated_confirmation_time': '2-5 minutes'
            }
            
        except Exception as e:
            logger.error(f"Error creating ETH payout: {str(e)}")
            payout_request.status = 'failed'
            payout_request.failure_reason = str(e)
            payout_request.save()
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def _move_crypto_to_escrow(self, transaction: Transaction) -> Dict:
        """Move confirmed crypto funds to escrow"""
        try:
            currency = transaction.converted_currency
            escrow_account, created = EscrowAccount.objects.get_or_create(
                account_type='crypto',
                currency=currency,
                defaults={
                    'account_reference': f'crypto_escrow_{currency.code.lower()}',
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
            
            # Update transaction
            transaction.status = 'escrowed'
            transaction.escrow_account_id = str(escrow_account.id)
            transaction.escrow_amount = net_amount
            transaction.escrow_currency = currency.code
            transaction.save()
            
            logger.info(f"Moved {net_amount} {currency.code} to escrow for transaction {transaction.id}")
            
            return {
                'success': True,
                'escrow_account_id': str(escrow_account.id)
            }
            
        except Exception as e:
            logger.error(f"Error moving crypto to escrow: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_btc_address(self, address: str) -> bool:
        """Validate Bitcoin address format"""
        try:
            # Basic Bitcoin address validation
            if len(address) < 26 or len(address) > 62:
                return False
            
            # Check for valid Bitcoin address prefixes
            valid_prefixes = ['1', '3', 'bc1', 'tb1']  # Legacy, P2SH, Bech32, Testnet
            
            return any(address.startswith(prefix) for prefix in valid_prefixes)
            
        except Exception:
            return False
    
    def _validate_eth_address(self, address: str) -> bool:
        """Validate Ethereum address format"""
        try:
            # Basic Ethereum address validation
            if not address.startswith('0x'):
                return False
            
            if len(address) != 42:  # 0x + 40 hex characters
                return False
            
            # Check if all characters after 0x are valid hex
            hex_part = address[2:]
            try:
                int(hex_part, 16)
                return True
            except ValueError:
                return False
                
        except Exception:
            return False
    
    def _get_btc_balance(self, address: str) -> Dict:
        """Get Bitcoin balance for address"""
        try:
            # Mock balance check - in production use blockchain API
            return {
                'success': True,
                'balance': Decimal('0.0'),
                'unconfirmed_balance': Decimal('0.0')
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_eth_balance(self, address: str, currency_code: str) -> Dict:
        """Get Ethereum/ERC-20 balance for address"""
        try:
            # Mock balance check
            return {
                'success': True,
                'balance': Decimal('0.0'),
                'currency': currency_code
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_payment_qr(self, address: str, amount: Decimal, currency: str) -> str:
        """Generate QR code for crypto payment"""
        try:
            # Create payment URI
            if currency == 'BTC':
                payment_uri = f"bitcoin:{address}?amount={amount}"
            else:  # Ethereum-based
                payment_uri = f"ethereum:{address}?value={amount}"
            
            # Generate QR code (reuse existing QR generation logic)
            import qrcode
            import base64
            from io import BytesIO
            
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(payment_uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_data = buffer.getvalue()
            buffer.close()
            
            qr_code_b64 = base64.b64encode(img_data).decode('utf-8')
            return f"data:image/png;base64,{qr_code_b64}"
            
        except Exception as e:
            logger.error(f"Error generating payment QR: {str(e)}")
            return ""
