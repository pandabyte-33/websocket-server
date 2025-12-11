from .websocket.manager import ConnectionManager


SHUTDOWN_TIMEOUT_MINS = 30

manager = ConnectionManager(shutdown_timeout=SHUTDOWN_TIMEOUT_MINS)
