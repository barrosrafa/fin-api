import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.mark.asyncio
async def test_cors_allows_vercel_domains():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        test_origins = [
            "https://fin-web-wheat.vercel.app",
            "https://fin-web.vercel.app",
            "https://fin-web-preview-123.vercel.app",
            "http://localhost:3000",
        ]
        for origin in test_origins:
            res = await client.options(
                "/api/v1/market/benchmarks",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert res.status_code == 200, f"Failed for origin {origin}: {res.status_code}"
            assert res.headers.get("access-control-allow-origin") == origin, f"Missing allow-origin for {origin}"

        # Disallowed origin
        res_disallowed = await client.options(
            "/api/v1/market/benchmarks",
            headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res_disallowed.headers.get("access-control-allow-origin") is None
