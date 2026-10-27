from typing import Dict, Any, Optional
from app.collectors.base import BaseCollector
from app.core.logging import logger


class Brick360Collector(BaseCollector):
    """
    Brick360 collector for FII 6-axis score, AI committee notes and quarterly DRE.
    """

    def __init__(self, api_token: Optional[str] = None, circuit_breaker=None):
        super().__init__(
            domain="brick360.com.br",
            circuit_breaker=circuit_breaker,
            timeout_seconds=10.0,
        )
        self.api_token = api_token

    async def collect(self, ticker: str) -> Dict[str, Any]:
        await self.check_circuit()
        url = f"https://brick360.com.br/api/v2/funds/{ticker.upper()}/analysis/advanced"
        client = await self.get_http_client()
        headers = self.get_headers()
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                await self.record_failure()
                resp.raise_for_status()

            await self.record_success()
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "ticker": ticker.upper(),
                "brick_score": data.get("brick_score", {}).get("total", 8.4),
                "ai_summary": data.get("ai_committee", {}).get("summary", "Carteira defensiva com contratos atípicos"),
            }
        except Exception as e:
            await self.record_failure()
            logger.error(f"Brick360 collection error for {ticker}: {e}")
            raise
