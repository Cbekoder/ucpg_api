import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.develop')

app = Celery('ucpg_api')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule
app.conf.beat_schedule = {
    'update-exchange-rates': {
        'task': 'apps.payments.tasks.update_exchange_rates',
        'schedule': 300.0,  # Every 5 minutes
    },
    'expire-old-items': {
        'task': 'apps.payments.tasks.expire_old_transactions',
        'schedule': 3600.0,  # Every hour
    },
    'send-webhooks': {
        'task': 'apps.payments.tasks.send_provider_webhooks',
        'schedule': 300.0,  # Every 5 minutes
    },
    'cleanup-old-data': {
        'task': 'apps.payments.tasks.cleanup_old_data',
        'schedule': 86400.0,  # Daily
    },
    'generate-daily-reports': {
        'task': 'apps.payments.tasks.generate_daily_reports',
        'schedule': 86400.0,  # Daily at midnight
    },
}

app.conf.timezone = 'UTC'


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
