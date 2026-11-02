from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from app.fiis.service import FIIService
from app.market.lifecycle import trading_status
from app.market.quality import verified_market_text
from app.stocks.service import StockService


def test_quote_evidence_gate_is_identity_session_nominal_and_not_a_price_cap():
    sql = str(verified_market_text('SELECT * FROM market.cotacao_diaria cd WHERE cd.id_ativo=:id'))
    for predicate in ('official.ticker = identity.ticker', 'official.reference_date = legacy.data_pregao',
                      'official.close = legacy.preco_fechamento', 'is_backtest_simulado', 'America/Sao_Paulo'):
        assert predicate in sql
    assert 'WHERE cd.id_ativo=:id' in sql
    with pytest.raises(ValueError):
        verified_market_text('DELETE FROM market.cotacao_diaria')


def test_trading_status_respects_effective_date_and_registry_for_any_asset():
    assert trading_status('AXIA6', 'ACTIVE', date(2026, 6, 7)).status == 'active'
    event = trading_status('axia6', 'ACTIVE', date(2026, 6, 8))
    assert event.status == 'inactive' and event.successor == 'AXIA3' and event.source_url
    assert trading_status('ANY11', 'INACTIVE').status == 'inactive'
    assert trading_status('BBML3', 'ACTIVE').status == 'active'
    assert trading_status('UNKNOWN3').status == 'unknown'


@pytest.mark.asyncio
async def test_delisted_valuation_fails_before_reading_quotes():
    db = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await StockService().get_valuation('AXIA6', db)
    assert error.value.status_code == 409
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fii_without_database_never_returns_demo_data():
    with pytest.raises(HTTPException) as error:
        await FIIService().get_fii_detail('ANY11')
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_fii_missing_fields_remain_missing_and_real_zero_survives():
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        'id_ativo': 1, 'canonical_instrument_id': None, 'razao_social': 'QA', 'segmento': None,
        'preco': None, 'vpa': None, 'pl': None, 'vf': 0, 'vfin': None,
    }
    empty = MagicMock()
    empty.mappings.return_value.all.return_value = []
    empty.mappings.return_value.first.return_value = None
    db = AsyncMock(execute=AsyncMock(side_effect=[result, empty, empty, empty]))
    detail = await FIIService().get_fii_detail('QA11', db)
    assert detail.current_price is None and detail.pvp is None and detail.dividend_yield_12m is None
    assert detail.physical_vacancy_pct == 0 and detail.financial_vacancy_pct is None
    assert detail.indicators.last_dividend is None
    assert detail.indicators.quote_datetime is None
    assert detail.properties == detail.brick_score == detail.cri_portfolio == detail.top_tenants == []
    assert detail.quarterly_dre is None and detail.lucratividade is None
    assert detail.cadastral.cnpj is None and detail.cadastral.administrator_name is None
