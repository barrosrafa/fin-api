import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from app.worker.settings import WorkerSettings, QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_BATCH
from app.worker.tasks.ingestion import refresh_ticker_data_task
from app.worker.tasks.cache import warm_cache_top_tickers_task
from app.worker.tasks.housekeeping import purge_stale_cache_task

def test_worker_settings_configuration():
    assert WorkerSettings.queue_name == QUEUE_DEFAULT
    assert WorkerSettings.max_jobs == 20
    assert len(WorkerSettings.cron_jobs) == 2
    func_names = [f.__name__ for f in WorkerSettings.functions]
    assert "refresh_ticker_data_task" in func_names
    assert "warm_cache_top_tickers_task" in func_names

@pytest.mark.asyncio
async def test_legacy_refresh_only_enqueues_durable_command():
    from uuid import uuid4
    task_id = uuid4()
    factory = MagicMock()
    session = AsyncMock()
    factory.return_value.__aenter__.return_value = session
    ctx = {"db_session_factory": factory, "collector_router": AsyncMock()}
    with patch("app.worker.tasks.ingestion.enqueue_refresh", AsyncMock(return_value={"task_id": task_id})) as enqueue:
        result = await refresh_ticker_data_task(ctx, "PETR4")
    assert result == {"status": "queued", "task_id": str(task_id)}
    enqueue.assert_awaited_once_with(session, "PETR4")
    ctx["collector_router"].collect_stock.assert_not_called()

@pytest.mark.asyncio
async def test_warm_cache_reads_database_without_scraping():
    session = AsyncMock()
    rows = MagicMock()
    rows.mappings.return_value.all.return_value = [{"ticker": "PETR4", "price": 35, "as_of": "2026-10-29"}]
    session.execute.return_value = rows
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    ctx = {"redis": AsyncMock(), "db_session_factory": factory, "collector_router": AsyncMock()}
    result = await warm_cache_top_tickers_task(ctx, ["PETR4"])
    assert result["warmed_count"] == 1
    ctx["collector_router"].collect_stock.assert_not_called()
    ctx["redis"].set.assert_called_once()
    assert "2026-10-29" in ctx["redis"].set.call_args.args[1]


@pytest.mark.asyncio
async def test_incomplete_jobs_fail_and_are_not_scheduled():
    from app.worker.tasks.calculation import calculate_sector_averages_task, recalculate_rankings_task
    from app.worker.tasks.housekeeping import refresh_clube_fii_token_task, purge_stale_cache_task
    for task in (calculate_sector_averages_task, recalculate_rankings_task, refresh_clube_fii_token_task, purge_stale_cache_task):
        assert task not in WorkerSettings.functions
        with pytest.raises(NotImplementedError):
            await task({})
