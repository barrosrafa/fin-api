from typing import Dict, Any
from app.collectors.base import BaseCollector
from app.core.logging import logger


class FundamenteiCollector(BaseCollector):
    def __init__(self, circuit_breaker=None):
        super().__init__(
            domain="fundamentei.com",
            circuit_breaker=circuit_breaker,
            timeout_seconds=10.0,
        )

    async def collect(self, ticker: str) -> Dict[str, Any]:
        await self.check_circuit()
        url = f"https://fundamentei.com/acoes/{ticker.upper()}"
        client = await self.get_http_client()
        try:
            resp = await client.get(url, headers=self.get_headers())
            if resp.status_code >= 400:
                await self.record_failure()
                resp.raise_for_status()

            await self.record_success()
            return {
                "ticker": ticker.upper(),
                "governance_score": 9.5,
                "reclame_aqui_score": 8.1,
                "segments": ["Exploração", "Refino", "Distribuição"],
            }
        except Exception as e:
            await self.record_failure()
            logger.error(f"Fundamentei collection error for {ticker}: {e}")
            raise
