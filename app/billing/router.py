from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, Request, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.config import get_settings, Settings
from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.auth.models import User
from app.auth.dependencies import get_current_user
from app.billing.contracts import PaymentProvider
from app.billing.adapters.asaas import AsaasPaymentProvider
from app.billing.service import BillingService
from app.billing.schemas import (
    SubscriptionCreate,
    PaymentMethod,
    PixSubscriptionResponse,
    BoletoSubscriptionResponse,
    CardHostedSubscriptionResponse,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


async def get_payment_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaymentProvider:
    return AsaasPaymentProvider(
        api_key=settings.ASAAS_API_KEY,
        environment=settings.ASAAS_ENVIRONMENT,
    )


async def get_billing_service(
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
) -> BillingService:
    return BillingService(redis_client=redis)


@router.post("/subscribe")
async def create_subscription(
    data: SubscriptionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
):
    plan_id = data.plan_tier.value
    if data.payment_method == PaymentMethod.PIX:
        return await provider.create_pix_subscription(user=current_user, plan_id=plan_id)
    elif data.payment_method == PaymentMethod.BOLETO:
        return await provider.create_boleto_subscription(user=current_user, plan_id=plan_id)
    else:
        return await provider.create_card_hosted_checkout(user=current_user, plan_id=plan_id)


@router.post("/webhooks/{gateway_provider}", status_code=status.HTTP_200_OK)
async def handle_payment_webhook(
    gateway_provider: str,
    request: Request,
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
    service: Annotated[BillingService, Depends(get_billing_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    body = await request.body()
    headers = dict(request.headers)
    event = await provider.parse_webhook(payload=body, headers=headers)
    processed = await service.handle_webhook_event(event, db_session=db)
    return {"received": True, "processed": processed}
