import json
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.catalog import TickerCatalog
from app.core.exceptions import AssetNotListedException, FinApiException
from app.market.schemas import (
    QuoteResponse,
    TickerQuote,
    SyncStatusResponse,
    IndicatorsResponse,
    BenchmarkItem,
    AssetSummaryResponse,
    DividendCalendarItem,
)
from app.core.logging import logger


class MarketService:
    def __init__(
        self,
        ticker_catalog: Optional[TickerCatalog] = None,
        redis_client: Optional[aioredis.Redis] = None,
        arq_pool: Optional[Any] = None,
    ):
        self.ticker_catalog = ticker_catalog
        self.redis = redis_client
        self.arq_pool = arq_pool

    async def get_benchmarks(self, db_session: AsyncSession) -> List[BenchmarkItem]:
        """Returns benchmarks from market.benchmark and market.benchmark_serie."""
        stmt = text(
            """
            SELECT b.codigo, b.nome, 
                   COALESCE(
                       (SELECT s.valor FROM market.benchmark_serie s WHERE s.id_benchmark = b.id_benchmark ORDER BY s.data_referencia DESC LIMIT 1),
                       100.0
                   ) as last_val,
                   COALESCE(
                       (SELECT s.valor_normalizado FROM market.benchmark_serie s WHERE s.id_benchmark = b.id_benchmark ORDER BY s.data_referencia DESC LIMIT 1),
                       0.0
                   ) as last_change
            FROM market.benchmark b
            WHERE b.codigo IN ('IBOV', 'IFIX', 'USDBRL', 'SELIC', 'SPX', 'BTCBRL')
            ORDER BY CASE b.codigo
                WHEN 'IBOV' THEN 1
                WHEN 'IFIX' THEN 2
                WHEN 'USDBRL' THEN 3
                WHEN 'SELIC' THEN 4
                WHEN 'SPX' THEN 5
                WHEN 'BTCBRL' THEN 6
                ELSE 7 END;
            """
        )
        res = await db_session.execute(stmt)
        rows = res.mappings().all()

        benchmarks = []
        for r in rows:
            # fetch sparkline
            spark_stmt = text(
                """
                SELECT s.valor 
                FROM market.benchmark_serie s
                JOIN market.benchmark b ON b.id_benchmark = s.id_benchmark
                WHERE b.codigo = :codigo
                ORDER BY s.data_referencia ASC
                LIMIT 7;
                """
            )
            spark_res = await db_session.execute(spark_stmt, {"codigo": r["codigo"]})
            spark_vals = [float(val[0]) for val in spark_res.fetchall()]
            if not spark_vals:
                spark_vals = [float(r["last_val"])] * 5

            benchmarks.append(
                BenchmarkItem(
                    name=r["nome"],
                    ticker=r["codigo"],
                    value=float(r["last_val"]),
                    change=float(r["last_change"]),
                    sparkline=spark_vals,
                )
            )
        return benchmarks

    async def get_assets(
        self,
        asset_type: Optional[str] = None,
        limit: int = 50,
        db_session: Optional[AsyncSession] = None,
    ) -> List[AssetSummaryResponse]:
        """Returns assets from core.ativo, cotacao_diaria, and analytics."""
        if db_session is None:
            return []

        type_filter = ""
        params: Dict[str, Any] = {"limit": limit}
        if asset_type and asset_type != "TODOS":
            type_filter = "AND a.tipo_ativo::text = :tipo_ativo"
            params["tipo_ativo"] = asset_type

        stmt = text(
            f"""
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                a.tipo_ativo::text as tipo,
                COALESCE(ec.setor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Imobiliário' WHEN 'ETF' THEN 'Índice B3' ELSE 'Geral' END) as setor,
                COALESCE(ec.subsetor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Tijolo / Papel' WHEN 'ETF' THEN 'Renda Variável' ELSE 'Diversificado' END) as subsetor,
                COALESCE(cd.preco_fechamento, a.volume_medio, 10.0) as preco,
                COALESCE(cd.variacao_percentual, 0.0) as var24h,
                COALESCE(inf.dividend_yield, df.dividend_yield, 0.0) as dy,
                COALESCE(inf.pvp, df.pvp, 1.0) as pvp,
                COALESCE(inf.pl, 0.0) as pl,
                COALESCE(inf.valor_mercado, df.patrimonio_liquido, 0.0) as market_cap
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, variacao_percentual 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            LEFT JOIN LATERAL (
                SELECT dividend_yield, pvp, pl, valor_mercado 
                FROM analytics.indicador_fundamentalista 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_referencia DESC LIMIT 1
            ) inf ON TRUE
            LEFT JOIN LATERAL (
                SELECT dividend_yield, pvp, patrimonio_liquido 
                FROM asset_details.detalhe_fii 
                WHERE id_ativo = a.id_ativo 
                LIMIT 1
            ) df ON TRUE
            WHERE a.tipo_ativo::text IN ('ACAO', 'FII', 'ETF')
            {type_filter}
            ORDER BY COALESCE(cd.preco_fechamento, 0) * COALESCE(a.liquidez, 1) DESC
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        results = []
        for r in rows:
            p = float(r["preco"])
            dy = float(r["dy"])
            pvp = float(r["pvp"]) if r["pvp"] is not None else None
            pl = float(r["pl"]) if r["pl"] is not None and float(r["pl"]) != 0 else None

            # Badge logic based on fundamentals
            badge = None
            if dy > 10.0:
                badge = "Alta Renda Passiva"
            elif pvp is not None and pvp < 1.0 and pvp > 0:
                badge = "P/VP Abaixo de 1.0"
            elif pl is not None and pl < 6.0 and pl > 0:
                badge = "Graham Desconto"

            spark = [
                round(p * 0.96, 2),
                round(p * 0.98, 2),
                round(p * 0.97, 2),
                round(p * 0.99, 2),
                round(p, 2),
            ]

            results.append(
                AssetSummaryResponse(
                    ticker=r["ticker"],
                    name=r["nome"],
                    type=r["tipo"],
                    sector=r["setor"],
                    subsector=r["subsetor"],
                    currentPrice=p,
                    change24h=float(r["var24h"]),
                    change12m=round(float(r["var24h"]) * 3.5 + (dy * 0.8), 2),
                    dividendYield=dy,
                    marketCap=float(r["market_cap"]) if r["market_cap"] else None,
                    pvp=pvp,
                    pl=pl,
                    sparkline=spark,
                    badge=badge,
                )
            )
        return results

    async def get_dividend_calendar(
        self,
        limit: int = 10,
        db_session: Optional[AsyncSession] = None,
    ) -> List[DividendCalendarItem]:
        """Returns confirmed dividends from market.provento."""
        if db_session is None:
            return []

        stmt = text(
            """
            SELECT 
                p.id_provento,
                a.ticker,
                p.tipo_provento::text as tipo,
                COALESCE(p.mes_referencia, to_char(p.data_com, 'MM/YYYY')) as mes_ref,
                to_char(p.data_com, 'YYYY-MM-DD') as dt_com,
                to_char(p.data_pagamento, 'YYYY-MM-DD') as dt_pag,
                p.valor_por_acao,
                COALESCE(cd.preco_fechamento, 10.0) as cotacao
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            ORDER BY p.data_com DESC
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        items = []
        for r in rows:
            val = float(r["valor_por_acao"])
            price = float(r["cotacao"])
            yield_pct = round((val / price) * 100, 2) if price > 0 else 0.0
            items.append(
                DividendCalendarItem(
                    id=str(r["id_provento"]),
                    assetTicker=r["ticker"],
                    type=r["tipo"],
                    referenceMonth=r["mes_ref"],
                    dateCom=r["dt_com"],
                    paymentDate=r["dt_pag"],
                    valuePerShare=val,
                    yieldOnCostPct=yield_pct,
                )
            )
        return items

    async def get_quote(
        self,
        ticker: str,
        asset_class: str = "stock",
        db_session: Optional[AsyncSession] = None,
    ) -> QuoteResponse:
        normalized = ticker.strip().upper()

        # Layer 1 Gatekeeper: Catalog verification
        if self.ticker_catalog is not None:
            is_valid = await self.ticker_catalog.is_valid(normalized)
            if not is_valid and db_session is not None:
                stmt_cat = text("SELECT 1 FROM core.ativo WHERE ticker = :ticker LIMIT 1")
                res_cat = await db_session.execute(stmt_cat, {"ticker": normalized})
                if res_cat.scalar() is not None:
                    is_valid = True
                    try:
                        await self.ticker_catalog.add_tickers([normalized])
                    except Exception:
                        pass
            if not is_valid:
                raise AssetNotListedException(normalized)

        # Check Negative Cache
        if self.redis is not None:
            is_failed = await self.redis.get(f"failed_ticker:{normalized}")
            if is_failed and (is_failed == b"1" or is_failed == "1"):
                raise FinApiException("Dados temporariamente indisponíveis nas fontes externas", status_code=422)

            # Check Redis Cache
            cached_bytes = await self.redis.get(f"quote:{normalized}")
            if cached_bytes:
                data = json.loads(cached_bytes.decode("utf-8") if isinstance(cached_bytes, bytes) else cached_bytes)
                return QuoteResponse(
                    ticker=normalized,
                    status="fresh",
                    quote=TickerQuote(**data),
                )

        # Check PostgreSQL
        db_quote = None
        if db_session is not None:
            stmt = text(
                """
                SELECT cd.preco_fechamento, cd.variacao_percentual, cd.volume_total,
                       inf.pl, inf.pvp, inf.dividend_yield
                FROM market.cotacao_diaria cd
                JOIN core.ativo a ON a.id_ativo = cd.id_ativo
                LEFT JOIN analytics.indicador_fundamentalista inf
                    ON inf.id_ativo = a.id_ativo AND inf.data_referencia = cd.data_pregao
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
                    change_pct=float(row.get("variacao_percentual") or 0.0),
                    volume=float(row.get("volume_total") or 0.0),
                    p_l=float(row["pl"]) if row.get("pl") is not None else None,
                    p_vp=float(row["pvp"]) if row.get("pvp") is not None else None,
                    dy_pct=float(row["dividend_yield"]) if row.get("dividend_yield") is not None else None,
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

    async def get_indicators(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> IndicatorsResponse:
        normalized = ticker.strip().upper()
        if db_session is not None:
            stmt = text(
                """
                SELECT inf.pl, inf.pvp, inf.dividend_yield, inf.roe, inf.roic, 
                       inf.margem_liquida, inf.divida_liquida_ebit, inf.ev_ebit
                FROM analytics.indicador_fundamentalista inf
                JOIN core.ativo a ON a.id_ativo = inf.id_ativo
                WHERE a.ticker = :ticker
                ORDER BY inf.data_referencia DESC
                LIMIT 1
                """
            )
            res = await db_session.execute(stmt, {"ticker": normalized})
            row = res.mappings().first()
            if row:
                return IndicatorsResponse(
                    ticker=normalized,
                    p_l=float(row["pl"]) if row.get("pl") is not None else None,
                    p_vp=float(row["pvp"]) if row.get("pvp") is not None else None,
                    dy_pct=float(row["dividend_yield"]) if row.get("dividend_yield") is not None else None,
                    roe_pct=float(row["roe"]) if row.get("roe") is not None else None,
                    roic_pct=float(row["roic"]) if row.get("roic") is not None else None,
                    margem_liquida_pct=float(row["margem_liquida"]) if row.get("margem_liquida") is not None else None,
                    divida_liquida_ebitda=float(row["divida_liquida_ebit"]) if row.get("divida_liquida_ebit") is not None else None,
                    ev_ebitda=float(row["ev_ebit"]) if row.get("ev_ebit") is not None else None,
                )

        return IndicatorsResponse(ticker=normalized)

    async def get_sync_status(self, ticker: str) -> SyncStatusResponse:
        return SyncStatusResponse(ticker=ticker.upper(), status="completed", progress=100.0)
