from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_debtor_concentration_endpoint():
    response = client.get("/api/v1/portfolio/test-user-1/debtor-concentration")
    assert response.status_code == 200
    data = response.json()
    assert "debtors" in data
    assert "coverage" in data
    assert any(d["entity_name"] == "Grupo JHSF" for d in data["debtors"])
    assert data["coverage"]["pct_resolved"] > 0


def test_get_falsifiable_phrase_endpoint():
    response = client.get("/api/v1/portfolio/test-user-1/falsifiable-phrase")
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert "interactive_pills" in data
    assert "inference_log" in data
    assert "Você não tem concentração por ticker — tem concentração por devedor" in data["text"]


def test_post_user_override_endpoint():
    payload = {
        "source_asset_id": "KNIP11",
        "target_entity_name": "Grupo JHSF",
        "override_type": "EXCLUDE_EDGE",
        "reason": "Test exclusion override",
    }
    response = client.post("/api/v1/portfolio/test-user-1/overrides", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_get_reconciliation_endpoint():
    response = client.get("/api/v1/reconciliation/KNIP11")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "KNIP11"
    assert "arbitrated" in data
    assert "divergence" in data
    assert data["divergence"]["taxonomy"] == "DIVIDEND_WINDOW_MISMATCH"
