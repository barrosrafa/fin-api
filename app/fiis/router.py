from fastapi import APIRouter, Depends
from app.fiis.schemas import FIIDetailResponse
from app.fiis.service import FIIService

router = APIRouter(prefix="/fiis", tags=["FIIs"])


def get_fii_service() -> FIIService:
    return FIIService()


@router.get("/{ticker}", response_model=FIIDetailResponse)
async def get_fii_detail(
    ticker: str,
    service: FIIService = Depends(get_fii_service),
):
    return await service.get_fii_detail(ticker=ticker)
