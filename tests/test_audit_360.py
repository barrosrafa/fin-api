from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.stocks.service import StockService
from app.screener.router import ScreenerQueryRequest, query_screener


def database(rows, ptax=None):
    currency, assets = MagicMock(), MagicMock()
    currency.scalar.return_value = ptax
    assets.mappings.return_value.all.return_value = rows
    return AsyncMock(execute=AsyncMock(side_effect=[currency, assets]))


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['get_us_stocks', 'get_reits'])
async def test_international_empty_database_has_no_mock_assets(method):
    assert await getattr(StockService(), method)(database([])) == []


@pytest.mark.asyncio
async def test_us_prices_are_source_backed_and_missing_ptax_is_not_invented():
    rows = [dict(ticker='AAPL', nome='Apple', setor='', preco_usd=185.5),
            dict(ticker='MSFT', nome='Microsoft', setor='', preco_usd=None)]
    result = await StockService().get_us_stocks(database(rows))
    assert result[0].price_usd == 185.5
    assert result[1].price_usd is None
    assert all(r.price_brl is None and r.ptax_rate is None for r in result)
    assert all(r.pe_ratio is None and r.dividend_yield_pct is None for r in result)


@pytest.mark.asyncio
async def test_reit_does_not_invent_indicators_or_tax_yield():
    row = dict(ticker='PLD', nome='Prologis', subtipo_reit=None, preco_usd=100,
               ffo_por_acao=0, affo_por_acao=None, p_ffo=None, p_affo=None,
               ffo_payout=None, ocupacao=None, props=None)
    result = (await StockService().get_reits(database([row], 5)))[0]
    assert result.price_brl == 500
    assert result.ffo_per_share == 0
    assert result.affo_per_share is None
    assert result.gross_dy_pct is None and result.net_dy_brl_pct is None
    assert result.properties_count is None


@pytest.mark.asyncio
async def test_screener_quality_and_filters_precede_limit_and_are_bound():
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    db = AsyncMock(execute=AsyncMock(return_value=result))
    await query_screener(ScreenerQueryRequest(sector="x' OR TRUE--", min_dy=6, limit=10), db)
    stmt, params = db.execute.call_args.args
    sql = str(stmt)
    assert sql.index('BETWEEN 0 AND 100') < sql.index('LIMIT :limit')
    assert 'ec.setor = :sector' in sql and '>= :min_dy' in sql
    assert "x' OR TRUE--" not in sql
    assert params['sector'] == "x' OR TRUE--"


@pytest.mark.parametrize('value', [0, -1, 1001])
def test_screener_rejects_unbounded_limits(value):
    with pytest.raises(ValidationError):
        ScreenerQueryRequest(limit=value)
