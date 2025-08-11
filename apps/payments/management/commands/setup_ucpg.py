from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from apps.payments.models import Currency, CommissionSetting
from apps.providers.models import Provider


class Command(BaseCommand):
    help = 'Setup initial UCPG data (currencies, commission settings, etc.)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing data before setup',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up UCPG initial data...'))
        
        if options['reset']:
            self.stdout.write('Resetting existing data...')
            self._reset_data()
        
        with transaction.atomic():
            self._create_currencies()
            self._create_commission_settings()
            self._create_sample_provider()
        
        self.stdout.write(self.style.SUCCESS('UCPG setup completed successfully!'))

    def _reset_data(self):
        """Reset existing data"""
        Currency.objects.all().delete()
        CommissionSetting.objects.all().delete()
        Provider.objects.all().delete()
        self.stdout.write('Existing data reset.')

    def _create_currencies(self):
        """Create supported currencies"""
        currencies = [
            # Fiat currencies
            {'code': 'USD', 'name': 'US Dollar', 'symbol': '$', 'is_crypto': False, 'decimal_places': 2},
            {'code': 'EUR', 'name': 'Euro', 'symbol': '€', 'is_crypto': False, 'decimal_places': 2},
            {'code': 'GBP', 'name': 'British Pound', 'symbol': '£', 'is_crypto': False, 'decimal_places': 2},
            {'code': 'JPY', 'name': 'Japanese Yen', 'symbol': '¥', 'is_crypto': False, 'decimal_places': 0},
            {'code': 'UZS', 'name': 'Uzbek Som', 'symbol': 'сўм', 'is_crypto': False, 'decimal_places': 2},
            {'code': 'KZT', 'name': 'Kazakhstani Tenge', 'symbol': '₸', 'is_crypto': False, 'decimal_places': 2},
            {'code': 'RUB', 'name': 'Russian Ruble', 'symbol': '₽', 'is_crypto': False, 'decimal_places': 2},
            
            # Cryptocurrencies
            {'code': 'BTC', 'name': 'Bitcoin', 'symbol': '₿', 'is_crypto': True, 'decimal_places': 8},
            {'code': 'ETH', 'name': 'Ethereum', 'symbol': 'Ξ', 'is_crypto': True, 'decimal_places': 8},
            {'code': 'USDT', 'name': 'Tether USD', 'symbol': '₮', 'is_crypto': True, 'decimal_places': 6},
            {'code': 'USDC', 'name': 'USD Coin', 'symbol': 'USDC', 'is_crypto': True, 'decimal_places': 6},
            {'code': 'BNB', 'name': 'Binance Coin', 'symbol': 'BNB', 'is_crypto': True, 'decimal_places': 8},
            {'code': 'ADA', 'name': 'Cardano', 'symbol': 'ADA', 'is_crypto': True, 'decimal_places': 6},
            {'code': 'DOT', 'name': 'Polkadot', 'symbol': 'DOT', 'is_crypto': True, 'decimal_places': 8},
        ]
        
        created_count = 0
        for curr_data in currencies:
            currency, created = Currency.objects.get_or_create(
                code=curr_data['code'],
                defaults=curr_data
            )
            if created:
                created_count += 1
                self.stdout.write(f'Created currency: {currency.code} - {currency.name}')
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} currencies'))

    def _create_commission_settings(self):
        """Create default commission settings"""
        # Global default commission
        global_commission, created = CommissionSetting.objects.get_or_create(
            is_global=True,
            defaults={
                'rate': Decimal('0.05'),  # 5%
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write('Created global commission setting: 5%')
        
        # Currency-specific commissions (optional examples)
        currency_commissions = [
            {'currency_code': 'BTC', 'rate': Decimal('0.01')},  # 1% for Bitcoin
            {'currency_code': 'USDT', 'rate': Decimal('0.03')}, # 3% for USDT
            {'currency_code': 'USD', 'rate': Decimal('0.04')},  # 4% for USD
        ]
        
        created_count = 0
        for comm_data in currency_commissions:
            try:
                currency = Currency.objects.get(code=comm_data['currency_code'])
                setting, created = CommissionSetting.objects.get_or_create(
                    currency=currency,
                    provider=None,
                    defaults={
                        'rate': comm_data['rate'],
                        'is_active': True,
                        'is_global': False
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'Created {currency.code} commission: {comm_data["rate"] * 100}%')
            except Currency.DoesNotExist:
                self.stdout.write(f'Warning: Currency {comm_data["currency_code"]} not found')
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} currency-specific commission settings'))

    def _create_sample_provider(self):
        """Create a sample provider for testing"""
        provider_data = {
            'name': 'Sample VPN Service',
            'slug': 'sample-vpn',
            'description': 'A sample VPN service provider for testing UCPG integration',
            'provider_type': 'vpn',
            'webhook_url': 'https://sample-vpn.com/webhooks/ucpg',
            'redirect_url': 'https://sample-vpn.com/success',
            'commission_rate': Decimal('0.02'),  # 2%
            'contact_email': 'integration@sample-vpn.com',
            'contact_person': 'John Doe',
            'website_url': 'https://sample-vpn.com',
            'is_active': True,
            'is_verified': True,
            'min_transaction_amount': Decimal('5.00'),
            'max_transaction_amount': Decimal('500.00'),
            'daily_transaction_limit': Decimal('10000.00')
        }
        
        provider, created = Provider.objects.get_or_create(
            slug='sample-vpn',
            defaults=provider_data
        )
        
        if created:
            # Generate API key
            provider.generate_api_key()
            provider.save()
            
            self.stdout.write(f'Created sample provider: {provider.name}')
            self.stdout.write(f'Provider API Key: {provider.api_key}')
            
            # Create provider-specific commission
            CommissionSetting.objects.get_or_create(
                provider=provider,
                currency=None,
                defaults={
                    'rate': provider.commission_rate,
                    'is_active': True,
                    'is_global': False
                }
            )
        else:
            self.stdout.write(f'Sample provider already exists: {provider.name}')
        
        self.stdout.write(self.style.SUCCESS('Sample provider setup completed'))
