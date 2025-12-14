import signal
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.websocket.routers import router
from src.logging import logger
from src import manager


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

    yield

    if manager.shutdown_task:
        await manager.shutdown_task


app = FastAPI(
    title="WebSocket Server",
    description="WebSocket server for sending real-time notifications with graceful shutdown",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router)
