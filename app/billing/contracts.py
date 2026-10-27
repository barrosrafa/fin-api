from abc import ABC, abstractmethod
from typing import Dict, Any
from app.auth.models import User
from app.billing.schemas import (
    PixSubscriptionResponse,
    BoletoSubscriptionResponse,
    CardHostedSubscriptionResponse,
    WebhookEvent,
)


class PaymentProvider(ABC):
    """
    Decoupled interface for payment gateways.
    Supports transparent PIX/Boleto and hosted Card checkout under Strategy pattern.
    """

    @abstractmethod
    async def create_pix_subscription(
        self,
        user: User,
        plan_id: str,
    ) -> PixSubscriptionResponse:
        pass

    @abstractmethod
    async def create_boleto_subscription(
        self,
        user: User,
        plan_id: str,
    ) -> BoletoSubscriptionResponse:
        pass

    @abstractmethod
    async def create_card_hosted_checkout(
        self,
        user: User,
        plan_id: str,
    ) -> CardHostedSubscriptionResponse:
        pass

    @abstractmethod
    async def cancel_subscription(self, subscription_id: str) -> bool:
        pass

    @abstractmethod
    async def parse_webhook(self, payload: bytes, headers: Dict[str, str]) -> WebhookEvent:
        pass
