from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.brokers.schemas import BrokerResponse
from app.brokers.service import BrokerService

router = APIRouter(prefix="/brokers", tags=["Brokers"])


def get_broker_service() -> BrokerService:
    return BrokerService()


@router.get("", response_model=BrokerResponse)
async def get_brokers(
    service: BrokerService = Depends(get_broker_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_brokers(db_session=db)
