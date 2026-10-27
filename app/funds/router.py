from fastapi import APIRouter, Depends
from app.funds.schemas import FundRiskMatrixResponse
from app.funds.service import FundService

router = APIRouter(prefix="/funds", tags=["Funds CVM 175"])


def get_fund_service() -> FundService:
    return FundService()


@router.get("/{fund_id}/risk-matrix", response_model=FundRiskMatrixResponse)
async def get_fund_risk_matrix(
    fund_id: str,
    service: FundService = Depends(get_fund_service),
):
    return await service.get_fund_risk_matrix(fund_id=fund_id)
