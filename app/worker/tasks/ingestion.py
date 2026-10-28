import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy import text
from app.core.logging import logger


async def refresh_ticker_data_task(
    ctx: Dict[str, Any],
    ticker: str,
    asset_class: str = "stock",
) -> Dict[str, Any]:
    """
    ARQ worker task to collect fresh market quote and fundamental indicators,
    persist them to fin-db, update Redis cache, and publish progress via Redis Pub/Sub.
    """
    router = ctx.get("collector_router")
    redis = ctx.get("redis")
    db_factory = ctx.get("db_session_factory")

    normalized_ticker = ticker.strip().upper()
    logger.info(f"Starting refresh_ticker_data_task for {normalized_ticker} ({asset_class})")

    # Step 1: Update sync status to in_progress
    if redis is not None:
        await redis.set(
            f"sync:{normalized_ticker}",
            json.dumps({"status": "in_progress", "progress": 0.25}),
            ex=300,
        )

    # Step 2: Route collection by asset class with negative cache tracking
    try:
        if asset_class == "fii":
            canonical = await router.collect_fii(normalized_ticker)
        elif asset_class == "fund":
            canonical = await router.collect_fund(normalized_ticker)
        elif asset_class == "etf":
            canonical = await router.collect_etf(normalized_ticker)
        else:
            canonical = await router.collect_stock(normalized_ticker)
            
        # Success: reset failure counter
        if redis is not None:
            await redis.delete(f"failed_count:{normalized_ticker}")
            await redis.delete(f"failed_ticker:{normalized_ticker}")
    except Exception as e:
        logger.error(f"Collection failed across all sources for {normalized_ticker}: {e}")
        if redis is not None:
            fail_count = await redis.incr(f"failed_count:{normalized_ticker}")
            if fail_count >= 3:
                # Set 10-minute negative cache triggering HTTP 422
                await redis.set(f"failed_ticker:{normalized_ticker}", "1", ex=600)
            await redis.set(
                f"sync:{normalized_ticker}",
                json.dumps({"status": "failed", "progress": 0.0, "message": str(e)}),
                ex=300,
            )
            await redis.publish(f"channel:sync:{normalized_ticker}", json.dumps({"status": "failed"}))
        raise

    # Step 3: Upsert into PostgreSQL 18 / TimescaleDB (market.cotacao_diaria)
    data_pregao = canonical.collected_at.date() if hasattr(canonical, "collected_at") else datetime.now(timezone.utc).date()
    db_success = False

    if db_factory is not None:
        async with db_factory() as session:
            stmt = text(
                """
                INSERT INTO market.cotacao_diaria (
                    id_ativo, data_pregao, preco_fechamento, variacao_percentual,
                    volume_total
                )
                VALUES (
                    (SELECT id_ativo FROM core.ativo WHERE ticker = :ticker LIMIT 1),
                    :data_pregao, :price, :change_pct, :volume
                )
                ON CONFLICT (id_ativo, data_pregao) DO UPDATE SET
                    preco_fechamento = EXCLUDED.preco_fechamento,
                    variacao_percentual = EXCLUDED.variacao_percentual,
                    volume_total = EXCLUDED.volume_total
                """
            )
            try:
                await session.execute(
                    stmt,
                    {
                        "ticker": normalized_ticker,
                        "data_pregao": data_pregao,
                        "price": canonical.price,
                        "change_pct": canonical.change_pct,
                        "volume": canonical.volume,
                    },
                )
                await session.commit()
                db_success = True
            except Exception as e:
                logger.error(f"DB upsert failure for {normalized_ticker}: {e}")
                if redis is not None:
                    await redis.set(
                        f"sync:{normalized_ticker}",
                        json.dumps({"status": "failed", "progress": 0.0, "message": f"Database write failed: {str(e)}"}),
                        ex=300,
                    )
                    await redis.publish(f"channel:sync:{normalized_ticker}", json.dumps({"status": "failed"}))
                raise

    # Step 4: Populate Redis cache
    quote_data = canonical.model_dump()
    if redis is not None:
        await redis.set(
            f"quote:{normalized_ticker}",
            json.dumps(quote_data, default=str),
            ex=60,  # 60s quote cache TTL
        )
        await redis.set(
            f"sync:{normalized_ticker}",
            json.dumps({"status": "completed", "progress": 1.0, "result": quote_data}, default=str),
            ex=300,
        )
        # Notify SSE listeners via Redis Pub/Sub
        await redis.publish(f"channel:sync:{normalized_ticker}", json.dumps({"status": "completed"}))

    logger.info(f"Finished refresh_ticker_data_task for {normalized_ticker}: price={canonical.price}")
    return {
        "status": "success",
        "ticker": normalized_ticker,
        "price": canonical.price,
        "source": canonical.source,
    }
