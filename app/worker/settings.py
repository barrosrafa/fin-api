from arq.connections import RedisSettings
from arq.cron import cron
from app.config import get_settings
from app.core.redis import get_redis_client, close_redis_client
from app.core.database import get_session_factory, close_database_engine
from app.core.catalog import TickerCatalog
from app.collectors.router import CollectorRouter
from app.worker.tasks.ingestion import refresh_ticker_data_task
from app.worker.tasks.cache import warm_cache_top_tickers_task, sync_ticker_catalog_task
from app.worker.tasks.calculation import calculate_sector_averages_task, recalculate_rankings_task
from app.worker.tasks.housekeeping import refresh_clube_fii_token_task, purge_stale_cache_task
from app.core.logging import logger

QUEUE_HIGH = "high_priority"
QUEUE_DEFAULT = "default"
QUEUE_BATCH = "batch"


async def startup(ctx):
    logger.info("Initializing ARQ worker context...")
    redis = await get_redis_client()
    db_factory = get_session_factory()
    catalog = TickerCatalog(redis_client=redis)
    router = CollectorRouter()

    ctx["redis"] = redis
    ctx["db_session_factory"] = db_factory
    ctx["ticker_catalog"] = catalog
    ctx["collector_router"] = router
    logger.info("ARQ worker ready to process tasks.")


async def shutdown(ctx):
    logger.info("Shutting down ARQ worker...")
    if "collector_router" in ctx:
        await ctx["collector_router"].close()
    await close_redis_client()
    await close_database_engine()
    logger.info("ARQ worker shutdown complete.")


class WorkerSettings:
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    queue_name = QUEUE_DEFAULT
    max_jobs = settings.ARQ_MAX_JOBS

    functions = [
        refresh_ticker_data_task,
        warm_cache_top_tickers_task,
        sync_ticker_catalog_task,
        calculate_sector_averages_task,
        recalculate_rankings_task,
        refresh_clube_fii_token_task,
        purge_stale_cache_task,
    ]

    cron_jobs = [
        cron(warm_cache_top_tickers_task, hour=9, minute=30, run_at_startup=False),
        cron(sync_ticker_catalog_task, hour=6, minute=0, run_at_startup=False),
        cron(calculate_sector_averages_task, hour=19, minute=0, run_at_startup=False),
        cron(recalculate_rankings_task, hour=20, minute=0, run_at_startup=False),
        cron(refresh_clube_fii_token_task, hour={0, 6, 12, 18}, minute=0, run_at_startup=False),
    ]

    on_startup = startup
    on_shutdown = shutdown
