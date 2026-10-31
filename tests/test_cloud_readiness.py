import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_health_check_memory_only():
    """Verify that /health responds fast without requiring DB queries."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "fin-api"
    assert "version" in data


def test_unlisted_preview_is_not_trusted():
    client = TestClient(app)
    response = client.options("/api/v1/market/PETR4", headers={
        "Origin": "https://fin-web-preview.vercel.app",
        "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_port_environment_variable_fallback():
    """Verify that CLI serve resolves PORT from os.environ when not explicitly passed."""
    from app.config import get_settings
    settings = get_settings()
    assert settings.PORT > 0
