import json
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.catalog import TickerCatalog
from app.core.exceptions import AssetNotListedException, FinApiException
from app.market.schemas import QuoteResponse, TickerQuote, SyncStatusResponse, IndicatorsResponse
from app.core.logging import logger


class MarketService:
    def __init__(
        self,
        ticker_catalog: TickerCatalog,
        redis_client: aioredis.Redis,
        arq_pool: Optional[Any] = None,
    ):
        self.ticker_catalog = ticker_catalog
        self.redis = redis_client
        self.arq_pool = arq_pool

    async def get_quote(
        self,
        ticker: str,
        asset_class: str = "stock",
        db_session: Optional[AsyncSession] = None,
    ) -> QuoteResponse:
        normalized = ticker.strip().upper()

        # Layer 1 Gatekeeper: O(1) Catalog verification
        is_valid = await self.ticker_catalog.is_valid(normalized)
        if not is_valid:
            raise AssetNotListedException(normalized)

        # Check Negative Cache (422 after repeated collector failures)
        is_failed = await self.redis.get(f"failed_ticker:{normalized}")
        if is_failed and (is_failed == b"1" or is_failed == "1"):
            raise FinApiException("Dados temporariamente indisponíveis nas fontes externas", status_code=422)

        # Layer 2: Check Redis Cache
        cached_bytes = await self.redis.get(f"quote:{normalized}")
        if cached_bytes:
            data = json.loads(cached_bytes.decode("utf-8") if isinstance(cached_bytes, bytes) else cached_bytes)
            return QuoteResponse(
                ticker=normalized,
                status="fresh",
                quote=TickerQuote(**data),
            )

        # Layer 3: Check PostgreSQL 18 / TimescaleDB
        db_quote = None
        if db_session is not None:
            stmt = text(
                """
                SELECT cd.preco_fechamento, cd.variacao_percentual, cd.volume_total
                FROM market.cotacao_diaria cd
                JOIN core.ativo a ON a.id_ativo = cd.id_ativo
                WHERE a.ticker = :ticker
                ORDER BY cd.data_pregao DESC
                LIMIT 1
                """
            )
            res = await db_session.execute(stmt, {"ticker": normalized})
            row = res.mappings().first()
            if row:
                db_quote = TickerQuote(
                    ticker=normalized,
                    price=float(row["preco_fechamento"]),
                    change_pct=float(row.get("variacao_percentual") or row.get("variacao_pct") or 0.0),
                    volume=float(row.get("volume_total") or row.get("volume_financeiro") or 0.0),
                    source=row.get("fonte", "fin-db"),
                )

        # Dispatch background job if arq pool is configured
        job_id = None
        if self.arq_pool is not None:
            try:
                job_id = await self.arq_pool.enqueue_job(
                    "refresh_ticker_data_task",
                    normalized,
                    asset_class,
                    _queue_name="high_priority",
                )
            except Exception as e:
                logger.warning(f"Failed to enqueue arq refresh job for {normalized}: {e}")

        # If DB had prior quote, return stale-while-revalidate
        if db_quote is not None:
            return QuoteResponse(
                ticker=normalized,
                status="stale",
                quote=db_quote,
                sync_id=str(job_id) if job_id else None,
            )

        # Cold-start total miss: return 202 syncing
        return QuoteResponse(
            ticker=normalized,
            status="syncing",
            sync_id=str(job_id) if job_id else "sync_pending",
            message="Ativo válido em processo de coleta inicial",
            check_url=f"/api/v1/market/{normalized}/sync-status",
        )

    async def get_sync_status(self, ticker: str) -> SyncStatusResponse:
        normalized = ticker.strip().upper()
        raw = await self.redis.get(f"sync:{normalized}")
        if not raw:
            return SyncStatusResponse(ticker=normalized, status="idle", progress=0.0)

        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return SyncStatusResponse(
            ticker=normalized,
            status=data.get("status", "idle"),
            progress=float(data.get("progress", 0.0)),
            result=data.get("result"),
        )
