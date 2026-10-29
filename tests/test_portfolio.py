import pytest
import json
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from app.portfolio.service import PortfolioService
from app.portfolio.schemas import (
    WalletCreate,
    TransactionCreate,
    TransactionType,
    WalletResponse,
    PositionResponse,
)

@pytest.mark.asyncio
async def test_create_and_list_wallets():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"id_carteira": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "nome_carteira": "Carteira Principal", "data_criacao": "2026-10-26T20:00:00Z"}
    ]
    mock_result.mappings.return_value.first.return_value = {
        "id_carteira": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "nome_carteira": "Carteira Principal", "data_criacao": "2026-10-26T20:00:00Z"
    }
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    service = PortfolioService()
    
    wallet = await service.create_wallet(
        user_id="user_123",
        data=WalletCreate(nome="Carteira Principal", descricao="Foco em dividendos", padrao=True),
        db_session=mock_db,
    )
    assert wallet.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert wallet.nome == "Carteira Principal"

    wallets = await service.list_wallets(user_id="user_123", db_session=mock_db)
    assert len(wallets) == 1
    assert wallets[0].nome == "Carteira Principal"

@pytest.mark.asyncio
async def test_calculate_average_price_on_buy():
    # Buy 100 @ 30.00, then buy 100 @ 40.00 -> 200 @ 35.00
    p1 = PortfolioService.compute_new_average_price(
        current_qty=100.0,
        current_avg_price=30.0,
        new_qty=100.0,
        new_price=40.0,
    )
    assert p1 == 35.0

    # This helper models purchases; selling belongs to the explicit sell operation.
    with pytest.raises(ValueError):
        PortfolioService.compute_new_average_price(200, 35, -50, 45)

@pytest.mark.asyncio
async def test_get_portfolio_summary_and_allocation():
    mock_db = AsyncMock()
    
    # First query checks ownership (scalar_one_or_none -> returns wallet id)
    mock_check = MagicMock()
    mock_check.scalar_one_or_none.return_value = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    
    # Second query returns positions
    mock_positions = MagicMock()
    mock_positions.mappings.return_value.all.return_value = [
        {"ticker": "PETR4", "quantidade": 200, "preco_medio": 30.0, "tipo_ativo": "ACAO"},
        {"ticker": "HGLG11", "quantidade": 50, "preco_medio": 160.0, "tipo_ativo": "FII"},
    ]
    mock_db.execute = AsyncMock(side_effect=[mock_check, mock_positions])

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(side_effect=lambda k: json.dumps({"price": "35.0" if "PETR4" in k else "170.0", "source": "fixture", "as_of": datetime.now(timezone.utc).isoformat()}))

    service = PortfolioService(redis_client=mock_cache)
    summary = await service.get_portfolio_summary(
        wallet_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        user_id="user_123",
        db_session=mock_db,
    )

    assert summary.total_equity == 15500.0
    assert summary.total_cost == 14000.0
    assert summary.profit_loss == 1500.0
    assert summary.profit_loss_pct == Decimal("10.71")
