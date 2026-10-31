"""ARQ cache jobs read published database data; collection belongs to ingestion."""
import json
from sqlalchemy import text


async def warm_cache_top_tickers_task(ctx, tickers=None):
    redis = ctx["redis"]
    async with ctx["db_session_factory"]() as session:
        rows = (await session.execute(text("""
            SELECT DISTINCT ON (a.ticker) a.ticker, cd.preco_fechamento AS price,
                   cd.data_pregao::text AS as_of
            FROM market.cotacao_diaria cd
            JOIN core.ativo a ON a.id_ativo=cd.id_ativo
            WHERE cd.preco_fechamento > 0
              AND (:all_tickers OR a.ticker = ANY(CAST(:tickers AS text[])))
            ORDER BY a.ticker, cd.data_pregao DESC
            LIMIT 100
        """), {"all_tickers": tickers is None, "tickers": tickers or []})).mappings().all()
    for row in rows:
        # Preserve source date: writing a cache does not refresh market data.
        await redis.set(f"finance:quote:{row['ticker']}", json.dumps(dict(row), default=str), ex=300)
    return {"status": "success", "warmed_count": len(rows)}


async def sync_ticker_catalog_task(ctx):
    async with ctx["db_session_factory"]() as session:
        tickers = (await session.execute(text("SELECT ticker FROM core.ativo WHERE ticker IS NOT NULL"))).scalars().all()
    count = await ctx["ticker_catalog"].add_tickers(tickers)
    return {"status": "success", "added_tickers": count}
