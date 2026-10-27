from fastapi import APIRouter, Depends
from app.etfs.schemas import ETFDetailResponse
from app.etfs.service import ETFService

router = APIRouter(prefix="/etfs", tags=["ETFs"])


def get_etf_service() -> ETFService:
    return ETFService()


@router.get("/{ticker}", response_model=ETFDetailResponse)
async def get_etf_detail(
    ticker: str,
    service: ETFService = Depends(get_etf_service),
):
    return await service.get_etf_detail(ticker=ticker)
