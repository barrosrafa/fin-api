from typing import Sequence
import redis.asyncio as aioredis


class TickerCatalog:
    """
    O(1) Redis-backed set for validating official B3/CVM tickers.
    Acts as Layer 1 Gatekeeper for Cold-Start.
    """

    DEFAULT_CATALOG_KEY = "catalog:tickers:b3"

    def __init__(
        self,
        redis_client: aioredis.Redis,
        catalog_key: str = DEFAULT_CATALOG_KEY,
    ):
        self.redis = redis_client
        self.catalog_key = catalog_key

    async def is_valid(self, ticker: str) -> bool:
        """Returns True if ticker is in the official pre-seeded catalog (O(1))."""
        normalized = ticker.strip().upper()
        try:
            res = await self.redis.sismember(self.catalog_key, normalized)
            return bool(res)
        except Exception:
            return False

    async def add_tickers(self, tickers: Sequence[str]) -> int:
        """Adds a batch of tickers to the catalog."""
        if not tickers:
            return 0
        normalized = [t.strip().upper() for t in tickers if t.strip()]
        if not normalized:
            return 0
        return await self.redis.sadd(self.catalog_key, *normalized)

    async def get_all_tickers(self) -> set[str]:
        """Returns all tickers currently in the catalog."""
        members = await self.redis.smembers(self.catalog_key)
        return {
            m.decode("utf-8") if isinstance(m, bytes) else str(m)
            for m in members
        }
