from typing import Annotated, List
from fastapi import APIRouter, Depends, status
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
    TransactionCreate,
    PortfolioSummaryResponse,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


async def get_portfolio_service(
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
) -> PortfolioService:
    return PortfolioService(redis_client=redis)


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
