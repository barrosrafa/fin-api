from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.derivatives.schemas import DerivativesResponse
from app.derivatives.service import DerivativesService

router = APIRouter(prefix="/derivatives", tags=["Derivatives"])


def get_derivatives_service() -> DerivativesService:
    return DerivativesService()


@router.get("/{ticker}/options-chain", response_model=DerivativesResponse)
async def get_options_chain(
    ticker: str,
    service: DerivativesService = Depends(get_derivatives_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_options_chain(ticker=ticker, db_session=db)
