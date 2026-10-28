import secrets
from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.config import get_settings, Settings
from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.core.exceptions import UnauthorizedException
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
    settings: Annotated[Settings, Depends(get_settings)],
):
    if gateway_provider != "asaas":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provedor de pagamento não suportado: '{gateway_provider}'"
        )

    # Strictly verify Asaas Webhook Token (Header: asaas-access-token)
    token = request.headers.get("asaas-access-token")
    if not token or not settings.ASAAS_WEBHOOK_SECRET or not secrets.compare_digest(token, settings.ASAAS_WEBHOOK_SECRET):
        raise UnauthorizedException("Assinatura do webhook inválida ou ausente (asaas-access-token)")

    body = await request.body()
    headers = dict(request.headers)
    event = await provider.parse_webhook(payload=body, headers=headers)
    processed = await service.handle_webhook_event(event, db_session=db)
    return {"received": True, "processed": processed}


@router.get("/plans")
async def get_plans():
    return {
        "plans": [
            {
                "id": "free",
                "name": "Gratuito",
                "price_monthly": 0.0,
                "price_annual": 0.0,
                "badge": "Iniciante",
                "features": [
                    "Cotações B3 com delay de 15 minutos",
                    "Acesso aos filtros básicos de Ações e FIIs",
                    "Simulador de Dividendos (até 3 simulações/mês)",
                    "Acesso ao Dicionário e Biblioteca de Livros",
                ],
                "restricted_features": [
                    "Histórico financeiro completo de 10 anos",
                    "Checklist dos 5 Pilares de Valuation desbloqueado",
                    "Mapa de Sazonalidade de Dividendos ilimitado",
                    "Alertas de proventos via Telegram e WhatsApp",
                    "Exportação de dados em planilhas Excel/CSV",
                ],
            },
            {
                "id": "pro_annual",
                "name": "Premium Pro Anual",
                "price_monthly": 29.90,
                "price_annual": 358.80,
                "badge": "Mais Popular - Economize 30%",
                "features": [
                    "Todos os recursos do plano Gratuito",
                    "Histórico financeiro completo de 10 anos (Balanço, DRE, DFC)",
                    "Checklist dos 5 Pilares de Valuation com Preço Teto Bazin e Preço Justo Graham",
                    "Mapa de Sazonalidade de Dividendos com heatmap de 12 meses",
                    "Simulador de Dividendos e Magic Number ilimitado",
                    "Módulo internacional: Stocks EUA e REITs com métricas Nareit e IRS 30%",
                    "Alertas imediatos de Data-Com e Pagamento via WhatsApp",
                    "Exportação ilimitada de dados em XLSX e CSV",
                    "Garantia incondicional de reembolso de 7 dias (CDC)",
                ],
                "restricted_features": [],
            },
            {
                "id": "pro_monthly",
                "name": "Premium Pro Mensal",
                "price_monthly": 42.90,
                "price_annual": 514.80,
                "badge": "Flexibilidade Mensal",
                "features": [
                    "Todos os recursos do plano Premium Anual",
                    "Cobrança recorrente mensal no cartão de crédito ou PIX",
                    "Cancele a qualquer momento sem fidelidade ou multa",
                ],
                "restricted_features": [],
            },
        ]
    }

