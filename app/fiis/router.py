from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.fiis.schemas import FIIDetailResponse
from app.fiis.service import FIIService

router = APIRouter(prefix="/fiis", tags=["FIIs"])


def get_fii_service() -> FIIService:
    return FIIService()


@router.get("/{ticker}", response_model=FIIDetailResponse)
async def get_fii_detail(
    ticker: str,
    service: FIIService = Depends(get_fii_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_fii_detail(ticker=ticker, db_session=db)
