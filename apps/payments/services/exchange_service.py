import logging
import requests
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from ..models import Currency, ExchangeRate

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """Service for handling currency exchange rates"""
    
    def __init__(self):
        self.binance_api_url = settings.BINANCE_API_URL
        self.coingecko_api_url = settings.COINGECKO_API_URL
        self.coingecko_api_key = settings.COINGECKO_API_KEY
        self.cache_timeout = settings.UCPG_SETTINGS['EXCHANGE_RATE_CACHE_TIMEOUT']

    def get_exchange_rate(self, from_currency, to_currency):
        """
        Get exchange rate between two currencies
        
        Args:
            from_currency (Currency): Source currency
            to_currency (Currency): Target currency
            
        Returns:
            Decimal: Exchange rate
        """
        if from_currency.code == to_currency.code:
            return Decimal('1.0')
        
        cache_key = f"exchange_rate_{from_currency.code}_{to_currency.code}"
        cached_rate = cache.get(cache_key)
        
        if cached_rate:
            return Decimal(str(cached_rate))
        
        # Try to get rate from database (recent)
        recent_rate = ExchangeRate.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency,
            timestamp__gte=timezone.now() - timedelta(minutes=10)
        ).first()
        
        if recent_rate:
            cache.set(cache_key, str(recent_rate.rate), self.cache_timeout)
            return recent_rate.rate
        
        # Fetch fresh rate from APIs
        rate = self._fetch_rate_from_apis(from_currency, to_currency)
        
        if rate:
            # Store in database
            ExchangeRate.objects.create(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
                source='api_fetch'
            )
            
            # Cache the rate
            cache.set(cache_key, str(rate), self.cache_timeout)
            return rate
        
        raise ValueError(f"Could not get exchange rate for {from_currency.code} to {to_currency.code}")

    def convert_currency(self, amount, from_currency, to_currency):
        """
        Convert amount from one currency to another
        
        Args:
            amount (Decimal): Amount to convert
            from_currency (Currency): Source currency
            to_currency (Currency): Target currency
            
        Returns:
            dict: Conversion result
        """
        rate = self.get_exchange_rate(from_currency, to_currency)
        converted_amount = amount * rate
        
        return {
            'original_amount': amount,
            'original_currency': from_currency.code,
            'converted_amount': converted_amount,
            'converted_currency': to_currency.code,
            'exchange_rate': rate,
            'timestamp': timezone.now().isoformat()
        }

    def update_all_rates(self):
        """Update exchange rates for all active currency pairs"""
        active_currencies = Currency.objects.filter(is_active=True)
        updated_count = 0
        
        for from_currency in active_currencies:
            for to_currency in active_currencies:
                if from_currency.code != to_currency.code:
                    try:
                        rate = self._fetch_rate_from_apis(from_currency, to_currency)
                        if rate:
                            ExchangeRate.objects.create(
                                from_currency=from_currency,
                                to_currency=to_currency,
                                rate=rate,
                                source='scheduled_update'
                            )
                            updated_count += 1
                    except Exception as e:
                        logger.error(f"Failed to update rate {from_currency.code} -> {to_currency.code}: {str(e)}")
        
        logger.info(f"Updated {updated_count} exchange rates")
        return updated_count

    def get_supported_currencies(self):
        """Get list of all supported currencies"""
        currencies = Currency.objects.filter(is_active=True).order_by('code')
        
        return [
            {
                'code': currency.code,
                'name': currency.name,
                'symbol': currency.symbol,
                'is_crypto': currency.is_crypto,
                'decimal_places': currency.decimal_places
            }
            for currency in currencies
        ]

    def get_rate_history(self, from_currency, to_currency, days=30):
        """Get historical exchange rates"""
        start_date = timezone.now() - timedelta(days=days)
        
        rates = ExchangeRate.objects.filter(
            from_currency__code=from_currency,
            to_currency__code=to_currency,
            timestamp__gte=start_date
        ).order_by('timestamp')
        
        return [
            {
                'rate': rate.rate,
                'timestamp': rate.timestamp.isoformat(),
                'source': rate.source
            }
            for rate in rates
        ]

    def _fetch_rate_from_apis(self, from_currency, to_currency):
        """Fetch exchange rate from external APIs"""
        
        # Try Binance first for crypto pairs
        if from_currency.is_crypto or to_currency.is_crypto:
            rate = self._fetch_binance_rate(from_currency, to_currency)
            if rate:
                return rate
        
        # Try CoinGecko for any pair
        rate = self._fetch_coingecko_rate(from_currency, to_currency)
        if rate:
            return rate
        
        # For fiat-to-fiat, could add more providers here
        logger.warning(f"Could not fetch rate for {from_currency.code} -> {to_currency.code}")
        return None

    def _fetch_binance_rate(self, from_currency, to_currency):
        """Fetch rate from Binance API"""
        try:
            # Binance uses symbol pairs like BTCUSDT
            symbol = f"{from_currency.code}{to_currency.code}"
            
            url = f"{self.binance_api_url}/ticker/price"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                rate = Decimal(str(data['price']))
                logger.info(f"Fetched Binance rate {symbol}: {rate}")
                return rate
            else:
                # Try reverse pair
                reverse_symbol = f"{to_currency.code}{from_currency.code}"
                params = {'symbol': reverse_symbol}
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    reverse_rate = Decimal(str(data['price']))
                    rate = Decimal('1') / reverse_rate
                    logger.info(f"Fetched Binance reverse rate {reverse_symbol}: {rate}")
                    return rate
                
        except Exception as e:
            logger.error(f"Binance API error for {from_currency.code}->{to_currency.code}: {str(e)}")
        
        return None

    def _fetch_coingecko_rate(self, from_currency, to_currency):
        """Fetch rate from CoinGecko API"""
        try:
            # CoinGecko uses different currency mappings
            from_id = self._get_coingecko_id(from_currency.code)
            to_id = self._get_coingecko_id(to_currency.code)
            
            if not from_id or not to_id:
                return None
            
            url = f"{self.coingecko_api_url}/simple/price"
            params = {
                'ids': from_id,
                'vs_currencies': to_id
            }
            
            if self.coingecko_api_key:
                params['x_cg_demo_api_key'] = self.coingecko_api_key
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if from_id in data and to_id in data[from_id]:
                    rate = Decimal(str(data[from_id][to_id]))
                    logger.info(f"Fetched CoinGecko rate {from_currency.code}->{to_currency.code}: {rate}")
                    return rate
                
        except Exception as e:
            logger.error(f"CoinGecko API error for {from_currency.code}->{to_currency.code}: {str(e)}")
        
        return None

    def _get_coingecko_id(self, currency_code):
        """Map currency code to CoinGecko ID"""
        mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether',
            'USDC': 'usd-coin',
            'BNB': 'binancecoin',
            'ADA': 'cardano',
            'DOT': 'polkadot',
            'USD': 'usd',
            'EUR': 'eur',
            'GBP': 'gbp',
            'JPY': 'jpy',
            'KZT': 'kzt',
            'UZS': 'uzs'
        }
        
        return mapping.get(currency_code.upper())

    def cleanup_old_rates(self, days_to_keep=30):
        """Clean up old exchange rate records"""
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        deleted_count = ExchangeRate.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old exchange rate records")
        return deleted_count
