import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.service import MarketService


@pytest.mark.asyncio
@pytest.mark.parametrize('period, expected', [
    ('5Y', datetime.date(2021, 10, 31)),
    ('MAX', datetime.date.min),
])
async def test_history_uses_full_requested_period(period, expected):
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result
    now = datetime.datetime(2026, 10, 31)
    with patch('app.market.service.datetime.datetime') as clock:
        clock.now.return_value = now
        await MarketService().get_quote_history('PETR4', timeframe=period, db_session=db)
    params = db.execute.call_args.args[1]
    assert params['start_date'] == expected


@pytest.mark.asyncio
async def test_csv_exports_all_history_with_unknown_first_variation():
    from app.market.router import export_ticker_quote_history
    from app.market.schemas import DailyQuoteItem, QuoteHistoryResponse

    service = AsyncMock()
    service.get_quote_history.return_value = QuoteHistoryResponse(
        ticker="PETR4", timeframe="MAX", adjusted=True, total_days=1,
        data=[DailyQuoteItem(date="2000-01-03", open=1, high=1, low=1,
                            close=1, close_adjusted=1, volume=1, pct_change=None)],
    )
    response = await export_ticker_quote_history(
        ticker="PETR4", db=AsyncMock(), service=service, timeframe="MAX", adjusted=True,
    )
    assert service.get_quote_history.call_args.kwargs['limit'] is None
    assert b"2000-01-03" in response.body
