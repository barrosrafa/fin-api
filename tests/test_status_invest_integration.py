"""Testes de integração para validação de exposição dos dados do Status Invest via API."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.market.service import MarketService
from app.market.schemas import IndicatorsResponse, TickerQuote


@pytest.mark.asyncio
async def test_market_quote_exposes_fundamental_indicators():
    mock_catalog = AsyncMock()
    mock_catalog.is_valid = AsyncMock(return_value=True)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    mock_arq = AsyncMock()
    mock_arq.enqueue_job = AsyncMock(return_value="job_test")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {
        "preco_fechamento": 38.45,
        "variacao_percentual": 1.25,
        "volume_total": 1450000000.0,
        "pl": 4.80,
        "pvp": 1.15,
        "dividend_yield": 14.80,
        "fonte": "fin-db",
    }
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
        arq_pool=mock_arq,
    )

    quote_resp = await service.get_quote("PETR4", db_session=mock_db)
    assert quote_resp.status == "stale"
    assert quote_resp.quote is not None
    assert quote_resp.quote.price == 38.45
    assert quote_resp.quote.p_l == 4.80
    assert quote_resp.quote.p_vp == 1.15
    assert quote_resp.quote.dy_pct == 14.80
    assert quote_resp.quote.source == "fin-db"


@pytest.mark.asyncio
async def test_market_indicators_endpoint_query():
    mock_catalog = AsyncMock()
    mock_redis = AsyncMock()
    mock_db = AsyncMock()

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {
        "pl": 5.25,
        "pvp": 0.90,
        "dividend_yield": 11.07,
        "roe": 14.05,
        "roic": 12.50,
        "margem_liquida": 12.60,
        "divida_liquida_ebitda": 1.80,
        "ev_ebitda": 5.25,
    }
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = MarketService(
        ticker_catalog=mock_catalog,
        redis_client=mock_redis,
    )

    indicators = await service.get_indicators("ABCB4", db_session=mock_db)
    assert isinstance(indicators, IndicatorsResponse)
    assert indicators.ticker == "ABCB4"
    assert indicators.p_l == 5.25
    assert indicators.p_vp == 0.90
    assert indicators.dy_pct == 11.07
    assert indicators.roe_pct == 14.05
    assert indicators.margem_liquida_pct == 12.60


@pytest.mark.asyncio
async def test_e2e_fii_detail_and_indicators_contract():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Endpoint de FII
        fii_resp = await client.get("/api/v1/fiis/HGLG11")
        assert fii_resp.status_code == 200
        fii_data = fii_resp.json()
        assert fii_data["ticker"] == "HGLG11"
        assert "current_price" in fii_data
        assert "pvp" in fii_data
        assert "dividend_yield_12m" in fii_data
        assert "net_worth" in fii_data
        assert "properties" in fii_data
        assert "brick_score" in fii_data

        # 2. Endpoint de Indicadores de Mercado
        ind_resp = await client.get("/api/v1/market/PETR4/indicators")
        assert ind_resp.status_code == 200
        ind_data = ind_resp.json()
        assert ind_data["ticker"] == "PETR4"
        assert "p_l" in ind_data
        assert "p_vp" in ind_data
        assert "dy_pct" in ind_data
