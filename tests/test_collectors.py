import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.collectors.base import BaseCollector
from app.collectors.normalizer import DataNormalizer
from app.collectors.router import CollectorRouter
from app.collectors.adapters.status_invest import StatusInvestCollector
from app.collectors.adapters.fundamentus import FundamentusCollector
from app.collectors.adapters.clube_fii import ClubeFiiCollector
from app.collectors.adapters.funds_explorer import FundsExplorerCollector
from app.collectors.adapters.mais_retorno import MaisRetornoCollector
from app.collectors.adapters.etfs_brasil import EtfsBrasilCollector
from app.core.circuit_breaker import RedisCircuitBreaker
from app.core.exceptions import CollectorCircuitOpenException

@pytest.mark.asyncio
async def test_base_collector_circuit_breaker_blocks_execution():
    mock_cb = AsyncMock()
    mock_cb.can_execute = AsyncMock(return_value=False)
    mock_cb.get_cooldown_remaining = AsyncMock(return_value=420)

    collector = StatusInvestCollector(circuit_breaker=mock_cb)

    with pytest.raises(CollectorCircuitOpenException) as exc_info:
        await collector.collect("PETR4")

    assert "circuit is currently OPEN" in str(exc_info.value)
    assert exc_info.value.cooldown_remaining == 420

def test_data_normalizer_canonical_quote():
    raw_status_invest = {
        "ticker": "PETR4",
        "price": "36,50",
        "change_pct": "+1,25%",
        "volume": "1.500.000.000,00",
        "p_l": "4,12",
        "dy": "14,50%",
    }
    canonical = DataNormalizer.normalize_quote(raw_status_invest, source="status_invest")
    
    assert canonical.ticker == "PETR4"
    assert canonical.price == 36.50
    assert canonical.change_pct == 1.25
    assert canonical.volume == 1500000000.0
    assert canonical.p_l == 4.12
    assert canonical.dy_pct == 14.50
    assert canonical.source == "status_invest"

@pytest.mark.asyncio
async def test_collector_router_fallback():
    # Primary collector fails with an error
    failing_primary = AsyncMock()
    failing_primary.collect = AsyncMock(side_effect=Exception("Timeout / HTTP 500"))
    failing_primary.domain = "statusinvest.com.br"

    # Secondary collector succeeds
    successful_secondary = AsyncMock()
    successful_secondary.domain = "fundamentus.com.br"
    successful_secondary.collect = AsyncMock(
        return_value={
            "ticker": "VALE3",
            "price": "60,00",
            "change_pct": "-0,50%",
            "volume": "800.000.000,00",
        }
    )

    router = CollectorRouter(
        stock_collectors=[failing_primary, successful_secondary],
    )

    data = await router.collect_stock("VALE3")
    assert data.ticker == "VALE3"
    assert data.price == 60.00
    assert data.source == "fundamentus.com.br"
    failing_primary.collect.assert_called_once_with("VALE3")
    successful_secondary.collect.assert_called_once_with("VALE3")

@pytest.mark.asyncio
async def test_clube_fii_adapter_parsing():
    adapter = ClubeFiiCollector()
    mock_payload = {
        "data": {
            "fundo": {
                "codigo": "HGLG11",
                "cotacao": 162.50,
                "dy_anual": 8.92,
                "vacancia_fisica": 0.05,
                "quantidade_imoveis": 23,
                "gestora": "Credit Suisse Hedging-Griffo",
            }
        }
    }
    with patch.object(adapter, "_fetch_graphql", AsyncMock(return_value=mock_payload)):
        result = await adapter.collect("HGLG11")
        assert result["ticker"] == "HGLG11"
        assert result["price"] == 162.50
        assert result["imoveis_total"] == 23
