"""Atomic Redis token bucket with bounded per-process fallback during outages."""
import asyncio
import hashlib
import math
import time
from collections import OrderedDict

from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.redis import get_redis_client
from app.core.logging import logger

TOKEN_BUCKET_LUA = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local capacity, rate = tonumber(ARGV[1]), tonumber(ARGV[2])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(data[1]) or capacity
local updated = tonumber(data[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * rate)
local delay = 0
if tokens >= 1 then tokens = tokens - 1 else delay = (1 - tokens) / rate end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate) + 60)
return math.ceil(delay * 1000)
"""


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings):
        super().__init__(app)
        self.enabled = settings.API_RATE_LIMIT_ENABLED
        self.capacity = settings.API_RATE_LIMIT_BURST
        self.rate = settings.API_RATE_LIMIT_PER_MINUTE / 60
        self.local = OrderedDict()
        self.redis_retry_at = 0.0

    def local_delay(self, key):
        now = time.monotonic()
        tokens, updated = self.local.pop(key, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - updated) * self.rate)
        delay = 0 if tokens >= 1 else (1 - tokens) / self.rate
        self.local[key] = (tokens - 1 if delay == 0 else tokens, now)
        if len(self.local) > 10000:
            self.local.popitem(last=False)
        return delay

    async def dispatch(self, request, call_next):
        if not self.enabled or request.method == 'OPTIONS' or not request.url.path.startswith('/api/v1/'):
            return await call_next(request)
        peer = request.client.host if request.client else 'unknown'
        key = 'fin:api:rate:' + hashlib.sha256(peer.encode()).hexdigest()
        # Always account locally so a Redis outage cannot replenish the fallback bucket.
        local_delay = self.local_delay(key)
        delay = local_delay
        if time.monotonic() >= self.redis_retry_at:
            try:
                async with asyncio.timeout(0.25):
                    redis = await get_redis_client()
                    delay = int(await redis.eval(TOKEN_BUCKET_LUA, 1, key, self.capacity, self.rate)) / 1000
            except (RedisError, TimeoutError, OSError):
                self.redis_retry_at = time.monotonic() + 5
                logger.warning('API rate limit using bounded local fallback')
        if delay > 0:
            return JSONResponse(status_code=429, content={'detail': 'Too many requests'},
                                headers={'Retry-After': str(max(1, math.ceil(delay))),
                                         'Cache-Control': 'private, no-store'})
        return await call_next(request)
