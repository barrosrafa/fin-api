import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.exceptions import UnauthorizedException, ResourceNotFoundException, FinApiException
from app.market.service import MarketService
from app.portfolio.service import PortfolioService
from app.billing.service import BillingService
from app.billing.schemas import WebhookEvent
from app.auth.models import SubscriptionTier

@pytest.mark.asyncio
async def test_negative_caching_returns_422():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=True)

    mock_redis = AsyncMock()
    # Negative cache key hit
    mock_redis.get = AsyncMock(side_effect=lambda k: b"1" if "failed_ticker" in k else None)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
    )

    with pytest.raises(FinApiException) as exc_info:
        await service.get_quote("BROKEN3")

    assert exc_info.value.status_code == 422
    assert "temporariamente indisponíveis" in exc_info.value.message

@pytest.mark.asyncio
async def test_portfolio_summary_idor_protection():
    mock_db = AsyncMock()
    # Mock query returns empty (wallet does not belong to this user)
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Check wallet ownership check
    mock_wallet_check = MagicMock()
    mock_wallet_check.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_wallet_check)

    service = PortfolioService()

    with pytest.raises(ResourceNotFoundException):
        await service.get_portfolio_summary(
            wallet_id="99999999-9999-9999-9999-999999999999",
            user_id="unauthorized_user_123",
            db_session=mock_db,
        )
