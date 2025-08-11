import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .services import ExchangeRateService, PaymentService, PromoLinkService

logger = logging.getLogger(__name__)


@shared_task
def update_exchange_rates():
    """
    Celery task to update exchange rates from external APIs
    Runs every 5 minutes
    """
    try:
        exchange_service = ExchangeRateService()
        updated_count = exchange_service.update_all_rates()
        
        logger.info(f"Exchange rate update task completed. Updated {updated_count} rates.")
        return {
            'success': True,
            'updated_count': updated_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating exchange rates: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def expire_old_transactions():
    """
    Celery task to expire old transactions and promo links
    Runs every hour
    """
    try:
        payment_service = PaymentService()
        promo_service = PromoLinkService()
        
        # Expire transactions
        expired_transactions = payment_service.expire_old_transactions()
        
        # Expire promo links
        expired_promos = promo_service.expire_old_promo_links()
        
        logger.info(f"Expiry task completed. Expired {expired_transactions} transactions and {expired_promos} promo links.")
        
        return {
            'success': True,
            'expired_transactions': expired_transactions,
            'expired_promo_links': expired_promos,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error expiring old items: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def cleanup_old_data():
    """
    Celery task to cleanup old data (exchange rates, logs, etc.)
    Runs daily
    """
    try:
        exchange_service = ExchangeRateService()
        
        # Cleanup old exchange rates (keep 30 days)
        cleaned_rates = exchange_service.cleanup_old_rates(days_to_keep=30)
        
        # Could add more cleanup tasks here:
        # - Old transaction logs
        # - Old API logs
        # - Expired promo links
        
        logger.info(f"Cleanup task completed. Cleaned {cleaned_rates} old exchange rates.")
        
        return {
            'success': True,
            'cleaned_rates': cleaned_rates,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up old data: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def send_provider_webhooks():
    """
    Celery task to send pending webhooks to providers
    Runs every 5 minutes
    """
    try:
        from apps.providers.models import ProviderWebhook
        import requests
        
        # Get pending webhooks
        pending_webhooks = ProviderWebhook.objects.filter(
            delivered=False,
            delivery_attempts__lt=5,  # Max 5 attempts
            next_retry__lte=timezone.now()
        ).select_related('provider', 'transaction')[:50]  # Process 50 at a time
        
        sent_count = 0
        failed_count = 0
        
        for webhook in pending_webhooks:
            try:
                # Prepare payload
                payload = {
                    'event': webhook.event,
                    'transaction_id': str(webhook.transaction.id),
                    'amount': float(webhook.transaction.net_amount),
                    'currency': webhook.transaction.converted_currency.code,
                    'status': webhook.transaction.status,
                    'timestamp': webhook.created_at.isoformat(),
                    'signature': _generate_webhook_signature(webhook)
                }
                
                # Send webhook
                timeout = webhook.provider.settings.webhook_timeout if hasattr(webhook.provider, 'settings') else 30
                response = requests.post(
                    webhook.provider.webhook_url,
                    json=payload,
                    timeout=timeout,
                    headers={
                        'Content-Type': 'application/json',
                        'X-UCPG-Event': webhook.event,
                        'X-UCPG-Signature': payload['signature']
                    }
                )
                
                if response.status_code in range(200, 300):
                    webhook.mark_delivered(response.status_code, response.text[:1000])
                    sent_count += 1
                else:
                    webhook.mark_failed(f"HTTP {response.status_code}: {response.text[:500]}", response.status_code)
                    failed_count += 1
                    
            except Exception as e:
                webhook.mark_failed(str(e))
                failed_count += 1
                logger.error(f"Error sending webhook {webhook.id}: {str(e)}")
        
        logger.info(f"Webhook task completed. Sent {sent_count}, failed {failed_count}")
        
        return {
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error sending webhooks: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def generate_daily_reports():
    """
    Celery task to generate daily reports
    Runs daily at midnight
    """
    try:
        from .services import CommissionService
        from django.db.models import Count, Sum
        from .models import Transaction, PromoLink
        
        # Get yesterday's date
        yesterday = timezone.now().date() - timedelta(days=1)
        
        # Transaction statistics
        transactions = Transaction.objects.filter(created_at__date=yesterday)
        transaction_stats = transactions.aggregate(
            count=Count('id'),
            volume=Sum('original_amount'),
            commission=Sum('commission_amount')
        )
        
        # Promo link statistics
        promo_stats = PromoLink.objects.filter(created_at__date=yesterday).aggregate(
            created=Count('id'),
            used=Count('id', filter=Q(is_used=True))
        )
        
        # Commission statistics
        commission_service = CommissionService()
        commission_stats = commission_service.get_commission_statistics(days=1)
        
        report_data = {
            'date': yesterday.isoformat(),
            'transactions': transaction_stats,
            'promo_links': promo_stats,
            'commission': commission_stats,
            'generated_at': timezone.now().isoformat()
        }
        
        # Here you could:
        # - Save report to database
        # - Send email to admins
        # - Store in file system
        # - Send to external analytics service
        
        logger.info(f"Daily report generated for {yesterday}")
        
        return {
            'success': True,
            'report_date': yesterday.isoformat(),
            'data': report_data
        }
        
    except Exception as e:
        logger.error(f"Error generating daily report: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


def _generate_webhook_signature(webhook):
    """Generate HMAC signature for webhook"""
    import hmac
    import hashlib
    
    # Use provider's API secret as key
    secret = webhook.provider.api_secret or webhook.provider.api_key
    message = f"{webhook.event}:{webhook.transaction.id}:{webhook.created_at.isoformat()}"
    
    signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return f"sha256={signature}"
