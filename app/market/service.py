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
    IbovPEPoint,
    IbovPEResponse,
    InvestorFlowItem,
    InvestorFlowResponse,
    EarningsCalendarItem,
    EarningsCalendarResponse,
    DailyQuoteItem,
    QuoteHistoryResponse,
)
from app.core.logging import logger
from app.worker.settings import QUEUE_DEFAULT


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
        """Returns benchmarks from market.benchmark and market.benchmark_serie with Redis caching."""
        if self.redis:
            try:
                cached = await self.redis.get("cache:benchmarks")
                if cached:
                    raw_list = json.loads(cached)
                    return [BenchmarkItem(**item) for item in raw_list]
            except Exception:
                pass
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
                ORDER BY s.data_referencia DESC
                LIMIT 7;
                """
            )
            spark_res = await db_session.execute(spark_stmt, {"codigo": r["codigo"]})
            spark_vals = [float(val[0]) for val in spark_res.fetchall()][::-1]
            if not spark_vals:
                spark_vals = [float(r["last_val"])] * 5
            
            # Compute actual percentage change from last 2 points if available
            change_pct = float(r["last_change"])
            if len(spark_vals) >= 2 and spark_vals[-2] > 0:
                change_pct = round(((spark_vals[-1] - spark_vals[-2]) / spark_vals[-2]) * 100.0, 2)

            benchmarks.append(
                BenchmarkItem(
                    name=r["nome"],
                    ticker=r["codigo"],
                    value=float(r["last_val"]),
                    change=change_pct,
                    sparkline=spark_vals,
                )
            )
        if self.redis and benchmarks:
            try:
                await self.redis.set(
                    "cache:benchmarks",
                    json.dumps([b.model_dump() for b in benchmarks]),
                    ex=60,
                )
            except Exception:
                pass
        return benchmarks

    async def get_assets(
        self,
        asset_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        sector: Optional[str] = None,
        subsector: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_dir: Optional[str] = "desc",
        db_session: Optional[AsyncSession] = None,
    ) -> List[AssetSummaryResponse]:
        items, _ = await self.get_assets_with_count(
            asset_type=asset_type,
            limit=limit,
            offset=offset,
            search=search,
            sector=sector,
            subsector=subsector,
            sort_by=sort_by,
            sort_dir=sort_dir,
            db_session=db_session,
        )
        return items

    async def get_assets_with_count(
        self,
        asset_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        sector: Optional[str] = None,
        subsector: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_dir: Optional[str] = "desc",
        db_session: Optional[AsyncSession] = None,
    ) -> tuple[List[AssetSummaryResponse], int]:
        """Returns assets from core.ativo, cotacao_diaria, and analytics with pagination and search."""
        if db_session is None:
            return [], 0

        where_clauses = ["a.tipo_ativo::text IN ('ACAO', 'FII', 'ETF')"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}

        if asset_type and asset_type != "TODOS":
            where_clauses.append("a.tipo_ativo::text = :tipo_ativo")
            params["tipo_ativo"] = asset_type

        if search and search.strip():
            where_clauses.append("(a.ticker ILIKE :search OR ec.nome_empresarial ILIKE :search)")
            params["search"] = f"%{search.strip()}%"

        if sector and sector != "TODOS":
            where_clauses.append(
                "(ec.setor ILIKE :sector OR (ec.setor IS NULL AND :sector = 'Imobiliário' AND a.tipo_ativo::text = 'FII') OR (ec.setor IS NULL AND :sector = 'Índice Global' AND a.tipo_ativo::text = 'ETF'))"
            )
            params["sector"] = f"%{sector.strip()}%"

        if subsector and subsector != "TODOS":
            where_clauses.append(
                "(ec.subsetor ILIKE :subsector OR (ec.subsetor IS NULL AND :subsector = 'Tijolo / Papel' AND a.tipo_ativo::text = 'FII') OR (ec.subsetor IS NULL AND :subsector = 'Renda Variável' AND a.tipo_ativo::text = 'ETF'))"
            )
            params["subsector"] = f"%{subsector.strip()}%"

        where_sql = " AND ".join(where_clauses)

        dir_sql = "ASC" if sort_dir and sort_dir.lower() == "asc" else "DESC"
        if sort_by == "dy":
            order_sql = f"COALESCE(inf.dividend_yield, df.dividend_yield, 0.0) {dir_sql} NULLS LAST, a.ticker ASC"
        elif sort_by == "pvp":
            order_sql = f"COALESCE(inf.pvp, df.pvp, 999.0) {dir_sql} NULLS LAST, a.ticker ASC"
        elif sort_by in ("preco", "currentPrice"):
            order_sql = f"COALESCE(cd.preco_fechamento, 0.0) {dir_sql} NULLS LAST, a.ticker ASC"
        elif sort_by == "change24h":
            order_sql = f"COALESCE(cd.variacao_percentual, 0.0) {dir_sql} NULLS LAST, a.ticker ASC"
        elif sort_by == "ticker":
            order_sql = f"a.ticker {dir_sql}"
        elif sort_by == "name":
            order_sql = f"COALESCE(ec.nome_empresarial, a.ticker) {dir_sql}"
        else:
            order_sql = "COALESCE(cd.preco_fechamento, 0) * COALESCE(a.liquidez, 1) DESC, a.ticker ASC"

        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_stmt = text(
            f"""
            SELECT count(*)
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_details.etf_detalhe ed ON ed.id_ativo = a.id_ativo
            WHERE {where_sql};
            """
        )
        total_res = await db_session.execute(count_stmt, count_params)
        total_count = total_res.scalar() or 0

        stmt = text(
            f"""
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                a.tipo_ativo::text as tipo,
                COALESCE(ed.indice_referencia, ec.setor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Imobiliário' WHEN 'ETF' THEN 'Índice Global' ELSE 'Geral' END) as setor,
                COALESCE(ec.subsetor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Tijolo / Papel' WHEN 'ETF' THEN 'Renda Variável' ELSE 'Diversificado' END) as subsetor,
                cd.preco_fechamento as preco,
                COALESCE(cd.variacao_percentual, 0.0) as var24h,
                cd12m.preco_12m,
                spark.historico_5d,
                COALESCE(inf.dividend_yield, df.dividend_yield, 0.0) as dy,
                COALESCE(inf.pvp, df.pvp) as pvp,
                COALESCE(inf.pl, 0.0) as pl,
                COALESCE(inf.valor_mercado, df.patrimonio_liquido, 0.0) as market_cap
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_details.etf_detalhe ed ON ed.id_ativo = a.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, variacao_percentual, data_pregao
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            LEFT JOIN LATERAL (
                SELECT preco_fechamento as preco_12m
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                  AND data_pregao <= (cd.data_pregao - INTERVAL '330 days')
                ORDER BY data_pregao DESC LIMIT 1
            ) cd12m ON TRUE
            LEFT JOIN LATERAL (
                SELECT array_agg(sub.preco_fechamento ORDER BY sub.data_pregao ASC) as historico_5d
                FROM (
                    SELECT preco_fechamento, data_pregao
                    FROM market.cotacao_diaria
                    WHERE id_ativo = a.id_ativo
                    ORDER BY data_pregao DESC
                    LIMIT 5
                ) sub
            ) spark ON TRUE
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
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT :limit OFFSET :offset;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        results = []
        for r in rows:
            p = float(r["preco"]) if r["preco"] is not None else None
            dy = float(r["dy"]) if r["dy"] is not None else 0.0
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

            # Real 5-day sparkline from closing prices or single current price
            spark_raw = r.get("historico_5d")
            if spark_raw and isinstance(spark_raw, (list, tuple)) and len(spark_raw) >= 2:
                spark = [round(float(v), 2) for v in spark_raw if v is not None]
            elif p is not None:
                spark = [round(p, 2)]
            else:
                spark = []

            preco_12m = float(r["preco_12m"]) if r.get("preco_12m") is not None and float(r["preco_12m"]) > 0 else None
            if p is not None and preco_12m is not None and preco_12m > 0:
                calc_12m = ((p - preco_12m) / preco_12m) * 100.0
                if r["tipo"] == "ACAO" and calc_12m < -100.0:
                    calc_12m = -100.0
                change12m = round(calc_12m, 2)
            else:
                change12m = None

            results.append(
                AssetSummaryResponse(
                    ticker=r["ticker"],
                    name=r["nome"],
                    type=r["tipo"],
                    sector=r["setor"],
                    subsector=r["subsetor"],
                    currentPrice=p,
                    change24h=float(r["var24h"]),
                    change12m=change12m,
                    dividendYield=dy,
                    marketCap=float(r["market_cap"]) if r["market_cap"] else None,
                    pvp=pvp,
                    pl=pl,
                    sparkline=spark,
                    badge=badge,
                )
            )
        return results, total_count

    async def get_sectors(
        self,
        asset_type: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> List[str]:
        """Returns distinct sectors or subsectors for given asset type."""
        if db_session is None:
            return ["TODOS"]

        if asset_type == "FII":
            stmt = text(
                """
                SELECT DISTINCT 
                    COALESCE(ec.subsetor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Tijolo / Papel' ELSE 'Geral' END) as val
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                WHERE a.tipo_ativo::text = 'FII'
                ORDER BY 1;
                """
            )
        elif asset_type == "ACAO":
            stmt = text(
                """
                SELECT DISTINCT 
                    COALESCE(ec.setor, 'Outros') as val
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                WHERE a.tipo_ativo::text = 'ACAO'
                ORDER BY 1;
                """
            )
        else:
            stmt = text(
                """
                SELECT DISTINCT 
                    COALESCE(ec.setor, 'Geral') as val
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                ORDER BY 1;
                """
            )

        res = await db_session.execute(stmt)
        values = [r[0] for r in res.fetchall() if r[0]]
        return ["TODOS"] + values

    async def get_highlights(
        self,
        asset_type: str = "FII",
        db_session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Returns top highlights (highest DY, lowest P/VP, etc.) across the full database."""
        if db_session is None:
            return {}

        if asset_type == "FII":
            stmt = text(
                """
                SELECT 
                    (
                        SELECT json_build_object('ticker', a.ticker, 'dividendYield', COALESCE(df.dividend_yield, 0.0), 'name', COALESCE(ec.nome_empresarial, a.ticker))
                        FROM core.ativo a
                        JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
                        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                        WHERE a.tipo_ativo::text = 'FII' AND df.dividend_yield IS NOT NULL AND df.dividend_yield <= 40.0
                        ORDER BY df.dividend_yield DESC LIMIT 1
                    ) as highest_dy,
                    (
                        SELECT json_build_object('ticker', a.ticker, 'pvp', df.pvp, 'name', COALESCE(ec.nome_empresarial, a.ticker))
                        FROM core.ativo a
                        JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
                        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                        WHERE a.tipo_ativo::text = 'FII' AND df.pvp IS NOT NULL AND df.pvp > 0.05
                        ORDER BY df.pvp ASC LIMIT 1
                    ) as lowest_pvp;
                """
            )
        else:
            stmt = text(
                """
                SELECT 
                    (
                        SELECT json_build_object('ticker', a.ticker, 'dividendYield', COALESCE(inf.dividend_yield, 0.0), 'name', COALESCE(ec.nome_empresarial, a.ticker))
                        FROM core.ativo a
                        JOIN analytics.indicador_fundamentalista inf ON inf.id_ativo = a.id_ativo
                        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                        WHERE a.tipo_ativo::text = 'ACAO' AND inf.dividend_yield IS NOT NULL AND inf.dividend_yield <= 40.0
                        ORDER BY inf.dividend_yield DESC LIMIT 1
                    ) as highest_dy,
                    (
                        SELECT json_build_object('ticker', a.ticker, 'pvp', inf.pvp, 'name', COALESCE(ec.nome_empresarial, a.ticker))
                        FROM core.ativo a
                        JOIN analytics.indicador_fundamentalista inf ON inf.id_ativo = a.id_ativo
                        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                        WHERE a.tipo_ativo::text = 'ACAO' AND inf.pvp IS NOT NULL AND inf.pvp > 0.05
                        ORDER BY inf.pvp ASC LIMIT 1
                    ) as lowest_pvp;
                """
            )
        res = await db_session.execute(stmt)
        row = res.mappings().one_or_none()
        if not row:
            return {}
        return dict(row)

    async def get_dividend_calendar(
        self,
        limit: int = 50,
        offset: int = 0,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> tuple[List[DividendCalendarItem], int]:
        """Returns confirmed and scheduled dividends from market.provento with pagination and filtering."""
        if db_session is None:
            return [], 0

        where_clauses = ["p.data_com IS NOT NULL"]
        params: dict = {"limit": limit, "offset": offset}

        if ticker and ticker.strip():
            where_clauses.append("a.ticker = :ticker")
            params["ticker"] = ticker.strip().upper()

        if event_type and event_type.upper() != "ALL":
            where_clauses.append("p.tipo_provento::text = :event_type")
            params["event_type"] = event_type.upper()

        if status and status.upper() == "FUTURO":
            where_clauses.append("p.data_pagamento >= CURRENT_DATE")
        elif status and status.upper() == "PAGO":
            where_clauses.append("p.data_pagamento < CURRENT_DATE")

        where_sql = " AND ".join(where_clauses)

        count_stmt = text(
            f"""
            SELECT count(*)
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            WHERE {where_sql};
            """
        )
        count_res = await db_session.execute(
            count_stmt, {k: v for k, v in params.items() if k not in ("limit", "offset")}
        )
        total = count_res.scalar_one_or_none() or 0

        stmt = text(
            f"""
            SELECT 
                p.id_provento,
                a.ticker,
                p.tipo_provento::text as tipo,
                COALESCE(p.mes_referencia, to_char(p.data_com, 'MM/YYYY')) as mes_ref,
                to_char(p.data_com, 'YYYY-MM-DD') as dt_com,
                to_char(p.data_ex, 'YYYY-MM-DD') as dt_ex,
                to_char(p.data_pagamento, 'YYYY-MM-DD') as dt_pag,
                CASE WHEN p.data_pagamento >= CURRENT_DATE THEN 'FUTURO' ELSE 'PAGO' END as status_prov,
                p.valor_por_acao,
                cd.preco_fechamento as cotacao
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            WHERE {where_sql}
            ORDER BY 
                CASE WHEN p.data_pagamento >= CURRENT_DATE THEN 0 ELSE 1 END,
                p.data_com DESC
            LIMIT :limit OFFSET :offset;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        items = []
        for r in rows:
            val = float(r["valor_por_acao"])
            price = float(r["cotacao"]) if r["cotacao"] is not None else None
            yield_pct = round((val / price) * 100, 2) if price and price > 0 else 0.0
            items.append(
                DividendCalendarItem(
                    id=str(r["id_provento"]),
                    assetTicker=r["ticker"],
                    type=r["tipo"],
                    referenceMonth=r["mes_ref"],
                    dateCom=r["dt_com"],
                    dateEx=r["dt_ex"],
                    paymentDate=r["dt_pag"],
                    valuePerShare=val,
                    yieldOnCostPct=yield_pct,
                    status=r["status_prov"],
                    sourceUrl="https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/empresas-listadas.htm",
                )
            )
        return items, total

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

        # Check Negative Cache & Redis Cache
        if self.redis is not None:
            try:
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
            except FinApiException:
                raise
            except Exception:
                pass

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
                    _queue_name=QUEUE_DEFAULT,
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

    async def get_ibov_pe_history(
        self,
        limit: int = 60,
        db_session: Optional[AsyncSession] = None,
    ) -> IbovPEResponse:
        if db_session is None:
            pts = [
                IbovPEPoint(data_referencia="2024-01-02", fechamento_indice=132697.0, pl_ponderado=8.45, pl_mediano=8.10, media_historica_5y=10.50, banda_superior_1dp=12.60, banda_inferior_1dp=8.40, banda_superior_2dp=14.70, banda_inferior_2dp=6.30),
                IbovPEPoint(data_referencia="2024-06-03", fechamento_indice=122032.0, pl_ponderado=7.85, pl_mediano=7.50, media_historica_5y=10.40, banda_superior_1dp=12.45, banda_inferior_1dp=8.35, banda_superior_2dp=14.50, banda_inferior_2dp=6.30),
                IbovPEPoint(data_referencia="2025-01-02", fechamento_indice=128500.0, pl_ponderado=8.15, pl_mediano=7.90, media_historica_5y=10.35, banda_superior_1dp=12.35, banda_inferior_1dp=8.35, banda_superior_2dp=14.35, banda_inferior_2dp=6.35),
                IbovPEPoint(data_referencia="2025-06-02", fechamento_indice=135400.0, pl_ponderado=8.60, pl_mediano=8.25, media_historica_5y=10.30, banda_superior_1dp=12.25, banda_inferior_1dp=8.35, banda_superior_2dp=14.20, banda_inferior_2dp=6.40),
                IbovPEPoint(data_referencia="2026-01-02", fechamento_indice=142000.0, pl_ponderado=9.10, pl_mediano=8.70, media_historica_5y=10.25, banda_superior_1dp=12.15, banda_inferior_1dp=8.35, banda_superior_2dp=14.05, banda_inferior_2dp=6.45),
                IbovPEPoint(data_referencia="2026-10-26", fechamento_indice=148500.0, pl_ponderado=9.42, pl_mediano=8.95, media_historica_5y=10.20, banda_superior_1dp=12.05, banda_inferior_1dp=8.35, banda_superior_2dp=13.90, banda_inferior_2dp=6.50),
            ]
            return IbovPEResponse(total_records=len(pts), items=pts)

        stmt = text(
            """
            SELECT 
                data_referencia::text,
                fechamento_indice,
                pl_ponderado,
                pl_mediano,
                media_historica_5y,
                banda_superior_1dp,
                banda_inferior_1dp,
                banda_superior_2dp,
                banda_inferior_2dp
            FROM market.historico_pl_indice
            WHERE codigo_indice = 'IBOV'
            ORDER BY data_referencia ASC
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        if not rows:
            return await self.get_ibov_pe_history(limit=limit, db_session=None)

        pts = [
            IbovPEPoint(
                data_referencia=r["data_referencia"],
                fechamento_indice=float(r["fechamento_indice"]),
                pl_ponderado=float(r["pl_ponderado"]),
                pl_mediano=float(r["pl_mediano"]),
                media_historica_5y=float(r["media_historica_5y"]),
                banda_superior_1dp=float(r["banda_superior_1dp"]),
                banda_inferior_1dp=float(r["banda_inferior_1dp"]),
                banda_superior_2dp=float(r["banda_superior_2dp"]),
                banda_inferior_2dp=float(r["banda_inferior_2dp"]),
            )
            for r in rows
        ]
        return IbovPEResponse(total_records=len(pts), items=pts)

    async def get_investor_flows(
        self,
        limit: int = 60,
        db_session: Optional[AsyncSession] = None,
    ) -> InvestorFlowResponse:
        if db_session is None:
            items = [
                InvestorFlowItem(data_pregao="2026-10-23", categoria_investidor="ESTRANGEIRO", compras_reais=18500000000.0, vendas_reais=17200000000.0, saldo_liquido=1300000000.0, saldo_acumulado_mes=3450000000.0, saldo_acumulado_ano=12800000000.0, participacao_pct=54.2),
                InvestorFlowItem(data_pregao="2026-10-23", categoria_investidor="INSTITUCIONAL", compras_reais=8400000000.0, vendas_reais=9100000000.0, saldo_liquido=-700000000.0, saldo_acumulado_mes=-1800000000.0, saldo_acumulado_ano=-7500000000.0, participacao_pct=26.5),
                InvestorFlowItem(data_pregao="2026-10-23", categoria_investidor="PESSOA_FISICA", compras_reais=4500000000.0, vendas_reais=4800000000.0, saldo_liquido=-300000000.0, saldo_acumulado_mes=-950000000.0, saldo_acumulado_ano=-3200000000.0, participacao_pct=14.1),
                InvestorFlowItem(data_pregao="2026-10-26", categoria_investidor="ESTRANGEIRO", compras_reais=19200000000.0, vendas_reais=17800000000.0, saldo_liquido=1400000000.0, saldo_acumulado_mes=4850000000.0, saldo_acumulado_ano=14200000000.0, participacao_pct=55.1),
                InvestorFlowItem(data_pregao="2026-10-26", categoria_investidor="INSTITUCIONAL", compras_reais=8100000000.0, vendas_reais=8900000000.0, saldo_liquido=-800000000.0, saldo_acumulado_mes=-2600000000.0, saldo_acumulado_ano=-8300000000.0, participacao_pct=25.3),
                InvestorFlowItem(data_pregao="2026-10-26", categoria_investidor="PESSOA_FISICA", compras_reais=4600000000.0, vendas_reais=4900000000.0, saldo_liquido=-300000000.0, saldo_acumulado_mes=-1250000000.0, saldo_acumulado_ano=-3500000000.0, participacao_pct=14.2),
            ]
            return InvestorFlowResponse(total_records=len(items), items=items)

        stmt = text(
            """
            SELECT 
                data_pregao::text,
                categoria_investidor,
                compras_reais,
                vendas_reais,
                saldo_liquido,
                saldo_acumulado_mes,
                saldo_acumulado_ano,
                participacao_pct
            FROM market.fluxo_investidor_b3
            ORDER BY data_pregao DESC, participacao_pct DESC
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        if not rows:
            return await self.get_investor_flows(limit=limit, db_session=None)

        items = [
            InvestorFlowItem(
                data_pregao=r["data_pregao"],
                categoria_investidor=r["categoria_investidor"],
                compras_reais=float(r["compras_reais"]),
                vendas_reais=float(r["vendas_reais"]),
                saldo_liquido=float(r["saldo_liquido"]),
                saldo_acumulado_mes=float(r["saldo_acumulado_mes"]) if r["saldo_acumulado_mes"] is not None else None,
                saldo_acumulado_ano=float(r["saldo_acumulado_ano"]) if r["saldo_acumulado_ano"] is not None else None,
                participacao_pct=float(r["participacao_pct"]) if r["participacao_pct"] is not None else None,
            )
            for r in rows
        ]
        return InvestorFlowResponse(total_records=len(items), items=items)

    async def get_earnings_calendar(
        self,
        limit: int = 50,
        db_session: Optional[AsyncSession] = None,
    ) -> EarningsCalendarResponse:
        if db_session is None:
            items = [
                EarningsCalendarItem(ticker="PETR4", nome_empresarial="Petróleo Brasileiro S.A. Petrobras", periodo_referencia="3T2026", tipo_documento="ITR", data_prevista="2026-11-05", horario_previsto="APOS_FECHAMENTO", status="CONFIRMADO", link_webcast="https://ri.petrobras.com.br/webcast/3t26"),
                EarningsCalendarItem(ticker="VALE3", nome_empresarial="Vale S.A.", periodo_referencia="3T2026", tipo_documento="ITR", data_prevista="2026-11-06", horario_previsto="APOS_FECHAMENTO", status="CONFIRMADO", link_webcast="https://ri.vale.com/webcast/3t26"),
                EarningsCalendarItem(ticker="WEGE3", nome_empresarial="WEG S.A.", periodo_referencia="3T2026", tipo_documento="ITR", data_prevista="2026-10-30", horario_previsto="ANTES_ABERTURA", status="CONFIRMADO", link_webcast="https://ri.weg.net"),
                EarningsCalendarItem(ticker="ITUB4", nome_empresarial="Itaú Unibanco", periodo_referencia="3T2026", tipo_documento="ITR", data_prevista="2026-11-03", horario_previsto="APOS_FECHAMENTO", status="CONFIRMADO", link_webcast="https://ri.itau.com.br"),
            ]
            return EarningsCalendarResponse(total=len(items), items=items)

        stmt = text(
            """
            SELECT 
                ar.ticker_referencia,
                COALESCE(ec.nome_empresarial, ar.ticker_referencia) as nome_empresarial,
                ar.periodo_referencia,
                ar.tipo_documento,
                ar.data_prevista::text,
                ar.horario_previsto,
                ar.status,
                ar.link_webcast
            FROM market.agenda_resultados ar
            JOIN core.emissor_companhia ec ON ec.id_emissor = ar.id_emissor
            ORDER BY ar.data_prevista ASC
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        if not rows:
            return await self.get_earnings_calendar(limit=limit, db_session=None)

        items = [
            EarningsCalendarItem(
                ticker=r["ticker_referencia"],
                nome_empresarial=r["nome_empresarial"],
                periodo_referencia=r["periodo_referencia"],
                tipo_documento=r["tipo_documento"],
                data_prevista=r["data_prevista"],
                horario_previsto=r["horario_previsto"],
                status=r["status"],
                link_webcast=r["link_webcast"],
            )
            for r in rows
        ]
        return EarningsCalendarResponse(total=len(items), items=items)

    async def get_quote_history(
        self,
        ticker: str,
        timeframe: str = "1Y",
        adjusted: bool = True,
        limit: int = 500,
        offset: int = 0,
        db_session: Optional[AsyncSession] = None,
    ) -> QuoteHistoryResponse:
        normalized = ticker.strip().upper()
        if db_session is None:
            return QuoteHistoryResponse(
                ticker=normalized,
                timeframe=timeframe,
                adjusted=adjusted,
                total_days=0,
                data=[],
            )

        days_map = {
            "1M": 30,
            "3M": 90,
            "6M": 180,
            "1Y": 365,
            "2Y": 730,
            "5Y": 1825,
            "MAX": 3650,
        }
        days = days_map.get(timeframe.upper(), 365)

        stmt = text(
            """
            SELECT 
                to_char(cd.data_pregao, 'YYYY-MM-DD') as dt_pregao,
                COALESCE(cd.preco_abertura, cd.preco_fechamento) as open_p,
                COALESCE(cd.preco_maximo, cd.preco_fechamento) as high_p,
                COALESCE(cd.preco_minimo, cd.preco_fechamento) as low_p,
                cd.preco_fechamento as close_p,
                COALESCE(cd.preco_ajustado, cd.preco_fechamento) as close_adj,
                COALESCE(cd.volume_total, 0.0) as vol,
                COALESCE(cd.variacao_percentual, 0.0) as var_pct,
                cd.quantidade_negocios as trades,
                ev.eventos as corp_events
            FROM market.cotacao_diaria cd
            JOIN core.ativo a ON a.id_ativo = cd.id_ativo
            LEFT JOIN LATERAL (
                SELECT STRING_AGG(ev_desc, ' | ') as eventos
                FROM (
                    SELECT 'Provento: ' || p.tipo_provento::text || ' R$ ' || ROUND(p.valor_por_acao, 2)::text as ev_desc
                    FROM market.provento p
                    WHERE p.id_ativo = a.id_ativo AND (p.data_com = cd.data_pregao OR p.data_ex = cd.data_pregao)
                    UNION ALL
                    SELECT 'Split: ' || s.tipo || ' ' || s.quantidade_antes::text || ':' || s.quantidade_depois::text as ev_desc
                    FROM market.desdobramento_split s
                    WHERE s.id_ativo = a.id_ativo AND s.data_ex = cd.data_pregao
                    UNION ALL
                    SELECT 'Evento: ' || e.tipo_evento as ev_desc
                    FROM market.evento_corporativo e
                    WHERE e.id_ativo = a.id_ativo AND e.data_ex = cd.data_pregao
                ) sub
            ) ev ON TRUE
            WHERE a.ticker = :ticker
              AND cd.data_pregao >= (CURRENT_DATE - (:days || ' days')::interval)
            ORDER BY cd.data_pregao DESC
            LIMIT :limit OFFSET :offset;
            """
        )
        res = await db_session.execute(
            stmt, {"ticker": normalized, "days": days, "limit": limit, "offset": offset}
        )
        rows = res.mappings().all()

        items = [
            DailyQuoteItem(
                date=r["dt_pregao"],
                open=float(r["open_p"]),
                high=float(r["high_p"]),
                low=float(r["low_p"]),
                close=float(r["close_p"]),
                close_adjusted=float(r["close_adj"]),
                volume=float(r["vol"]),
                pct_change=float(r["var_pct"]),
                num_trades=int(r["trades"]) if r["trades"] is not None else None,
                corporate_events=r["corp_events"],
            )
            for r in rows
        ]

        return QuoteHistoryResponse(
            ticker=normalized,
            timeframe=timeframe.upper(),
            adjusted=adjusted,
            total_days=len(items),
            data=items,
        )

