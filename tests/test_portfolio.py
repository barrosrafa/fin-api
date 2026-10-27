import pytest
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
        {"id_carteira": 1, "nome": "Carteira Principal", "padrao": True, "descricao": "Foco em dividendos"}
    ]
    mock_result.mappings.return_value.first.return_value = {
        "id_carteira": 1, "nome": "Carteira Principal", "padrao": True, "descricao": "Foco em dividendos"
    }
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    service = PortfolioService()
    
    wallet = await service.create_wallet(
        user_id="user_123",
        data=WalletCreate(nome="Carteira Principal", descricao="Foco em dividendos", padrao=True),
        db_session=mock_db,
    )
    assert wallet.id == 1
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

    # Selling 50 does not change average purchase price
    p2 = PortfolioService.compute_new_average_price(
        current_qty=200.0,
        current_avg_price=35.0,
        new_qty=-50.0,
        new_price=45.0,
    )
    assert p2 == 35.0

@pytest.mark.asyncio
async def test_get_portfolio_summary_and_allocation():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"ticker": "PETR4", "quantidade": 200, "preco_medio": 30.0, "tipo_ativo": "ACAO"},
        {"ticker": "HGLG11", "quantidade": 50, "preco_medio": 160.0, "tipo_ativo": "FII"},
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_cache = AsyncMock()
    # Current prices: PETR4=35.00 (val: 7000), HGLG11=170.00 (val: 8500) -> total=15500
    mock_cache.get = AsyncMock(side_effect=lambda k: b'{"price": 35.0}' if "PETR4" in k else b'{"price": 170.0}')

    service = PortfolioService(redis_client=mock_cache)
    summary = await service.get_portfolio_summary(wallet_id=1, db_session=mock_db)

    assert summary.total_equity == 15500.0
    assert summary.total_cost == 14000.0  # 200*30 + 50*160
    assert summary.profit_loss == 1500.0
    assert summary.profit_loss_pct == pytest.approx(10.71, 0.01)
