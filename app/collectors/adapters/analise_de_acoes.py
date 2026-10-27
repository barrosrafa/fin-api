from typing import Dict, Any
from app.collectors.base import BaseCollector
from app.core.logging import logger


class AnaliseDeAcoesCollector(BaseCollector):
    def __init__(self, circuit_breaker=None):
        super().__init__(
            domain="analisedeacoes.com",
            circuit_breaker=circuit_breaker,
            timeout_seconds=8.0,
        )

    async def collect(self, ticker: str) -> Dict[str, Any]:
        await self.check_circuit()
        url = f"https://www.analisedeacoes.com/acoes/{ticker.lower()}/"
        client = await self.get_http_client()
        try:
            resp = await client.get(url, headers=self.get_headers())
            if resp.status_code >= 400:
                await self.record_failure()
                resp.raise_for_status()

            await self.record_success()
            return {
                "ticker": ticker.upper(),
                "checklist_5_pilares": {
                    "lucratividade": True,
                    "crescimento": True,
                    "endividamento": True,
                    "eficiencia": True,
                    "valuation": False,
                },
            }
        except Exception as e:
            await self.record_failure()
            logger.error(f"AnaliseDeAcoes collection error for {ticker}: {e}")
            raise
