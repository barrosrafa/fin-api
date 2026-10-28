from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.suitability.schemas import (
    SuitabilityQuestion,
    SuitabilityEvaluateRequest,
    SuitabilityEvaluateResponse,
)
from app.suitability.service import SuitabilityService

router = APIRouter(prefix="/suitability", tags=["Suitability"])


def get_suitability_service() -> SuitabilityService:
    return SuitabilityService()


@router.get("/questions", response_model=List[SuitabilityQuestion])
async def get_questions(
    service: SuitabilityService = Depends(get_suitability_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_questions(db_session=db)


@router.post("/evaluate", response_model=SuitabilityEvaluateResponse)
async def evaluate_answers(
    request: SuitabilityEvaluateRequest,
    service: SuitabilityService = Depends(get_suitability_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.evaluate_answers(db_session=db, request=request)
