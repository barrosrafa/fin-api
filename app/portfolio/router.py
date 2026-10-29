from typing import Annotated, List
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.auth.models import User
from app.auth.dependencies import get_current_user
from app.portfolio.service import PortfolioService
from app.portfolio.schemas import (
    WalletCreate,
    WalletResponse,
    PortfolioSummaryResponse,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


class DemoPositionItem(BaseModel):
    ticker: str
    type: str
    shares: float
    price: float
    total: float
    yieldAnn: float
    monthlyEstimate: float


async def get_portfolio_service(
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
) -> PortfolioService:
    return PortfolioService(redis_client=redis)


@router.get("/demo/positions", response_model=List[DemoPositionItem])
async def get_demo_positions():
    """
    Retorna uma carteira demonstrativa puramente estática e mockada para novos visitantes.
    NUNCA acessa tabelas privadas de custódia (core.posicao_custodia) do banco de produção.
    """
    demo_items = [
        DemoPositionItem(
            ticker="ITUB4",
            type="AÇÃO",
            shares=200.0,
            price=34.50,
            total=6900.0,
            yieldAnn=7.2,
            monthlyEstimate=41.40,
        ),
        DemoPositionItem(
            ticker="HGLG11",
            type="FII",
            shares=50.0,
            price=162.80,
            total=8140.0,
            yieldAnn=8.9,
            monthlyEstimate=60.37,
        ),
        DemoPositionItem(
            ticker="IVVB11",
            type="ETF",
            shares=30.0,
            price=295.10,
            total=8853.0,
            yieldAnn=0.0,
            monthlyEstimate=0.0,
        ),
        DemoPositionItem(
            ticker="B3SA3",
            type="AÇÃO",
            shares=300.0,
            price=12.40,
            total=3720.0,
            yieldAnn=6.5,
            monthlyEstimate=20.15,
        ),
    ]
    return demo_items


@router.get("/wallets", response_model=List[WalletResponse])
async def list_user_wallets(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    return await service.list_wallets(user_id=current_user.id, db_session=db)


@router.post("/wallets", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def create_user_wallet(
    data: WalletCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    return await service.create_wallet(user_id=current_user.id, data=data, db_session=db)


@router.get("/wallets/{wallet_id}/summary", response_model=PortfolioSummaryResponse)
async def get_wallet_summary(
    wallet_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    return await service.get_portfolio_summary(wallet_id=wallet_id, user_id=current_user.id, db_session=db)
