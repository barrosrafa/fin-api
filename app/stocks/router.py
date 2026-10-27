from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.stocks.schemas import StockValuationResponse
from app.stocks.service import StockService

router = APIRouter(prefix="/stocks", tags=["Stocks"])


def get_stock_service() -> StockService:
    return StockService()


@router.get("/{ticker}/valuation", response_model=StockValuationResponse)
async def get_stock_valuation(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_valuation(ticker=ticker, db_session=db)
