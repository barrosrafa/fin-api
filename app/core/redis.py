import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import get_settings

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,
            max_connections=20,
        )
    return _redis_client


async def close_redis_client():
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


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
