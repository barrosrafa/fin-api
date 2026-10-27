from typing import Optional
import redis.asyncio as aioredis


class RedisCircuitBreaker:
    """
    Sliding window / failure counter circuit breaker backed by Redis.
    Trip conditions:
      - When failures reach failure_threshold within failure_window_seconds,
        an open-flag is stored with TTL = cooldown_seconds.
    """

    def __init__(
        self,
        domain: str,
        redis_client: aioredis.Redis,
        failure_threshold: int = 5,
        failure_window_seconds: int = 120,
        cooldown_seconds: int = 600,
    ):
        self.domain = domain
        self.redis = redis_client
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.cooldown_seconds = cooldown_seconds

        self._open_key = f"cb:{self.domain}:open"
        self._counter_key = f"cb:{self.domain}:failures"

    async def can_execute(self) -> bool:
        """Returns True if the circuit is CLOSED (healthy) or HALF-OPEN."""
        is_open = await self.redis.get(self._open_key)
        return is_open is None

    async def get_cooldown_remaining(self) -> int:
        ttl = await self.redis.ttl(self._open_key)
        return max(0, ttl) if ttl is not None else 0

    async def record_failure(self) -> None:
        """Increments the error count and trips the circuit if threshold reached."""
        count = await self.redis.incr(self._counter_key)
        if count == 1:
            await self.redis.expire(self._counter_key, self.failure_window_seconds)

        if count >= self.failure_threshold:
            # Trip the circuit breaker
            await self.redis.set(self._open_key, "1", ex=self.cooldown_seconds)
            await self.redis.delete(self._counter_key)

    async def record_success(self) -> None:
        """Resets the failure counter on successful execution."""
        await self.redis.delete(self._counter_key)
        await self.redis.delete(self._open_key)
