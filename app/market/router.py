import asyncio
import json
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Response, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from arq.connections import create_pool, RedisSettings

from app.config import get_settings, Settings
from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.core.catalog import TickerCatalog
from app.market.service import MarketService
from app.market.schemas import QuoteResponse, SyncStatusResponse, IndicatorsResponse

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
