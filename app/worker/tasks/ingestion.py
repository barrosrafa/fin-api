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

    # Step 2: Route collection by asset class
    if asset_class == "fii":
        canonical = await router.collect_fii(normalized_ticker)
    elif asset_class == "fund":
        canonical = await router.collect_fund(normalized_ticker)
    elif asset_class == "etf":
        canonical = await router.collect_etf(normalized_ticker)
    else:
        canonical = await router.collect_stock(normalized_ticker)

    # Step 3: Upsert into PostgreSQL 18 / TimescaleDB (market.cotacao_diaria)
    if db_factory is not None:
        async with db_factory() as session:
            stmt = text(
                """
                INSERT INTO market.cotacao_diaria (
                    id_ativo, data_pregao, preco_fechamento, variacao_pct,
                    volume_financeiro, fonte, atualizado_em
                )
                VALUES (
                    (SELECT id_ativo FROM core.ativo WHERE codigo = :ticker LIMIT 1),
                    CURRENT_DATE, :price, :change_pct, :volume, :source, NOW()
                )
                ON CONFLICT (id_ativo, data_pregao) DO UPDATE SET
                    preco_fechamento = EXCLUDED.preco_fechamento,
                    variacao_pct = EXCLUDED.variacao_pct,
                    volume_financeiro = EXCLUDED.volume_financeiro,
                    fonte = EXCLUDED.fonte,
                    atualizado_em = NOW()
                """
            )
            try:
                await session.execute(
                    stmt,
                    {
                        "ticker": normalized_ticker,
                        "price": canonical.price,
                        "change_pct": canonical.change_pct,
                        "volume": canonical.volume,
                        "source": canonical.source,
                    },
                )
                await session.commit()
            except Exception as e:
                logger.warning(f"DB upsert warning for {normalized_ticker}: {e}")

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
