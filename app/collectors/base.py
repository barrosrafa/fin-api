import random
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import httpx
from app.core.circuit_breaker import RedisCircuitBreaker
from app.core.exceptions import CollectorCircuitOpenException
from app.core.logging import logger

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]


class BaseCollector(ABC):
    """
    Base class for all 12 REA financial data collectors.
    Handles HTTP client reuse, headers/user-agent rotation, and Redis circuit breaking.
    """

    def __init__(
        self,
        domain: str,
        circuit_breaker: Optional[RedisCircuitBreaker] = None,
        timeout_seconds: float = 10.0,
    ):
        self.domain = domain
        self.circuit_breaker = circuit_breaker
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    async def get_http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def check_circuit(self) -> None:
        if self.circuit_breaker is not None:
            can_run = await self.circuit_breaker.can_execute()
            if not can_run:
                cooldown = await self.circuit_breaker.get_cooldown_remaining()
                raise CollectorCircuitOpenException(
                    domain=self.domain,
                    cooldown_remaining=cooldown,
                )

    async def record_failure(self) -> None:
        if self.circuit_breaker is not None:
            await self.circuit_breaker.record_failure()

    async def record_success(self) -> None:
        if self.circuit_breaker is not None:
            await self.circuit_breaker.record_success()

    @abstractmethod
    async def collect(self, ticker: str) -> Dict[str, Any]:
        """Collects raw data for the ticker from the external source."""
        pass

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
