import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_simulate_portfolio_post():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "startDate": "2024-01-02",
            "endDate": "2026-10-26",
            "startingAmount": 50000.0,
            "monthlyContributions": 1000.0,
            "rebalancingFrequency": "TRIMESTRAL",
            "advisoryFee": 0.5,
            "portfolioList": [
                {
                    "name": "Conservador",
                    "assets": [
                        {"ticker": "BLFT11", "assetsType": "etfs", "percentage": 0.5},
                        {"ticker": "DEBB11", "assetsType": "etfs", "percentage": 0.5},
                    ],
                },
                {
                    "name": "Arrojado",
                    "assets": [
                        {"ticker": "BOVA11", "assetsType": "etfs", "percentage": 0.6},
                        {"ticker": "IVVB11", "assetsType": "etfs", "percentage": 0.4},
                    ],
                },
            ],
        }
        res = await client.post("/api/v1/simulate-portfolio", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "benchmark" in data
        assert data["benchmark"]["name"] == "CDI"
        assert len(data["portfolios"]) == 2
        assert data["portfolios"][0]["name"] == "Conservador"
        assert data["portfolios"][1]["name"] == "Arrojado"
        assert len(data["portfolios"][0]["equityCurve"]) > 10
        assert len(data["portfolios"][0]["drawdownCurve"]) > 10
        assert "finalAmount" in data["portfolios"][0]["metrics"]
        assert "sharpeRatio" in data["portfolios"][0]["metrics"]
        assert "sortinoRatio" in data["portfolios"][0]["metrics"]


@pytest.mark.asyncio
async def test_simulate_portfolio_get():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/simulate-portfolio")
        assert res.status_code == 200
        data = res.json()
        assert len(data["portfolios"]) >= 1


@pytest.mark.asyncio
async def test_comparator_pair_and_multi():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test Multi Compare
        payload = {"tickers": ["BOVA11", "SMAL11"], "timeframe": "12M"}
        res = await client.post("/api/v1/comparator/compare", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["metrics"]) == 2
        assert len(data["series"]) > 0
        assert data["overlap_analysis"] is not None
        assert data["overlap_analysis"]["total_overlap_pct"] >= 0.0

        # Test Canonical Pair GET
        pair_res = await client.get("/api/v1/comparator/pair/CDIB11/LFTB11")
        assert pair_res.status_code == 200
        pair_data = pair_res.json()
        assert len(pair_data["metrics"]) == 2
        assert pair_data["tickers"] == ["CDIB11", "LFTB11"]


@pytest.mark.asyncio
async def test_rankings():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/rankings?tipo_ativo=ETF&ordem=retorno_30d&categoria=Todos")
        assert res.status_code == 200
        data = res.json()
        assert data["tipo_ativo"] == "ETF"
        assert len(data["items"]) > 0
        assert data["items"][0]["pos"] == 1


@pytest.mark.asyncio
async def test_etf_detail():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/etfs/BOVA11")
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "BOVA11"
        assert len(data["underlying_holdings"]) > 0
        assert data["ter_pct"] > 0
