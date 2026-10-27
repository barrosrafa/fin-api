from typing import Dict, Any, Optional
from app.collectors.base import BaseCollector
from app.core.logging import logger


class ClubeFiiCollector(BaseCollector):
    """
    Clube FII collector leveraging GraphQL CR Data API & SiiLA real estate data.
    """

    def __init__(self, jwt_token: Optional[str] = None, circuit_breaker=None):
        super().__init__(
            domain="clubefii.com.br",
            circuit_breaker=circuit_breaker,
            timeout_seconds=10.0,
        )
        self.jwt_token = jwt_token

    async def _fetch_graphql(self, query: str, variables: dict) -> dict:
        client = await self.get_http_client()
        headers = self.get_headers()
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        resp = await client.post(
            "https://api.clubefii.dev.br/graphql",
            json={"query": query, "variables": variables},
            headers=headers,
        )
        if resp.status_code >= 400:
            await self.record_failure()
            resp.raise_for_status()
        return resp.json()

    async def collect(self, ticker: str) -> Dict[str, Any]:
        await self.check_circuit()
        query = """
        query GetFiiDetails($ticker: String!) {
            fundo(codigo: $ticker) {
                codigo
                cotacao
                dy_anual
                vacancia_fisica
                quantidade_imoveis
                gestora
            }
        }
        """
        try:
            data = await self._fetch_graphql(query, {"ticker": ticker.upper()})
            fundo = data.get("data", {}).get("fundo", {})
            await self.record_success()
            return {
                "ticker": fundo.get("codigo", ticker.upper()),
                "price": fundo.get("cotacao", 0.0),
                "dy": fundo.get("dy_anual", 0.0),
                "vacancia_pct": fundo.get("vacancia_fisica", 0.0),
                "imoveis_total": fundo.get("quantidade_imoveis", 0),
                "gestora": fundo.get("gestora", ""),
            }
        except Exception as e:
            await self.record_failure()
            logger.error(f"ClubeFii collection error for {ticker}: {e}")
            raise
