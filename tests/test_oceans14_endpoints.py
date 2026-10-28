import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_macro_government_accounts(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/macro/government-accounts?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total_records" in data


@pytest.mark.asyncio
async def test_macro_credit_system(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/macro/credit-system?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data


@pytest.mark.asyncio
async def test_stocks_ranking(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stocks/ranking?sort_by=dy&limit=5")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) > 0
        assert "rank" in items[0]
        assert "ticker" in items[0]
        assert "dy" in items[0]


@pytest.mark.asyncio
async def test_stocks_consistency_screener(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stocks/screener/consistency?min_years=5")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) > 0
        assert "consecutive_profitable_years" in items[0]


@pytest.mark.asyncio
async def test_stocks_financial_matrix(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stocks/PETR4/financials/matrix?period_type=ANUAL")
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "PETR4"
        assert "dre" in data
        assert "balance_sheet" in data
        assert "cash_flow" in data
        assert len(data["dre"]) > 0


@pytest.mark.asyncio
async def test_stocks_dividends_matrix(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stocks/PETR4/dividends/matrix")
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "PETR4"
        assert "matrix" in data
        assert len(data["matrix"]) > 0
        assert len(data["matrix"][0]["months"]) == 12


@pytest.mark.asyncio
async def test_fiis_ranking(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/fiis/ranking?sort_by=dy&limit=5")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) > 0
        assert "ticker" in items[0]
        assert "dy_12m" in items[0]


@pytest.mark.asyncio
async def test_fiis_vacancy_history(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/fiis/HGLG11/vacancy-history")
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "HGLG11"
        assert "history" in data
        assert len(data["history"]) > 0


@pytest.mark.asyncio
async def test_market_ibov_pe_history(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/market/ibov-pe-history?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert len(data["items"]) > 0
        assert "pl_ponderado" in data["items"][0]
        assert "media_historica_5y" in data["items"][0]


@pytest.mark.asyncio
async def test_market_investor_flows(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/market/investor-flows?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert len(data["items"]) > 0
        assert "categoria_investidor" in data["items"][0]


@pytest.mark.asyncio
async def test_market_earnings_calendar(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/market/earnings-calendar?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert len(data["items"]) > 0
        assert "ticker" in data["items"][0]


@pytest.mark.asyncio
async def test_comparator_multi_ticker(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"tickers": ["PETR4", "VALE3", "WEGE3"], "timeframe": "12M"}
        res = await client.post("/api/v1/comparator/compare", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["tickers"]) == 3
        assert len(data["metrics"]) == 3
        assert len(data["series"]) > 0
