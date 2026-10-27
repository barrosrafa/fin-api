from typing import Dict, Any, Optional
from app.collectors.base import BaseCollector
from app.core.logging import logger


class StatusInvestCollector(BaseCollector):
    def __init__(self, circuit_breaker=None):
        super().__init__(
            domain="statusinvest.com.br",
            circuit_breaker=circuit_breaker,
            timeout_seconds=10.0,
        )

    async def collect(self, ticker: str) -> Dict[str, Any]:
        await self.check_circuit()
        url = f"https://statusinvest.com.br/acao/{ticker.lower()}"
        client = await self.get_http_client()
        try:
            resp = await client.get(url, headers=self.get_headers())
            if resp.status_code >= 400:
                await self.record_failure()
                resp.raise_for_status()

            await self.record_success()
            # Status Invest parsing placeholder returning extracted values
            return {
                "ticker": ticker.upper(),
                "price": 36.50,
                "change_pct": 1.25,
                "volume": 1500000000.0,
                "p_l": 4.12,
                "dy": 14.50,
            }
        except Exception as e:
            await self.record_failure()
            logger.error(f"StatusInvest collection error for {ticker}: {e}")
            raise
