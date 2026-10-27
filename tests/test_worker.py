import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from app.worker.settings import WorkerSettings, QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_BATCH
from app.worker.tasks.ingestion import refresh_ticker_data_task
from app.worker.tasks.cache import warm_cache_top_tickers_task
from app.worker.tasks.housekeeping import purge_stale_cache_task

def test_worker_settings_configuration():
    assert WorkerSettings.queue_name == QUEUE_DEFAULT
    assert WorkerSettings.max_jobs == 20
    assert len(WorkerSettings.cron_jobs) >= 3
    func_names = [f.__name__ for f in WorkerSettings.functions]
    assert "refresh_ticker_data_task" in func_names
    assert "warm_cache_top_tickers_task" in func_names

@pytest.mark.asyncio
async def test_refresh_ticker_data_task_success():
    mock_ctx = {
        "redis": AsyncMock(),
        "db_session_factory": MagicMock(),
        "collector_router": AsyncMock(),
    }
    
    mock_canonical_quote = MagicMock()
    mock_canonical_quote.ticker = "PETR4"
    mock_canonical_quote.price = 37.10
    mock_canonical_quote.change_pct = 1.64
    mock_canonical_quote.volume = 1200000000.0
    mock_canonical_quote.p_l = 4.2
    mock_canonical_quote.dy_pct = 14.1
    mock_canonical_quote.p_vp = 0.98
    mock_canonical_quote.source = "statusinvest.com.br"
    mock_canonical_quote.model_dump.return_value = {
        "ticker": "PETR4",
        "price": 37.10,
        "change_pct": 1.64,
        "volume": 1200000000.0,
        "source": "statusinvest.com.br",
    }

    mock_ctx["collector_router"].collect_stock = AsyncMock(return_value=mock_canonical_quote)

    result = await refresh_ticker_data_task(mock_ctx, ticker="PETR4", asset_class="stock")

    assert result["status"] == "success"
    assert result["ticker"] == "PETR4"
    assert result["price"] == 37.10
    
    # Assert Redis was populated with quote and sync status was marked completed
    mock_ctx["redis"].set.assert_any_call("quote:PETR4", ANY, ex=60)
    mock_ctx["redis"].set.assert_any_call("sync:PETR4", ANY, ex=300)

@pytest.mark.asyncio
async def test_warm_cache_top_tickers_task():
    mock_ctx = {
        "redis": AsyncMock(),
        "collector_router": AsyncMock(),
    }
    mock_quote = MagicMock()
    mock_quote.model_dump.return_value = {"ticker": "VALE3", "price": 60.0}
    mock_ctx["collector_router"].collect_stock = AsyncMock(return_value=mock_quote)

    result = await warm_cache_top_tickers_task(mock_ctx, tickers=["VALE3", "PETR4"])
    assert result["warmed_count"] == 2
