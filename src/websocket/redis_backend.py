import os
import asyncio
import json
import redis.asyncio as aioredis
from typing import Optional, Any, Callable

from src.logging import logger

SECONDS_PER_HOUR = 3600
CONNECTION_TTL = 10 * SECONDS_PER_HOUR


class RedisBackend:
    """Handles Redis operations"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub_broadcast: Optional[aioredis.client.PubSub] = None
        self.worker_id = str(os.getpid())

        self.connections_key = "websocket:connections"
        self.metadata_key = "websocket:metadata"
        self.broadcast_channel = "websocket:broadcast"

        self._broadcast_callback: Optional[Callable] = None
        self._broadcast_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize Redis connection"""
        self.redis = aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        self.pubsub_broadcast = self.redis.pubsub()
        await self.pubsub_broadcast.subscribe(self.broadcast_channel)

        self._broadcast_task = asyncio.create_task(self._listen_for_broadcasts())
        logger.info(f'Redis backend initialized worker: {self.worker_id}')

    def set_broadcast_callback(self, callback: Callable[[dict], Any]):
        """Set a callback to handle incoming broadcast messages"""
        self._broadcast_callback = callback

    async def _listen_for_broadcasts(self):
        """Listen for broadcast messages from Redis"""
        try:
            async for message in self.pubsub_broadcast.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        sender_worker_id = data.get('sender_worker_id')

                        if sender_worker_id == self.worker_id:
                            continue

                        payload = data.get('payload')
                        if self._broadcast_callback:
                            await self._broadcast_callback(payload)
                    except Exception as e:
                        logger.error(f'Error processing broadcast message: {e}')
        except asyncio.CancelledError:
            logger.info('Broadcast listener cancelled')
        except Exception as e:
            logger.error(f'Error in broadcast listener: {e}')

    async def add_connection(self, conn_id: str, metadata: dict):
        """Add a connection"""
        await self.redis.hset(self.connections_key, conn_id, self.worker_id)
        await self.redis.hset(self.metadata_key, conn_id, json.dumps(metadata))
        await self.redis.expire(self.connections_key, CONNECTION_TTL)
        await self.redis.expire(self.metadata_key, CONNECTION_TTL)

    async def remove_connection(self, conn_id: str):
        """Remove a connection"""
        await self.redis.hdel(self.connections_key, conn_id)
        await self.redis.hdel(self.metadata_key, conn_id)

    async def get_connection_count(self) -> int:
        """Get total connection count across all workers"""
        count = await self.redis.hlen(self.connections_key)
        return count

    async def publish_broadcast(self, message: dict):
        """Publish a broadcast message to all workers"""
        payload = {'sender_worker_id': self.worker_id, 'payload': message}
        await self.redis.publish(self.broadcast_channel, json.dumps(payload))
