from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.fiis.schemas import FIIDetailResponse, FIIRankingItem, FIIVacancyHistoryResponse
from app.fiis.service import FIIService

router = APIRouter(prefix="/fiis", tags=["FIIs"])


def get_fii_service() -> FIIService:
    return FIIService()


@router.get("/ranking", response_model=List[FIIRankingItem])
async def get_fiis_ranking(
    sort_by: str = Query("dy", description="Critério de ordenação: dy, pvp, vacancia, liquidez"),
    limit: int = Query(50, ge=1, le=200),
    service: FIIService = Depends(get_fii_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Ranking dinâmico de Fundos Imobiliários por DY, P/VP, Vacância ou Liquidez."""
    return await service.get_fiis_ranking(sort_by=sort_by, limit=limit, db_session=db)


@router.get("/{ticker}", response_model=FIIDetailResponse)
async def get_fii_detail(
    ticker: str,
    service: FIIService = Depends(get_fii_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_fii_detail(ticker=ticker, db_session=db)


@router.get("/{ticker}/vacancy-history", response_model=FIIVacancyHistoryResponse)
async def get_fii_vacancy_history(
    ticker: str,
    service: FIIService = Depends(get_fii_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna o histórico de evolução da vacância física e financeira do FII."""
    return await service.get_fii_vacancy_history(ticker=ticker, db_session=db)

