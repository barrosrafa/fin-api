from typing import List, Optional
from app.collectors.base import BaseCollector
from app.collectors.normalizer import DataNormalizer, CanonicalQuote
from app.collectors.adapters.status_invest import StatusInvestCollector
from app.collectors.adapters.fundamentus import FundamentusCollector
from app.collectors.adapters.investidor10 import Investidor10Collector
from app.collectors.adapters.clube_fii import ClubeFiiCollector
from app.collectors.adapters.funds_explorer import FundsExplorerCollector
from app.collectors.adapters.fiis_com_br import FiisComBrCollector
from app.collectors.adapters.brick360 import Brick360Collector
from app.collectors.adapters.mais_retorno import MaisRetornoCollector
from app.collectors.adapters.etfs_brasil import EtfsBrasilCollector
from app.core.exceptions import FinApiException
from app.core.logging import logger


class CollectorRouter:
    """
    Orchestrates the 12 REA collectors with asset-class priority chains and automatic failover.
    """

    def __init__(
        self,
        stock_collectors: Optional[List[BaseCollector]] = None,
        fii_collectors: Optional[List[BaseCollector]] = None,
        fund_collectors: Optional[List[BaseCollector]] = None,
        etf_collectors: Optional[List[BaseCollector]] = None,
    ):
        self.stock_collectors = stock_collectors or [
            StatusInvestCollector(),
            FundamentusCollector(),
            Investidor10Collector(),
        ]
        self.fii_collectors = fii_collectors or [
            ClubeFiiCollector(),
            FundsExplorerCollector(),
            FiisComBrCollector(),
            Brick360Collector(),
        ]
        self.fund_collectors = fund_collectors or [
            MaisRetornoCollector(),
            StatusInvestCollector(),
        ]
        self.etf_collectors = etf_collectors or [
            EtfsBrasilCollector(),
            StatusInvestCollector(),
        ]

    async def _execute_chain(self, collectors: List[BaseCollector], identifier: str) -> CanonicalQuote:
        errors = []
        for collector in collectors:
            try:
                raw = await collector.collect(identifier)
                return DataNormalizer.normalize_quote(raw, source=collector.domain)
            except Exception as e:
                errors.append(f"{collector.domain}: {str(e)}")
                logger.warning(
                    f"Collector {collector.domain} failed for {identifier}: {e}. Trying fallback..."
                )

        raise FinApiException(
            f"All collectors failed for '{identifier}'. Errors: {'; '.join(errors)}",
            status_code=503,
        )

    async def collect_stock(self, ticker: str) -> CanonicalQuote:
        return await self._execute_chain(self.stock_collectors, ticker)

    async def collect_fii(self, ticker: str) -> CanonicalQuote:
        return await self._execute_chain(self.fii_collectors, ticker)

    async def collect_fund(self, identifier: str) -> CanonicalQuote:
        return await self._execute_chain(self.fund_collectors, identifier)

    async def collect_etf(self, ticker: str) -> CanonicalQuote:
        return await self._execute_chain(self.etf_collectors, ticker)

    async def close(self) -> None:
        for group in (
            self.stock_collectors,
            self.fii_collectors,
            self.fund_collectors,
            self.etf_collectors,
        ):
            for c in group:
                await c.close()
