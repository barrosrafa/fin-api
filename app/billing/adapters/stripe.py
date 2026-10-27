from typing import Dict, Any
from app.auth.models import User
from app.billing.contracts import PaymentProvider
from app.billing.schemas import (
    PixSubscriptionResponse,
    BoletoSubscriptionResponse,
    CardHostedSubscriptionResponse,
    WebhookEvent,
)
from app.core.exceptions import FinApiException


class StripePaymentProvider(PaymentProvider):
    """
    Stripe international adapter (ready for USD/EUR expansion).
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def create_pix_subscription(self, user: User, plan_id: str) -> PixSubscriptionResponse:
        raise FinApiException("PIX recurring is not natively supported via Stripe provider; use Asaas.")

    async def create_boleto_subscription(self, user: User, plan_id: str) -> BoletoSubscriptionResponse:
        raise FinApiException("Boleto is not recommended via Stripe; use Asaas.")

    async def create_card_hosted_checkout(self, user: User, plan_id: str) -> CardHostedSubscriptionResponse:
        return CardHostedSubscriptionResponse(
            subscription_id="sub_stripe_mock",
            checkout_url="https://checkout.stripe.com/pay/cs_test_mock",
        )

    async def cancel_subscription(self, subscription_id: str) -> bool:
        return True

    async def parse_webhook(self, payload: bytes, headers: Dict[str, str]) -> WebhookEvent:
        return WebhookEvent(
            event_id="evt_stripe_mock",
            event_type="invoice.payment_succeeded",
            customer_email="test@stripe.com",
        )
