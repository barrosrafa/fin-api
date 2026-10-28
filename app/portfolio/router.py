from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
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
async def get_demo_positions(
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    stmt = text(
        """
        SELECT 
            a.ticker,
            CASE a.tipo_ativo::text 
                WHEN 'ACAO' THEN 'AÇÃO' 
                WHEN 'FII' THEN 'FII' 
                WHEN 'ETF' THEN 'ETF' 
                WHEN 'TESOURO' THEN 'RENDA FIXA'
                ELSE a.tipo_ativo::text 
            END as tipo,
            pc.quantidade_total as shares,
            COALESCE(cd.preco_fechamento, pc.preco_medio_ponderado, 10.0) as price,
            COALESCE(inf.dividend_yield, df.dividend_yield, 8.5) as dy
        FROM core.posicao_custodia pc
        JOIN core.ativo a ON a.id_ativo = pc.id_ativo
        LEFT JOIN LATERAL (
            SELECT preco_fechamento 
            FROM market.cotacao_diaria 
            WHERE id_ativo = a.id_ativo 
            ORDER BY data_pregao DESC LIMIT 1
        ) cd ON TRUE
        LEFT JOIN LATERAL (
            SELECT dividend_yield 
            FROM analytics.indicador_fundamentalista 
            WHERE id_ativo = a.id_ativo 
            ORDER BY data_referencia DESC LIMIT 1
        ) inf ON TRUE
        LEFT JOIN LATERAL (
            SELECT dividend_yield 
            FROM asset_details.detalhe_fii 
            WHERE id_ativo = a.id_ativo 
            LIMIT 1
        ) df ON TRUE
        ORDER BY (pc.quantidade_total * COALESCE(cd.preco_fechamento, 10.0)) DESC;
        """
    )
    res = await db.execute(stmt)
    rows = res.mappings().all()

    items = []
    for r in rows:
        shares = float(r["shares"])
        price = float(r["price"])
        total = round(shares * price, 2)
        dy = float(r["dy"])
        monthly = round((total * (dy / 100.0)) / 12.0, 2) if dy > 0 else 0.0

        items.append(
            DemoPositionItem(
                ticker=r["ticker"],
                type=r["tipo"],
                shares=shares,
                price=price,
                total=total,
                yieldAnn=dy,
                monthlyEstimate=monthly,
            )
        )

    return items


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
