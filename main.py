import asyncio
import signal
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.websocket.routers import router
from src.websocket.schemas import ManagerState
from src.logging import logger
from src import manager


NOTIFICATION_INTERVAL = 10
DEFAULT_MESSAGE = 'ping'


async def notification_task():
    """Send a message to all clients periodically"""
    while True:
        try:
            await asyncio.sleep(NOTIFICATION_INTERVAL)

            if manager.is_accepting_connections() and manager.get_connection_count() > 0:
                message = {
                    'message': DEFAULT_MESSAGE,
                    'timestamp': datetime.now().isoformat()
                }
                await manager.broadcast(message)
                logger.info(f'Send {DEFAULT_MESSAGE} to {manager.get_connection_count()} clients')
        except Exception as e:
            logger.error(f'Error while sending message: {e}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    logger.info('Server starting up...')
    await manager.initialize()

    def signal_handler(signum, frame):
        logger.info(f'Received signal {signum}')
        manager.request_shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    # notifs_task = asyncio.create_task(notification_task())

    yield

    logger.info('Server shutting down...')
    # notifs_task.cancel()
    if manager.state == ManagerState.RUNNING:
        manager.request_shutdown()
    if manager.shutdown_task:
        await manager.shutdown_task
    await manager.close()


app = FastAPI(
    title="WebSocket Server",
    description="Real-time for sending real-time notifications",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router)
