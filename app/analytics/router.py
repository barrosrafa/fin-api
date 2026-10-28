from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.analytics.schemas import (
    DividendSimulationRequest,
    DividendSimulationResponse,
    DividendMapResponse,
    DividendCalendarDetailItem,
)
from app.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


@router.post("/simulate-dividends", response_model=DividendSimulationResponse)
async def simulate_dividends(
    request: DividendSimulationRequest,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return service.simulate_dividends(request)


@router.get("/dividend-map", response_model=DividendMapResponse)
async def get_dividend_map(
    month: Optional[int] = None,
    min_probability: float = 0.0,
    service: AnalyticsService = Depends(get_analytics_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_dividend_map(db_session=db, month=month, min_probability=min_probability)


@router.get("/dividend-calendar", response_model=List[DividendCalendarDetailItem])
async def get_dividend_calendar(
    limit: int = 50,
    event_type: str = "ALL",
    service: AnalyticsService = Depends(get_analytics_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_dividend_calendar(db_session=db, limit=limit, event_type=event_type)
