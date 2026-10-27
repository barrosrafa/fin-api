import json
from typing import Dict, Any, List
from app.core.logging import logger

DEFAULT_TOP_TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "ABEV3", "WEGE3", "RENT3",
    "HGLG11", "KNIP11", "XPLG11", "MXRF11", "BTLG11", "VISC11", "BOVA11", "IVVB11"
]


async def warm_cache_top_tickers_task(
    ctx: Dict[str, Any],
    tickers: List[str] = None,
) -> Dict[str, Any]:
    """
    Pre-warms the Redis cache for highest-volume B3 tickers before market opening.
    """
    tickers_to_warm = tickers or DEFAULT_TOP_TICKERS
    router = ctx.get("collector_router")
    redis = ctx.get("redis")

    warmed = 0
    for ticker in tickers_to_warm:
        try:
            quote = await router.collect_stock(ticker)
            if redis is not None:
                await redis.set(
                    f"quote:{ticker.upper()}",
                    json.dumps(quote.model_dump(), default=str),
                    ex=300,
                )
            warmed += 1
        except Exception as e:
            logger.warning(f"Failed to pre-warm cache for {ticker}: {e}")

    logger.info(f"Pre-warmed cache for {warmed}/{len(tickers_to_warm)} tickers")
    return {"status": "success", "warmed_count": warmed}


async def sync_ticker_catalog_task(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Daily sync of B3/CVM official tickers into the O(1) Redis TickerCatalog.
    """
    catalog = ctx.get("ticker_catalog")
    if catalog is not None:
        count = await catalog.add_tickers(DEFAULT_TOP_TICKERS)
        logger.info(f"Synced {count} tickers into TickerCatalog")
        return {"status": "success", "added_tickers": count}
    return {"status": "skipped", "reason": "no_catalog_in_context"}
