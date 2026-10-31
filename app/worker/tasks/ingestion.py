"""Compatibility command for previously queued ARQ jobs, with no collection."""
from app.ingestion.commands import enqueue_refresh


async def refresh_ticker_data_task(ctx, ticker, asset_class="stock"):
    async with ctx["db_session_factory"]() as session:
        task = await enqueue_refresh(session, ticker)
    return {"status": "queued", "task_id": str(task["task_id"])}
