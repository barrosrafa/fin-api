import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_bola_unauthorized_user_access_blocked():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Attacker tries to access an arbitrary user's overrides without auth token
        res = await ac.get("/api/v1/portfolio/victim_account_12345/debtor-concentration")
        assert res.status_code == 401
        assert "Authentication required" in res.json()["detail"]

        res_override = await ac.post(
            "/api/v1/portfolio/victim_account_12345/overrides",
            json={
                "source_asset_id": "KNIP11",
                "target_entity_name": "Grupo JHSF",
                "override_type": "EXCLUDE_EDGE",
            },
        )
        assert res_override.status_code == 401


@pytest.mark.asyncio
async def test_demo_namespace_access_allowed():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.get("/api/v1/portfolio/test-user-1/debtor-concentration")
        assert res.status_code == 200
        assert "debtors" in res.json()


@pytest.mark.asyncio
async def test_sql_injection_rejection():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # SQL Injection attempt in ticker
        sqli_ticker = "ITUB4' OR '1'='1"
        res = await ac.get(f"/api/v1/stocks/{sqli_ticker}/details")
        # Should cleanly return either 200 with sanitized fallback or handled safely, without executing injection
        assert res.status_code in [200, 404]
        if res.status_code == 200:
            # Name should be sanitized or fallback, not leak database schemas
            assert "neondb" not in res.text
