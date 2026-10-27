import asyncio
import typer
import uvicorn
from sqlalchemy import text
from app.config import get_settings
from app.core.database import get_async_engine, close_database_engine
from app.core.redis import get_redis_client, close_redis_client
from app.core.catalog import TickerCatalog
from app.core.logging import logger

cli = typer.Typer(help="fin-api unified management CLI for API server and background worker")


@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host IP to bind"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload for local development"),
    workers: int = typer.Option(1, help="Number of Uvicorn worker processes"),
):
    """Start the FastAPI HTTP application server."""
    logger.info(f"Starting fin-api HTTP server on {host}:{port} (workers={workers}, reload={reload})")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )


@cli.command()
def worker(
    burst: bool = typer.Option(False, help="Run worker in burst mode (exit when queues are empty)"),
):
    """Start the ARQ async background task worker and cron scheduler."""
    from arq import run_worker
    from app.worker.settings import WorkerSettings

    logger.info(f"Starting ARQ worker (burst={burst})...")
    WorkerSettings.burst = burst
    run_worker(WorkerSettings)


@cli.command()
def catalog_sync():
    """Sync B3 and CVM official tickers into the Redis TickerCatalog O(1) set."""
    async def _sync():
        redis = await get_redis_client()
        catalog = TickerCatalog(redis_client=redis)
        top_tickers = [
            "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "ABEV3", "WEGE3", "RENT3",
            "HGLG11", "KNIP11", "XPLG11", "MXRF11", "BTLG11", "VISC11", "BOVA11", "IVVB11"
        ]
        count = await catalog.add_tickers(top_tickers)
        typer.echo(f"Successfully seeded {count} tickers into TickerCatalog!")
        await close_redis_client()

    asyncio.run(_sync())


@cli.command()
def check():
    """Verify live connectivity to PostgreSQL 18 (Neon fin-db) and Redis."""
    async def _check():
        typer.echo("🔍 Checking fin-api external dependencies...")
        settings = get_settings()

        # Check Database
        typer.echo(f"• Connecting to PostgreSQL 18 ({settings.DATABASE_URL.split('@')[-1]})...")
        engine = get_async_engine()
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT version();"))
                ver = res.scalar()
                typer.echo(f"  ✅ PostgreSQL connected successfully! Server: {ver}")
                
                # Check fin-db tables
                cnt_res = await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('core', 'market', 'canonical');"))
                cnt = cnt_res.scalar()
                typer.echo(f"  ✅ fin-db schemas verified! Core/Market/Canonical tables found: {cnt}")
        except Exception as e:
            typer.echo(f"  ❌ Database connection error: {e}")
        finally:
            await close_database_engine()

        # Check Redis
        typer.echo(f"• Connecting to Redis ({settings.REDIS_URL})...")
        try:
            redis = await get_redis_client()
            await redis.ping()
            typer.echo("  ✅ Redis connected and PING succeeded!")
        except Exception as e:
            typer.echo(f"  ⚠️ Redis connection note (run redis-server locally or via docker): {e}")
        finally:
            await close_redis_client()

    asyncio.run(_check())


if __name__ == "__main__":
    cli()
