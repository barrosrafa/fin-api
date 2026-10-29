import json
import asyncio
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import get_settings

_redis_client: Optional[aioredis.Redis] = None
_redis_loop: asyncio.AbstractEventLoop | None = None


async def get_redis_client() -> aioredis.Redis:
    global _redis_client, _redis_loop
    current_loop = asyncio.get_running_loop()
    if _redis_client is None or _redis_loop is not current_loop:
        _redis_loop = current_loop
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,
            max_connections=20,
        )
    return _redis_client


async def close_redis_client():
    global _redis_client, _redis_loop
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        _redis_loop = None


class CacheService:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def get_json(self, key: str) -> Optional[dict]:
        val = await self.redis.get(key)
        if val is None:
            return None
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        return json.loads(val)

    async def set_json(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        serialized = json.dumps(value, default=str)
        return await self.redis.set(key, serialized, ex=ttl_seconds)

    async def delete(self, key: str) -> int:
        return await self.redis.delete(key)
