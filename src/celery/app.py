from celery import Celery
from src.config import settings


NOTIFICATION_INTERVAL = 10

celery_app = Celery(
    'websocket_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    'send-periodic-notification': {
        'task': 'src.celery.tasks.send_notification',
        'schedule': NOTIFICATION_INTERVAL,
    },
}

from src.celery import tasks    # noqa