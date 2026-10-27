import pytest
from unittest.mock import AsyncMock, MagicMock
from app.config import Settings
from app.core.catalog import TickerCatalog
from app.core.circuit_breaker import RedisCircuitBreaker
from app.core.exceptions import (
    ResourceNotFoundException,
    AssetNotListedException,
    CollectorCircuitOpenException,
)

def test_settings_load():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
        REDIS_URL="redis://localhost:6379/1",
        DEBUG=True,
    )
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.REDIS_URL == "redis://localhost:6379/1"
    assert settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD == 5

@pytest.mark.asyncio
async def test_ticker_catalog_validation():
    mock_redis = AsyncMock()
    # Mock sismember: returns 1 for PETR4, 0 for INVALID99
    mock_redis.sismember = AsyncMock(side_effect=lambda key, ticker: ticker == "PETR4")
    mock_redis.sadd = AsyncMock()

    catalog = TickerCatalog(redis_client=mock_redis)
    
    assert await catalog.is_valid("PETR4") is True
    assert await catalog.is_valid("INVALID99") is False

    await catalog.add_tickers(["VALE3", "ITUB4"])
    mock_redis.sadd.assert_called_once_with("catalog:tickers:b3", "VALE3", "ITUB4")

@pytest.mark.asyncio
async def test_circuit_breaker_transitions():
    mock_redis = AsyncMock()
    # Initially 0 failures and not open
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=5)
    mock_redis.set = AsyncMock()

    breaker = RedisCircuitBreaker(
        domain="statusinvest.com.br",
        redis_client=mock_redis,
        failure_threshold=5,
        cooldown_seconds=600,
    )

    # Initial state should be allowed
    assert await breaker.can_execute() is True

    # Record failure reaching threshold
    await breaker.record_failure()
    mock_redis.set.assert_called_with("cb:statusinvest.com.br:open", "1", ex=600)

    # When open flag is set, can_execute should be False
    mock_redis.get = AsyncMock(return_value=b"1")
    assert await breaker.can_execute() is False

def test_custom_exceptions():
    exc = AssetNotListedException("TICKER99")
    assert exc.status_code == 404
    assert "TICKER99" in exc.detail
    assert exc.ticker == "TICKER99"
