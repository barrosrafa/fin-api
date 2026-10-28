import asyncio
import json
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Response, status, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis
from arq.connections import create_pool, RedisSettings

from app.config import get_settings, Settings
from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.core.catalog import TickerCatalog
from app.market.service import MarketService
from app.market.schemas import (
    QuoteResponse,
    SyncStatusResponse,
    IndicatorsResponse,
    BenchmarkItem,
    AssetSummaryResponse,
    DividendCalendarItem,
    IbovPEResponse,
    InvestorFlowResponse,
    EarningsCalendarResponse,
)

router = APIRouter(prefix="/market", tags=["Market"])


async def get_market_service(
    settings: Annotated[Settings, Depends(get_settings)],
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
) -> MarketService:
    catalog = TickerCatalog(redis_client=redis)
    # Lazy ARQ connection pool
    try:
        arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    except Exception:
        arq_pool = None

    return MarketService(
        ticker_catalog=catalog,
        redis_client=redis,
        arq_pool=arq_pool,
    )


@router.get("/benchmarks", response_model=list[BenchmarkItem])
async def get_market_benchmarks(
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    service = MarketService()
    return await service.get_benchmarks(db_session=db)


@router.get("/assets", response_model=list[AssetSummaryResponse])
async def get_market_assets(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_type: Optional[str] = None,
    limit: int = 50,
):
    service = MarketService()
    return await service.get_assets(asset_type=asset_type, limit=limit, db_session=db)


@router.get("/dividends", response_model=list[DividendCalendarItem])
async def get_dividend_calendar(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = 15,
):
    service = MarketService()
    return await service.get_dividend_calendar(limit=limit, db_session=db)


@router.get("/ibov-pe-history", response_model=IbovPEResponse)
async def get_ibov_pe_history(
    limit: int = 60,
    db: AsyncSession = Depends(get_async_session),
):
    """Série histórica do P/L Ponderado do Ibovespa com média de 5 anos e bandas de +-1 e +-2 desvios padrão."""
    service = MarketService()
    return await service.get_ibov_pe_history(limit=limit, db_session=db)


@router.get("/investor-flows", response_model=InvestorFlowResponse)
async def get_investor_flows(
    limit: int = 60,
    db: AsyncSession = Depends(get_async_session),
):
    """Participação e fluxo líquido de investidores na B3 (Estrangeiro, Institucional, Pessoa Física, Instituições Financeiras)."""
    service = MarketService()
    return await service.get_investor_flows(limit=limit, db_session=db)


@router.get("/earnings-calendar", response_model=EarningsCalendarResponse)
async def get_earnings_calendar(
    limit: int = 50,
    db: AsyncSession = Depends(get_async_session),
):
    """Agenda de divulgação de resultados trimestrais (DFP/ITR) e webcasts com investidores."""
    service = MarketService()
    return await service.get_earnings_calendar(limit=limit, db_session=db)


@router.get("/news")
async def get_market_news(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(20, ge=1, le=100),
):
    """Retorna eventos e notícias corporativas reais com dados oficiais da CVM/B3."""
    stmt = text("""
        SELECT 
            p.id_provento as id,
            a.ticker,
            COALESCE(ec.nome_empresarial, a.ticker) as empresa,
            p.tipo_provento,
            p.valor_por_acao,
            p.data_com,
            p.data_pagamento
        FROM market.provento p
        JOIN core.ativo a ON a.id_ativo = p.id_ativo
        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
        ORDER BY p.data_com DESC
        LIMIT :limit;
    """)
    res = await db.execute(stmt, {"limit": limit})
    rows = res.mappings().all()

    news_items = []
    for r in rows:
        tipo_prov = r["tipo_provento"] or "DIVIDENDO"
        val = float(r["valor_por_acao"]) if r["valor_por_acao"] else 0.0
        data_com_str = r["data_com"].strftime("%d/%m/%Y") if r["data_com"] else "Recente"
        data_pag_str = r["data_pagamento"].strftime("%d/%m/%Y") if r["data_pagamento"] else "A definir"

        titulo = f"{r['ticker']} aprova pagamento de {tipo_prov.lower()} de R$ {val:.4f} por cota"
        resumo = f"Aprovada distribuição de proventos aos detentores com data base (data-com) em {data_com_str} e liquidação financeira prevista para {data_pag_str}."

        news_items.append({
            "id": str(r["id"]),
            "ticker": r["ticker"],
            "empresa": r["empresa"],
            "titulo": titulo,
            "tipo": "DIVIDENDO" if "DIV" in tipo_prov else "RESULTADO",
            "sentimento": "POSITIVO",
            "data_hora": f"Data-Com: {data_com_str}",
            "resumo": resumo,
            "cvm_protocolo": f"B3-PROV-{r['ticker']}-{r['id']}",
        })

    return {"total": len(news_items), "items": news_items}


@router.get("/{ticker}", response_model=QuoteResponse)
async def get_market_quote(
    ticker: str,
    response: Response,
    service: Annotated[MarketService, Depends(get_market_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_class: str = "stock",
):
    result = await service.get_quote(ticker=ticker, asset_class=asset_class, db_session=db)
    if result.status == "syncing":
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/{ticker}/sync-status", response_model=SyncStatusResponse)
async def get_ticker_sync_status(
    ticker: str,
    service: Annotated[MarketService, Depends(get_market_service)],
):
    return await service.get_sync_status(ticker)


@router.get("/{ticker}/indicators", response_model=IndicatorsResponse)
async def get_market_indicators(
    ticker: str,
    service: Annotated[MarketService, Depends(get_market_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    return await service.get_indicators(ticker=ticker, db_session=db)


@router.get("/{ticker}/stream")
async def stream_ticker_sync_progress(
    ticker: str,
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
):
    normalized = ticker.strip().upper()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"channel:sync:{normalized}")

    async def event_generator():
        try:
            # Send initial state
            raw = await redis.get(f"sync:{normalized}")
            if raw:
                yield {"event": "status", "data": raw.decode("utf-8") if isinstance(raw, bytes) else raw}

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield {"event": "status", "data": data}
                    payload = json.loads(data)
                    if payload.get("status") in ("completed", "failed"):
                        break
                await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(f"channel:sync:{normalized}")
            await pubsub.close()

    return EventSourceResponse(event_generator())



