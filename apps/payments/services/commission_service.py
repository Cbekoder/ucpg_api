import logging
from decimal import Decimal
from django.conf import settings

from ..models import CommissionSetting, Currency
from apps.providers.models import Provider

logger = logging.getLogger(__name__)


class CommissionService:
    """Service for handling commission calculations"""
    
    def __init__(self):
        self.default_rate = Decimal(str(settings.UCPG_SETTINGS['DEFAULT_COMMISSION_RATE']))
        self.max_rate = Decimal(str(settings.UCPG_SETTINGS['MAX_COMMISSION_RATE']))

    def calculate_commission(self, amount, currency, provider_id=None):
        """
        Calculate commission for a transaction
        
        Args:
            amount (Decimal): Transaction amount
            currency (Currency): Currency object
            provider_id (str, optional): Provider UUID
            
        Returns:
            dict: Commission calculation result
        """
        try:
            # Get applicable commission rate
            commission_rate = self._get_commission_rate(currency, provider_id)
            
            # Calculate commission amount
            commission_amount = amount * commission_rate
            
            # Calculate net amount (after commission)
            net_amount = amount - commission_amount
            
            return {
                'rate': commission_rate,
                'amount': commission_amount,
                'net_amount': net_amount,
                'original_amount': amount,
                'currency': currency.code
            }
            
        except Exception as e:
            logger.error(f"Error calculating commission: {str(e)}")
            raise

    def _get_commission_rate(self, currency, provider_id=None):
        """
        Get applicable commission rate based on priority:
        1. Provider + Currency specific
        2. Provider specific
        3. Currency specific
        4. Global setting
        5. Default fallback
        """
        provider = None
        if provider_id:
            try:
                provider = Provider.objects.get(id=provider_id, is_active=True)
            except Provider.DoesNotExist:
                logger.warning(f"Provider {provider_id} not found or inactive")
        
        # Try provider + currency specific rate
        if provider and currency:
            setting = CommissionSetting.objects.filter(
                provider=provider,
                currency=currency,
                is_active=True
            ).first()
            
            if setting:
                logger.info(f"Using provider+currency rate: {setting.rate}")
                return setting.rate
        
        # Try provider specific rate
        if provider:
            setting = CommissionSetting.objects.filter(
                provider=provider,
                currency__isnull=True,
                is_active=True
            ).first()
            
            if setting:
                logger.info(f"Using provider rate: {setting.rate}")
                return setting.rate
            
            # Use provider's default rate
            if provider.commission_rate:
                logger.info(f"Using provider default rate: {provider.commission_rate}")
                return provider.commission_rate
        
        # Try currency specific rate
        if currency:
            setting = CommissionSetting.objects.filter(
                currency=currency,
                provider__isnull=True,
                is_active=True
            ).first()
            
            if setting:
                logger.info(f"Using currency rate: {setting.rate}")
                return setting.rate
        
        # Try global setting
        global_setting = CommissionSetting.objects.filter(
            is_global=True,
            is_active=True
        ).first()
        
        if global_setting:
            logger.info(f"Using global rate: {global_setting.rate}")
            return global_setting.rate
        
        # Fallback to default
        logger.info(f"Using default rate: {self.default_rate}")
        return self.default_rate

    def get_commission_settings(self):
        """Get all commission settings"""
        settings_list = CommissionSetting.objects.filter(is_active=True).order_by(
            '-is_global', 'currency__code', 'provider__name'
        )
        
        return [
            {
                'id': setting.id,
                'type': self._get_setting_type(setting),
                'currency': setting.currency.code if setting.currency else None,
                'provider': setting.provider.name if setting.provider else None,
                'rate': setting.rate,
                'rate_percentage': setting.rate * 100,
                'is_global': setting.is_global,
                'created_at': setting.created_at.isoformat(),
                'updated_at': setting.updated_at.isoformat()
            }
            for setting in settings_list
        ]

    def update_commission_setting(self, setting_data):
        """
        Update or create commission setting
        
        Args:
            setting_data (dict): {
                'id': int (optional, for updates),
                'currency_code': str (optional),
                'provider_id': str (optional),
                'rate': float,
                'is_global': bool (optional)
            }
            
        Returns:
            dict: Updated setting data
        """
        try:
            rate = Decimal(str(setting_data['rate']))
            
            # Validate rate
            if rate < 0 or rate > self.max_rate:
                raise ValueError(f"Rate must be between 0 and {self.max_rate}")
            
            # Get related objects
            currency = None
            if setting_data.get('currency_code'):
                try:
                    currency = Currency.objects.get(
                        code=setting_data['currency_code'].upper(),
                        is_active=True
                    )
                except Currency.DoesNotExist:
                    raise ValueError(f"Currency {setting_data['currency_code']} not found")
            
            provider = None
            if setting_data.get('provider_id'):
                try:
                    provider = Provider.objects.get(
                        id=setting_data['provider_id'],
                        is_active=True
                    )
                except Provider.DoesNotExist:
                    raise ValueError(f"Provider {setting_data['provider_id']} not found")
            
            # Update or create setting
            if setting_data.get('id'):
                # Update existing
                setting = CommissionSetting.objects.get(id=setting_data['id'])
                setting.rate = rate
                setting.currency = currency
                setting.provider = provider
                setting.is_global = setting_data.get('is_global', False)
                setting.save()
            else:
                # Create new
                setting = CommissionSetting.objects.create(
                    rate=rate,
                    currency=currency,
                    provider=provider,
                    is_global=setting_data.get('is_global', False)
                )
            
            return {
                'id': setting.id,
                'rate': setting.rate,
                'rate_percentage': setting.rate * 100,
                'currency': setting.currency.code if setting.currency else None,
                'provider': setting.provider.name if setting.provider else None,
                'is_global': setting.is_global,
                'type': self._get_setting_type(setting)
            }
            
        except CommissionSetting.DoesNotExist:
            raise ValueError(f"Commission setting {setting_data['id']} not found")
        except Exception as e:
            logger.error(f"Error updating commission setting: {str(e)}")
            raise

    def delete_commission_setting(self, setting_id):
        """Delete commission setting"""
        try:
            setting = CommissionSetting.objects.get(id=setting_id)
            setting.delete()
            return True
        except CommissionSetting.DoesNotExist:
            raise ValueError(f"Commission setting {setting_id} not found")

    def test_commission_calculation(self, test_data):
        """
        Test commission calculation with given parameters
        
        Args:
            test_data (dict): {
                'amount': float,
                'currency_code': str,
                'provider_id': str (optional)
            }
            
        Returns:
            dict: Test calculation result
        """
        try:
            amount = Decimal(str(test_data['amount']))
            currency = Currency.objects.get(
                code=test_data['currency_code'].upper(),
                is_active=True
            )
            
            result = self.calculate_commission(
                amount=amount,
                currency=currency,
                provider_id=test_data.get('provider_id')
            )
            
            # Add additional info for testing
            result.update({
                'rate_source': self._get_rate_source(currency, test_data.get('provider_id')),
                'rate_percentage': result['rate'] * 100
            })
            
            return result
            
        except Currency.DoesNotExist:
            raise ValueError(f"Currency {test_data['currency_code']} not found")
        except Exception as e:
            logger.error(f"Error in test calculation: {str(e)}")
            raise

    def get_commission_statistics(self, days=30):
        """Get commission statistics for the last N days"""
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum, Count
        from ..models import Transaction
        
        start_date = timezone.now() - timedelta(days=days)
        
        transactions = Transaction.objects.filter(
            status='completed',
            completed_at__gte=start_date
        )
        
        stats = transactions.aggregate(
            total_transactions=Count('id'),
            total_commission=Sum('commission_amount'),
            total_volume=Sum('original_amount')
        )
        
        # Commission by currency
        currency_stats = transactions.values(
            'converted_currency__code'
        ).annotate(
            count=Count('id'),
            commission=Sum('commission_amount'),
            volume=Sum('converted_amount')
        )
        
        # Commission by provider
        provider_stats = transactions.filter(
            provider__isnull=False
        ).values(
            'provider__name'
        ).annotate(
            count=Count('id'),
            commission=Sum('commission_amount'),
            volume=Sum('converted_amount')
        )
        
        return {
            'period_days': days,
            'total_transactions': stats['total_transactions'] or 0,
            'total_commission': stats['total_commission'] or Decimal('0'),
            'total_volume': stats['total_volume'] or Decimal('0'),
            'average_commission_rate': (
                (stats['total_commission'] / stats['total_volume']) 
                if stats['total_volume'] else Decimal('0')
            ),
            'by_currency': list(currency_stats),
            'by_provider': list(provider_stats)
        }

    def _get_setting_type(self, setting):
        """Get human-readable setting type"""
        if setting.is_global:
            return 'Global'
        elif setting.currency and setting.provider:
            return f'{setting.currency.code} + {setting.provider.name}'
        elif setting.currency:
            return f'{setting.currency.code} Currency'
        elif setting.provider:
            return f'{setting.provider.name} Provider'
        else:
            return 'Unknown'

    def _get_rate_source(self, currency, provider_id=None):
        """Get description of which rate source was used"""
        provider = None
        if provider_id:
            try:
                provider = Provider.objects.get(id=provider_id)
            except Provider.DoesNotExist:
                pass
        
        if provider and currency:
            if CommissionSetting.objects.filter(
                provider=provider, currency=currency, is_active=True
            ).exists():
                return f"Provider + Currency ({provider.name} + {currency.code})"
        
        if provider:
            if CommissionSetting.objects.filter(
                provider=provider, currency__isnull=True, is_active=True
            ).exists():
                return f"Provider ({provider.name})"
            if provider.commission_rate:
                return f"Provider Default ({provider.name})"
        
        if currency:
            if CommissionSetting.objects.filter(
                currency=currency, provider__isnull=True, is_active=True
            ).exists():
                return f"Currency ({currency.code})"
        
        if CommissionSetting.objects.filter(is_global=True, is_active=True).exists():
            return "Global Setting"
        
        return "System Default"
