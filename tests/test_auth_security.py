import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import text

from app.main import create_app
from app.auth.models import User, UserRole, SubscriptionTier
from app.auth.dependencies import get_current_user
from app.core.database import get_async_session


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_auth_registration_and_login_flow(test_app, monkeypatch):
    monkeypatch.setattr("app.auth.router.bind_auth_email", AsyncMock())
    monkeypatch.setattr("app.auth.router.bind_tenant", AsyncMock())
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    # 1. Registration attempt with new user
    mock_db.execute.side_effect = [
        # Check existing user -> None
        AsyncMock(scalar_one_or_none=lambda: None),
        # Insert user -> mappings().one()
        AsyncMock(mappings=lambda: AsyncMock(one=lambda: {
            "id_usuario": "11111111-2222-3333-4444-555555555555",
            "nome": "Investidor Teste",
            "email": "investidor@fin.com",
            "role": "user",
            "tier": "free",
        })),
        # Insert default wallet
        AsyncMock(),
    ]

    test_app.dependency_overrides[get_async_session] = lambda: mock_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg_payload = {
            "name": "Investidor Teste",
            "email": "investidor@fin.com",
            "password": "SenhaSegura123!",
        }
        res_reg = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res_reg.status_code == 201
        data_reg = res_reg.json()
        assert "token" in data_reg
        assert data_reg["user"]["email"] == "investidor@fin.com"
        assert data_reg["user"]["tier"] == "free"

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_login_invalid_password_rejected(test_app):
    mock_db = AsyncMock()
    # User found but password hash does not match
    mock_db.execute.return_value = AsyncMock(mappings=lambda: AsyncMock(first=lambda: {
        "id_usuario": "11111111-2222-3333-4444-555555555555",
        "nome": "Investidor Teste",
        "email": "investidor@fin.com",
        "password_hash": "dummy_hash",
        "salt": "dummy_salt",
        "role": "user",
        "tier": "free",
        "status": "Ativo",
    }))

    test_app.dependency_overrides[get_async_session] = lambda: mock_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "investidor@fin.com", "password": "WrongPassword!"},
        )
        assert res.status_code == 401
        assert "E-mail ou senha incorretos" in res.json()["detail"]

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_demo_positions_isolated_safety(test_app):
    """Verify F14 remediation: demo positions do not leak custody database records."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/portfolio/demo/positions")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 3
        tickers = [item["ticker"] for item in data]
        assert "ITUB4" in tickers
        assert "HGLG11" in tickers
        assert "IVVB11" in tickers
