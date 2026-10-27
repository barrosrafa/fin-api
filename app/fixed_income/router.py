from fastapi import APIRouter, Depends
from app.fixed_income.schemas import FixedIncomeResponse
from app.fixed_income.service import FixedIncomeService

router = APIRouter(prefix="/fixed-income", tags=["Fixed Income"])


def get_fixed_income_service() -> FixedIncomeService:
    return FixedIncomeService()


@router.get("/treasury", response_model=FixedIncomeResponse)
async def get_treasury_bonds(
    service: FixedIncomeService = Depends(get_fixed_income_service),
):
    return await service.get_treasury_and_curves()
