import httpx

from src.logging import logger
from src.config import settings
from src.celery.app import celery_app


DEFAULT_MESSAGE = 'test message'


@celery_app.task(name='src.celery.tasks.send_notification')
def send_notification():
    """Send periodic notification to all clients"""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.post(f'{settings.WEBSOCKET_URL}/notify', params={'message': DEFAULT_MESSAGE})

            if response.status_code == 200:
                data = response.json()
                logger.info(f'Notification sent to {data.get('recipients', 0)} clients')
            else:
                logger.error(f'Failed to send notification: {response.status_code}')

    except Exception as e:
        logger.error(f"Error sending notification: {e}")
