from decimal import Decimal as D
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import json
import pytest
from pydantic import ValidationError
from app.calculations.pnl import Position
from app.calculations.money import money
from app.portfolio.service import PortfolioService
from app.portfolio.schemas import TransactionCreate


def test_sdd_cost_fees_realized_and_unrealized_vector():
    bought = Position().buy("100", "10", "5")
    assert bought.cost == D("1005")
    assert bought.average_price == D("10.05")
    sold = bought.sell("40", "12", "2")
    assert sold.quantity == 60
    assert sold.cost == 603
    assert sold.realized == 76
    assert sold.unrealized("11") == 57
    assert sold.sell("60", "11").cost == 0


def test_fractional_buy_partial_sell_conserves_cost_and_cash():
    position = Position().buy("0.3", "10.10", "0.07")
    before = position.cost
    sold = position.sell("0.1", "11.20", "0.02")
    assert sold.cost + (D("1.12") - D("0.02") - sold.realized) == before
    assert sold.quantity == D("0.2")
    assert money(D("1.005")) == D("1.01")
    assert money(D("-1.005")) == D("-1.01")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "-1", "0", "1e-9", "1e30"])
def test_reject_invalid_buy_quantity(bad):
    with pytest.raises(ValueError):
        Position().buy(bad, "10")


def test_cannot_sell_more_than_held_or_treat_negative_buy_as_sale():
    with pytest.raises(ValueError):
        Position().sell("1", "10")
    with pytest.raises(ValueError):
        PortfolioService.compute_new_average_price(10, 20, -1, 10)
    with pytest.raises(ValueError):
        Position().buy(1, 10, -1)


@pytest.mark.parametrize("field,bad", [("quantidade", "NaN"), ("quantidade", "1.0000001"), ("preco_unitario", "Infinity"), ("preco_unitario", "0"), ("taxas", "-1"), ("taxas", "NaN")])
def test_transaction_rejects_invalid_values(field, bad):
    values = dict(ticker="PETR4", tipo="COMPRA", quantidade="1", preco_unitario="10", taxas="0", data_operacao=date.today())
    values[field] = bad
    with pytest.raises(ValidationError):
        TransactionCreate(**values)


def db_for_positions():
    check, positions = MagicMock(), MagicMock()
    check.scalar_one_or_none.return_value = "wallet"
    positions.mappings.return_value.all.return_value = [
        {"ticker": "A", "quantidade": D("100"), "preco_medio": D("10.05"), "tipo_ativo": "ACAO"},
        {"ticker": "B", "quantidade": D("60"), "preco_medio": D("10.05"), "tipo_ativo": "ACAO"},
    ]
    return AsyncMock(execute=AsyncMock(side_effect=[check, positions]))


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [None, b"invalid", b'{"price":"NaN"}', b'{"price":"Infinity"}', b'{"price":-1}', b'{"price":10}'])
async def test_missing_or_unproven_cache_never_manufactures_zero_pnl(cached):
    summary = await PortfolioService(AsyncMock(get=AsyncMock(return_value=cached))).get_portfolio_summary("wallet", "user", db_for_positions())
    assert summary.total_cost == D("1608")
    assert summary.total_equity is None
    assert summary.profit_loss is None
    assert summary.profit_loss_pct is None
    assert summary.covered_equity == 0
    assert summary.price_coverage_pct == 0
    assert summary.allocation_by_type == {}
    assert all(p.lucro_prejuizo is None for p in summary.positions)


@pytest.mark.asyncio
async def test_partial_and_stale_prices_have_explicit_coverage_and_decimal_json():
    quote = json.dumps({"price": "11", "source": "fixture", "as_of": datetime.now(timezone.utc).isoformat()})
    stale = json.dumps({"price": "12", "source": "fixture", "as_of": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
    summary = await PortfolioService(AsyncMock(get=AsyncMock(side_effect=[quote, stale]))).get_portfolio_summary("wallet", "user", db_for_positions())
    assert summary.total_equity is None
    assert summary.covered_equity == 1100
    assert summary.price_coverage_pct == 50
    assert summary.positions[0].price_status == "valid"
    assert summary.positions[1].price_status == "stale"
    assert summary.positions[1].lucro_prejuizo is None
    assert summary.model_dump(mode="json")["total_cost"] == "1608.00"


@pytest.mark.asyncio
async def test_fresh_collection_does_not_make_old_fact_current():
    quote = json.dumps({"price": "11", "source": "fixture", "collected_at": datetime.now(timezone.utc).isoformat()})
    summary = await PortfolioService(AsyncMock(get=AsyncMock(return_value=quote))).get_portfolio_summary("wallet", "user", db_for_positions())
    assert summary.total_equity is None
    assert all(position.price_status == "stale" for position in summary.positions)
