from .websocket.redis_backend import RedisBackend
from .websocket.manager import ConnectionManager
from .config import Settings


settings = Settings()

SHUTDOWN_TIMEOUT_MINS = 30
REDIS_URL = settings.REDIS_URL

backend = RedisBackend(redis_url=REDIS_URL)
manager = ConnectionManager(backend=backend, shutdown_timeout=SHUTDOWN_TIMEOUT_MINS)