import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_specialized_fii_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/fiis/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "HGLG11"
        assert "properties" in data
        assert "brick_score" in data
        assert "wault_years" in data


@pytest.mark.asyncio
async def test_specialized_stock_valuation_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/stocks/PETR4/valuation")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "PETR4"
        assert "graham_fair_value" in data
        assert "bazin_ceiling_price" in data
        assert "checklist" in data


@pytest.mark.asyncio
async def test_specialized_funds_risk_matrix():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/funds/1001/risk-matrix")
        assert response.status_code == 200
        data = response.json()
        assert "matrix" in data
        assert len(data["matrix"]) > 0
        assert "sharpe" in data["matrix"][0]


@pytest.mark.asyncio
async def test_specialized_etf_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/etfs/BOVA11")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "BOVA11"
        assert "ter_pct" in data
        assert "nav_spread_pct" in data


@pytest.mark.asyncio
async def test_specialized_derivatives_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/derivatives/PETR4/options-chain")
        assert response.status_code == 200
        data = response.json()
        assert data["underlying"] == "PETR4"
        assert "calls" in data
        assert "btc_borrowing" in data


@pytest.mark.asyncio
async def test_specialized_fixed_income_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/fixed-income/treasury")
        assert response.status_code == 200
        data = response.json()
        assert "bonds" in data
        assert len(data["bonds"]) > 0


@pytest.mark.asyncio
async def test_specialized_screener_and_comparator():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Screener
        res_screener = await client.post("/api/v1/screener/query", json={"asset_class": "FII", "min_dy": 5.0})
        assert res_screener.status_code == 200
        assert "items" in res_screener.json()

        # Comparator
        res_comp = await client.post("/api/v1/comparator/compare", json={"tickers": ["PETR4", "VALE3"]})
        assert res_comp.status_code == 200
        assert "series" in res_comp.json()


@pytest.mark.asyncio
async def test_specialized_intelligence_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/intelligence/sentiment/PETR4")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "PETR4"
        assert "sentiment" in data
        assert "swot" in data
