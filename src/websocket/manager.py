import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import WebSocket
from starlette.status import WS_1001_GOING_AWAY

from src.logging import logger
from .schemas import ManagerState
from .redis_backend import RedisBackend


SECONDS_IN_MINUTE = 60
SHUTDOWN_CHECK_INTERVAL = 10


class ClientInfo:
    def __init__(self, client_id: str, ip_address: str):
        self.client_id = client_id
        self.ip_address = ip_address
        self.connected_at = datetime.now()

    def to_dict(self):
        return {
            'client_id': self.client_id,
            'ip_address': self.ip_address,
            'connected_at': self.connected_at.isoformat()
        }


class ConnectionManager:
    def __init__(self, backend: RedisBackend, shutdown_timeout: int = 30):
        self.backend = backend
        self.backend.set_broadcast_callback(self._handle_remote_broadcast)
        self.local_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, ClientInfo] = {}

        self.state = ManagerState.RUNNING
        self.shutdown_timeout = timedelta(minutes=shutdown_timeout)
        self.shutdown_requested_at: Optional[datetime] = None
        self.shutdown_task: Optional[asyncio.Task] = None
        self.shutdown_check_interval = SHUTDOWN_CHECK_INTERVAL
        self.lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the connection manager and backend"""
        await self.backend.initialize()
        logger.info(f"Connection manager initialized with backend (worker: {self.backend.worker_id})")

    async def close(self):
        """Close the connection manager and backend"""
        await self.backend.cleanup_worker_connections()
        await self.backend.close()

    async def connect(self, websocket: WebSocket, client_id: str, ip_address: str):
        """Register a new connection"""
        await websocket.accept()
        conn_id = f"{self.backend.worker_id}:{client_id}:{uuid.uuid4().hex[:8]}"

        async with self.lock:
            self.local_connections[conn_id] = websocket
            client_info = ClientInfo(client_id, ip_address)
            self.connection_metadata[conn_id] = client_info

            await self.backend.add_connection(conn_id, client_info.to_dict())

        total_connections = await self.backend.get_connection_count()
        logger.info(f'Client {client_id} connected from {ip_address} (conn: {conn_id}).'
                    f'Total connections: {total_connections}')

        return conn_id

    async def disconnect(self, conn_id: str):
        """Unregister connection"""
        async with self.lock:
            await self._remove_local_connection(conn_id)
            await self.backend.remove_connection(conn_id)

        total_connections = await self.backend.get_connection_count()
        logger.info(f'Client {conn_id} disconnected. Total connections: {total_connections}')

    async def _remove_local_connection(self, conn_id: str):
        """Remove connection from local storage"""
        self.local_connections.pop(conn_id, None)
        self.connection_metadata.pop(conn_id, None)

    def get_local_connection_count(self) -> int:
        """Get local connection count for this worker"""
        return len(self.local_connections)

    def is_accepting_connections(self) -> bool:
        """Check if the server should accept new connections"""
        return self.state == ManagerState.RUNNING

    async def get_full_status(self) -> dict:
        """Get the current status"""
        status = {
            'state': self.state.value,
            'active_connections': await self.backend.get_connection_count(),
            'worker_id': self.backend.worker_id,
            'worker_connections': self.get_local_connection_count()
        }

        if self.shutdown_requested_at:
            elapsed = datetime.now() - self.shutdown_requested_at
            remaining = self.shutdown_timeout - elapsed
            status['shutdown_elapsed_seconds'] = int(elapsed.total_seconds())
            status['shutdown_remaining_seconds'] = max(0, int(remaining.total_seconds()))

        return status

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        await self.backend.publish_broadcast(message)
        await self._broadcast_to_local_connections(message)

    async def _handle_remote_broadcast(self, message: dict):
        """Handle broadcast messages received from other workers via backend"""
        await self._broadcast_to_local_connections(message)

    async def _broadcast_to_local_connections(self, message: dict):
        """Send a message to all local connections"""
        disconnected = []

        for conn_id, connection in list(self.local_connections.items()):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f'Failed to send message to client {conn_id}: {e}')
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.disconnect(conn_id)

    async def close_all_connections(self):
        """Force close all active connections on this worker"""
        logger.info(f'Closing all {len(self.local_connections)} worker {self.backend.worker_id} active connections...')

        for conn_id, connection in list(self.local_connections.items()):
            try:
                await connection.close(code=WS_1001_GOING_AWAY, reason='Server shutting down')
            except Exception as e:
                logger.error(f'Error closing connection {conn_id}: {e}')

        async with self.lock:
            self.local_connections.clear()
            self.connection_metadata.clear()

        async with self.lock:
            conn_ids = list(self.local_connections.keys())
            self.local_connections.clear()
            self.connection_metadata.clear()

            for conn_id in conn_ids:
                await self.backend.remove_connection(conn_id)

        logger.info(f'All worker {self.backend.worker_id} connections closed')

    def request_shutdown(self):
        """Initiate a graceful shutdown process"""
        if self.state != ManagerState.RUNNING:
            logger.warning('Shutdown already in progress')
            return

        logger.info(f'Shutdown requested for worker {self.backend.worker_id} - initiating graceful shutdown')
        self.state = ManagerState.SHUTDOWN_REQUESTED
        self.shutdown_requested_at = datetime.now()
        self.shutdown_task = asyncio.create_task(self._monitor_shutdown())

    async def _monitor_shutdown(self):
        """Monitor connections and enforce timeout"""
        logger.info(f'Monitoring shutdown for worker {self.backend.worker_id} - will force close after {int(self.shutdown_timeout.total_seconds()) // SECONDS_IN_MINUTE} minutes')

        while self.state == ManagerState.SHUTDOWN_REQUESTED:
            active_count = self.get_local_connection_count()
            elapsed = datetime.now() - self.shutdown_requested_at
            remaining = self.shutdown_timeout - elapsed

            logger.info(f'Shutdown monitor for worker {self.backend.worker_id}: {active_count} active connections, {elapsed.total_seconds():.0f}s elapsed, {remaining.total_seconds():.0f}s remaining')

            if active_count == 0:
                logger.info('All connections closed naturally for worker {self.backend.worker_id} - proceeding to shutdown')
                break

            if elapsed >= self.shutdown_timeout:
                logger.warning(f'Shutdown timeout for worker {self.backend.worker_id} reached after {int(self.shutdown_timeout.total_seconds()) // SECONDS_IN_MINUTE} minutes - forcing closure')
                await self.close_all_connections()
                break

            await asyncio.sleep(self.shutdown_check_interval)

        self.state = ManagerState.SHUTDOWN
        logger.info(f'Shutdown completed for worker {self.backend.worker_id}')
