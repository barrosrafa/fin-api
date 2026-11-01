from unittest.mock import AsyncMock, MagicMock

import pytest

from app.stocks.service import StockService


@pytest.mark.asyncio
async def test_missing_verified_payments_returns_an_empty_matrix():
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = result
    response = await StockService().get_dividend_matrix("PETR4", db_session=session)
    assert response.years == []
    assert response.matrix == []
