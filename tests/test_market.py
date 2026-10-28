import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.market.service import MarketService
from app.market.schemas import QuoteResponse, SyncStatusResponse, ScreenerFilter
from app.core.exceptions import AssetNotListedException

@pytest.mark.asyncio
async def test_cold_start_invalid_ticker_returns_404():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=False)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=AsyncMock(),
        arq_pool=AsyncMock(),
    )

    with pytest.raises(AssetNotListedException) as exc_info:
        await service.get_quote("NONEXIST99")

    assert exc_info.value.status_code == 404
    assert exc_info.value.ticker == "NONEXIST99"

@pytest.mark.asyncio
async def test_quote_cache_hit_returns_fresh():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=True)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b'{"ticker":"PETR4","price":37.10,"change_pct":1.64,"volume":1200000000.0}')

    mock_arq = AsyncMock()

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
        arq_pool=mock_arq,
    )

    response = await service.get_quote("PETR4")
    assert response.status == "fresh"
    assert response.quote.ticker == "PETR4"
    assert response.quote.price == 37.10
    mock_arq.enqueue_job.assert_not_called()

@pytest.mark.asyncio
async def test_quote_cache_miss_db_hit_returns_stale_and_enqueues():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=True)

    mock_redis = AsyncMock()
    # Cache miss
    mock_redis.get = AsyncMock(return_value=None)

    mock_arq = AsyncMock()
    mock_arq.enqueue_job = AsyncMock(return_value="job_abc123")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {
        "ticker": "VALE3",
        "preco_fechamento": 60.50,
        "variacao_pct": -0.82,
        "volume_financeiro": 800000000.0,
        "atualizado_em": "2026-10-25T18:00:00Z",
    }
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
        arq_pool=mock_arq,
    )

    response = await service.get_quote("VALE3", db_session=mock_db)
    assert response.status == "stale"
    assert response.quote.ticker == "VALE3"
    assert response.quote.price == 60.50
    mock_arq.enqueue_job.assert_called_once_with(
        "refresh_ticker_data_task",
        "VALE3",
        "stock",
        _queue_name="default",
    )

@pytest.mark.asyncio
async def test_quote_total_miss_returns_202_accepted():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=True)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    mock_arq = AsyncMock()
    mock_arq.enqueue_job = AsyncMock(return_value="job_new_xyz")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
        arq_pool=mock_arq,
    )

    response = await service.get_quote("NEWIPO3", db_session=mock_db)
    assert response.status == "syncing"
    assert response.sync_id == "job_new_xyz"
    assert "processo de coleta inicial" in response.message
    mock_arq.enqueue_job.assert_called_once_with(
        "refresh_ticker_data_task",
        "NEWIPO3",
        "stock",
        _queue_name="default",
    )
