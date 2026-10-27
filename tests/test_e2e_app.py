import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

@pytest.mark.asyncio
async def test_health_check_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "fin-api"
        assert data["version"] == "0.1.0"

@pytest.mark.asyncio
async def test_openapi_docs_served():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200

        openapi_resp = await client.get("/openapi.json")
        assert openapi_resp.status_code == 200
        spec = openapi_resp.json()
        assert "paths" in spec
        assert "/api/v1/market/{ticker}" in spec["paths"]
        assert "/api/v1/portfolio/wallets" in spec["paths"]
        assert "/api/v1/billing/subscribe" in spec["paths"]
