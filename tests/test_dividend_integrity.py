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


@pytest.mark.asyncio
@pytest.mark.parametrize("price,expected_yield", [(52.71, 2.56), (None, None)])
async def test_matrix_uses_real_quote_and_preserves_per_share_precision(price, expected_yield):
    months = MagicMock()
    months.mappings.return_value.all.return_value = [
        {"ano": 2026, "mes": 11, "total_mes": 0.67407131},
        {"ano": 2026, "mes": 12, "total_mes": 0.67407131},
    ]
    quote = MagicMock()
    quote.scalar.return_value = price
    session = AsyncMock()
    session.execute.side_effect = [months, quote]
    result = await StockService().get_dividend_matrix("PETR4", db_session=session)
    assert result.matrix[0].months[10] == 0.67407131
    assert result.matrix[0].annual_total == 1.34814262
    assert result.matrix[0].yield_on_cost_pct == expected_yield
