import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import WebSocket
from starlette.status import WS_1001_GOING_AWAY

from src.logging import logger
from .schemas import ManagerState


SECONDS_IN_MINUTE = 60
SHUTDOWN_CHECK_INTERVAL = 10


class ClientInfo:
    def __init__(self, client_id: str, ip_address: str):
        self.client_id = client_id
        self.ip_address = ip_address
        self.connected_at = datetime.now()


class ConnectionManager:
    def __init__(self, shutdown_timeout: int = 30):
        self.active_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, ClientInfo] = {}
        self.state = ManagerState.RUNNING
        self.shutdown_timeout = timedelta(minutes=shutdown_timeout)
        self.shutdown_requested_at: Optional[datetime] = None
        self.shutdown_task: Optional[asyncio.Task] = None
        self.shutdown_check_interval = SHUTDOWN_CHECK_INTERVAL
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str, ip_address: str):
        """Register a new connection"""
        await websocket.accept()
        async with self.lock:
            self.active_connections.append(websocket)
            self.connection_metadata[websocket] = ClientInfo(client_id, ip_address)
        logger.info(f'Client {client_id} connected from {ip_address}. Total connections: {len(self.active_connections)}')

    async def disconnect(self, websocket: WebSocket):
        """Unregister connection"""
        async with self.lock:
            if websocket in self.active_connections:
                client_info = self.connection_metadata.get(websocket)
                self.active_connections.remove(websocket)
                self.connection_metadata.pop(websocket, None)
                logger.info(f'Client {client_info.client_id} disconnected. Total connections: {len(self.active_connections)}')

    def get_connection_count(self) -> int:
        return len(self.active_connections)

    def is_accepting_connections(self) -> bool:
        """Check if the server should accept new connections"""
        return self.state == ManagerState.RUNNING

    def get_status(self) -> dict:
        """Get the current shutdown status"""
        status = {
            'state': self.state.value,
            'active_connections': self.get_connection_count()
        }

        if self.shutdown_requested_at:
            elapsed = datetime.now() - self.shutdown_requested_at
            remaining = self.shutdown_timeout - elapsed
            status['shutdown_elapsed_seconds'] = int(elapsed.total_seconds())
            status['shutdown_remaining_seconds'] = max(0, int(remaining.total_seconds()))

        return status

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []

        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except Exception as e:
                client_info = self.connection_metadata.get(connection)
                logger.error(f'Failed to send message to client {client_info.client_id}: {e}')
                disconnected.append(connection)

        for connection in disconnected:
            await self.disconnect(connection)

    async def close_all_connections(self):
        """Force close all active connections"""
        logger.info(f'Closing all {len(self.active_connections)} active connections...')

        for connection in self.active_connections[:]:
            try:
                await connection.close(code=WS_1001_GOING_AWAY, reason='Server shutting down')
            except Exception as e:
                logger.error(f'Error closing connection: {e}')

        async with self.lock:
            self.active_connections.clear()
            self.connection_metadata.clear()

        logger.info('All connections closed')

    def request_shutdown(self):
        """Initiate a graceful shutdown process"""
        if self.state != ManagerState.RUNNING:
            logger.warning('Shutdown already in progress')
            return

        logger.info('Shutdown requested - initiating graceful shutdown')
        self.state = ManagerState.SHUTDOWN_REQUESTED
        self.shutdown_requested_at = datetime.now()
        self.shutdown_task = asyncio.create_task(self._monitor_shutdown())

    async def _monitor_shutdown(self):
        """Monitor connections and enforce timeout"""
        logger.info(f'Monitoring shutdown - will force close after {int(self.shutdown_timeout.total_seconds()) // SECONDS_IN_MINUTE} minutes')

        while self.state == ManagerState.SHUTDOWN_REQUESTED:
            active_count = self.get_connection_count()
            elapsed = datetime.now() - self.shutdown_requested_at
            remaining = self.shutdown_timeout - elapsed

            logger.info(f'Shutdown monitor: {active_count} active connections, {elapsed.total_seconds():.0f}s elapsed, {remaining.total_seconds():.0f}s remaining')

            if active_count == 0:
                logger.info('All connections closed naturally - proceeding to shutdown')
                break

            if elapsed >= self.shutdown_timeout:
                logger.warning(f'Shutdown timeout reached after {self.shutdown_timeout.total_seconds() / SECONDS_IN_MINUTE} minutes - forcing closure')
                await self.close_all_connections()
                break

            await asyncio.sleep(self.shutdown_check_interval)

        self.state = ManagerState.SHUTDOWN
        logger.info('Shutdown completed')
