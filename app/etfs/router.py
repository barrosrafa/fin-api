from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.etfs.schemas import ETFDetailResponse
from app.etfs.service import ETFService

router = APIRouter(prefix="/etfs", tags=["ETFs"])


def get_etf_service() -> ETFService:
    return ETFService()


@router.get("/{ticker}", response_model=ETFDetailResponse)
async def get_etf_detail(
    ticker: str,
    service: ETFService = Depends(get_etf_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_etf_detail(ticker=ticker, db_session=db)
