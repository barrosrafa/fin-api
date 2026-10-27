from fastapi import APIRouter, Depends
from app.derivatives.schemas import DerivativesResponse
from app.derivatives.service import DerivativesService

router = APIRouter(prefix="/derivatives", tags=["Derivatives"])


def get_derivatives_service() -> DerivativesService:
    return DerivativesService()


@router.get("/{ticker}/options-chain", response_model=DerivativesResponse)
async def get_options_chain(
    ticker: str,
    service: DerivativesService = Depends(get_derivatives_service),
):
    return await service.get_options_chain(ticker=ticker)
