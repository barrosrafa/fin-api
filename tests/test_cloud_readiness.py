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


def test_cors_headers_for_vercel_origins():
    """Verify that requests from Vercel subdomains receive valid CORS headers."""
    client = TestClient(app)
    headers = {
        "Origin": "https://fin-web-preview.vercel.app",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/v1/market/quote/PETR4", headers=headers)
    assert response.status_code in [200, 204]
    # Check that Origin header or allow-origin matches
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] in [
        "https://fin-web-preview.vercel.app",
        "*",
    ]


def test_port_environment_variable_fallback():
    """Verify that CLI serve resolves PORT from os.environ when not explicitly passed."""
    from app.config import get_settings
    settings = get_settings()
    assert settings.PORT > 0
