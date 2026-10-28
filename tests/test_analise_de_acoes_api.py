import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_simulate_dividends():
    payload = {
        "initial_capital": 10000.0,
        "monthly_contribution": 1000.0,
        "time_horizon_months": 120,
        "initial_stock_price": 10.0,
        "monthly_dividend_per_unit": 0.10,
        "annual_inflation_rate": 0.045,
        "annual_dividend_growth_rate": 0.05,
        "tax_rate": 0.0,
        "reinvest_dividends": True,
    }
    response = client.post("/api/v1/analytics/simulate-dividends", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["patrimonio_final"] > 10000.0
    assert data["total_aportado_bolso"] > 10000.0
    assert data["magic_number"]["atingido"] is True
    assert len(data["evolucao"]) == 120


def test_dividend_map():
    response = client.get("/api/v1/analytics/dividend-map")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_dividend_calendar():
    response = client.get("/api/v1/analytics/dividend-calendar?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_cms_glossary():
    response = client.get("/api/v1/cms/glossary")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    slug = data["items"][0]["slug"]

    detail_res = client.get(f"/api/v1/cms/glossary/{slug}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "conteudo_markdown" in detail


def test_cms_books():
    response = client.get("/api/v1/cms/books")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "titulo" in data[0]


def test_cms_support_ticket():
    ticket_payload = {
        "nome_contato": "Investidor Teste",
        "email_contato": "teste@exemplo.com",
        "assunto": "SUGESTAO",
        "mensagem": "Parabéns pela plataforma e pelas novas rotas de dividendos!",
    }
    response = client.post("/api/v1/cms/support/ticket", json=ticket_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ABERTO"
    assert data["id_ticket"] > 0


def test_suitability_questions_and_evaluate():
    q_res = client.get("/api/v1/suitability/questions")
    assert q_res.status_code == 200
    questions = q_res.json()
    assert len(questions) >= 1

    # Take first option of each question
    answers = []
    for q in questions:
        answers.append({"id_pergunta": q["id_pergunta"], "id_opcao_selecionada": q["opcoes"][0]["id_opcao"]})

    eval_res = client.post("/api/v1/suitability/evaluate", json={"respostas": answers})
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["score_total"] >= 0
    assert eval_data["codigo_categoria"] in ("CONSERVADOR", "MODERADO", "ARROJADO")
    assert "alocacao_alvo" in eval_data


def test_brokers_directory():
    response = client.get("/api/v1/brokers")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "costs" in data["items"][0]
    assert "ratings" in data["items"][0]


def test_stocks_us_and_reits():
    us_res = client.get("/api/v1/stocks/us")
    assert us_res.status_code == 200
    us_data = us_res.json()
    assert len(us_data) >= 1
    assert us_data[0]["price_usd"] > 0
    assert us_data[0]["price_brl"] > 0

    reits_res = client.get("/api/v1/stocks/reits")
    assert reits_res.status_code == 200
    reits_data = reits_res.json()
    assert len(reits_data) >= 1
    assert "ffo_per_share" in reits_data[0]
    assert reits_data[0]["net_dy_brl_pct"] < reits_data[0]["gross_dy_pct"]  # 30% IRS tax applied


def test_billing_plans():
    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert len(data["plans"]) == 3


def test_cms_articles():
    response = client.get("/api/v1/cms/articles?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "slug" in data[0]
    assert "titulo" in data[0]


def test_simulate_dividends_without_reinvestment():
    payload = {
        "initial_capital": 50000.0,
        "monthly_contribution": 0.0,
        "time_horizon_months": 24,
        "initial_stock_price": 20.0,
        "monthly_dividend_per_unit": 0.20,
        "annual_inflation_rate": 0.0,
        "annual_dividend_growth_rate": 0.0,
        "tax_rate": 0.0,
        "reinvest_dividends": False,
    }
    response = client.post("/api/v1/analytics/simulate-dividends", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["patrimonio_final"] == 50000.0
    assert data["total_proventos_gerados"] == 24 * (50000.0 / 20.0 * 0.20)
    assert data["magic_number"]["atingido"] is True

