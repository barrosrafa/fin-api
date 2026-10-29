from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
import pytest
from app.stocks.service import StockService
from app.collectors.normalizer import CanonicalQuote


@pytest.mark.asyncio
async def test_valuation_without_source_is_unavailable():
    with pytest.raises(HTTPException) as error:
        await StockService().get_valuation("PETR4")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_public_stock_components_never_fabricate_missing_numbers():
    service = StockService()
    details = await service.get_stock_details("PETR4")
    assert details.current_price is None
    assert details.valor_mercado is None
    assert details.min_52_semanas is None
    multiples = await service.get_multiples("PETR4")
    assert multiples.roe is None
    assert multiples.pl is None
    financials = await service.get_financials("PETR4")
    assert financials.ativo_total is None
    assert financials.patrimonio_liquido is None
    assert financials.data_balanco is None


@pytest.mark.asyncio
async def test_reported_zero_and_negative_multiples_survive():
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id_indicador": 1, "pl": -2, "pvp": 0, "dividend_yield": 0,
    }
    response = await StockService().get_multiples("PETR4", AsyncMock(execute=AsyncMock(return_value=result)))
    assert response.pl == -2
    assert response.pvp == 0
    assert response.dividend_yield == 0
    assert response.roe is None


def test_collection_instant_is_per_record():
    first = CanonicalQuote(ticker="A", price=1, change_pct=0, source="test")
    second = CanonicalQuote(ticker="B", price=1, change_pct=0, source="test")
    assert second.collected_at >= first.collected_at
    assert first.collected_at.tzinfo is not None


@pytest.mark.asyncio
async def test_simulator_does_not_manufacture_history_or_cdi_when_source_is_missing():
    from app.simulator.service import SimulatorService
    from app.simulator.schemas import SimulatePortfolioRequest
    request = SimulatePortfolioRequest(startDate="2026-10-01", endDate="2026-10-26", startingAmount=1000,
        monthlyContributions=0, rebalancingFrequency="NENHUM", advisoryFee=0,
        portfolioList=[{"name": "QA", "assets": [{"ticker": "PETR4", "percentage": 100}]}])
    with pytest.raises(HTTPException) as error:
        await SimulatorService().simulate(request)
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_valuation_with_missing_database_inputs_is_unavailable():
    asset, quote = MagicMock(), MagicMock()
    asset.mappings.return_value.first.return_value = {"id_ativo": 1, "id_emissor": None, "nome": "QA"}
    quote.mappings.return_value.first.return_value = None
    with pytest.raises(HTTPException) as error:
        await StockService().get_valuation("QA0003", AsyncMock(execute=AsyncMock(side_effect=[asset, quote])))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_source_backed_stock_details_preserve_prices_and_reported_zero():
    row = {"nome_empresarial": "Empresa QA", "tipo_ativo": "ACAO", "classe_acao": "PN",
        "setor": "QA", "subsetor": None, "segmento": None, "preco_fechamento": "12.34",
        "dt_pregao": "2026-10-26", "min_52_semanas": "10", "max_52_semanas": "14",
        "volume_medio_2m": 0, "valor_mercado": "1234", "enterprise_value": None, "quantidade_emitida": 100}
    response = MagicMock()
    response.mappings.return_value.first.return_value = row
    details = await StockService().get_stock_details("QA0003", AsyncMock(execute=AsyncMock(return_value=response)))
    assert details.current_price == 12.34
    assert details.min_52_semanas == 10
    assert details.max_52_semanas == 14
    assert details.volume_medio_2m == 0
    assert details.valor_mercado == 1234
    assert details.valor_firma is None
    assert details.numero_acoes == 100
    assert details.data_cotacao == "2026-10-26"
