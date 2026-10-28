import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_get_stock_complete_details_commercial():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/stocks/PETR4")
        assert response.status_code == 200
        data = response.json()
        assert "details" in data
        assert "multiples" in data
        assert "financials" in data

        details = data["details"]
        assert details["ticker"] == "PETR4"
        assert details["is_financial_institution"] is False
        assert details["current_price"] > 0

        multiples = data["multiples"]
        assert multiples["ticker"] == "PETR4"
        assert multiples["margem_bruta"] is not None
        assert multiples["ev_ebitda"] is not None

        financials = data["financials"]
        assert financials["ticker"] == "PETR4"
        assert financials["is_financial_institution"] is False
        assert financials["ativo_total"] is not None
        assert financials["ebit_12m"] is not None
        assert financials["carteira_credito"] is None


@pytest.mark.asyncio
async def test_get_stock_complete_details_banking():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/stocks/ITUB4")
        assert response.status_code == 200
        data = response.json()

        details = data["details"]
        assert details["ticker"] == "ITUB4"
        assert details["is_financial_institution"] is True

        multiples = data["multiples"]
        assert multiples["ticker"] == "ITUB4"
        # Bank valuation rules: no EBITDA or Gross Margin
        assert multiples["ev_ebitda"] is None
        assert multiples["margem_bruta"] is None
        assert multiples["roe"] is not None

        financials = data["financials"]
        assert financials["ticker"] == "ITUB4"
        assert financials["is_financial_institution"] is True
        # Banking specific items
        assert financials["carteira_credito"] is not None
        assert financials["depositos"] is not None
        assert financials["resultado_intermediacao_12m"] is not None
        assert financials["ebit_12m"] is None
        assert financials["divida_liquida"] is None


@pytest.mark.asyncio
async def test_sub_endpoints():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r_det = await ac.get("/api/v1/stocks/ITUB4/details")
        assert r_det.status_code == 200
        assert r_det.json()["ticker"] == "ITUB4"

        r_ind = await ac.get("/api/v1/stocks/ITUB4/indicators")
        assert r_ind.status_code == 200
        assert r_ind.json()["ticker"] == "ITUB4"

        r_fin = await ac.get("/api/v1/stocks/ITUB4/financials")
        assert r_fin.status_code == 200
        assert r_fin.json()["ticker"] == "ITUB4"
        assert r_fin.json()["is_financial_institution"] is True
