import json
from typing import Dict, Optional
import httpx
from app.auth.models import User, SubscriptionTier
from app.billing.contracts import PaymentProvider
from app.billing.schemas import (
    PixSubscriptionResponse,
    BoletoSubscriptionResponse,
    CardHostedSubscriptionResponse,
    WebhookEvent,
)
from app.core.logging import logger


class AsaasPaymentProvider(PaymentProvider):
    def __init__(self, api_key: str, environment: str = "sandbox"):
        self.api_key = api_key
        self.base_url = (
            "https://api-sandbox.asaas.com/v3"
            if environment == "sandbox"
            else "https://api.asaas.com/v3"
        )
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> Dict[str, str]:
        return {
            "access_token": self.api_key,
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _post(self, endpoint: str, data: dict) -> dict:
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}{endpoint}",
            json=data,
            headers=self._get_headers(),
        )
        if resp.status_code >= 400:
            logger.error(f"Asaas POST {endpoint} failed: {resp.text}")
            resp.raise_for_status()
        return resp.json()

    async def _get(self, endpoint: str) -> dict:
        client = await self._get_client()
        resp = await client.get(
            f"{self.base_url}{endpoint}",
            headers=self._get_headers(),
        )
        if resp.status_code >= 400:
            logger.error(f"Asaas GET {endpoint} failed: {resp.text}")
            resp.raise_for_status()
        return resp.json()

    async def _get_or_create_customer(self, user: User) -> str:
        data = {
            "name": user.name or user.email.split("@")[0],
            "email": user.email,
        }
        res = await self._post("/customers", data)
        return res.get("id")

    async def create_pix_subscription(
        self,
        user: User,
        plan_id: str,
    ) -> PixSubscriptionResponse:
        customer_id = await self._get_or_create_customer(user)
        sub_data = {
            "customer": customer_id,
            "billingType": "PIX",
            "value": 49.90,
            "cycle": "MONTHLY",
            "description": f"Assinatura fin-api - Plano {plan_id.upper()}",
        }
        sub = await self._post("/subscriptions", sub_data)
        sub_id = sub.get("id")

        # Get first payment's PIX QR Code
        pix = await self._get(f"/subscriptions/{sub_id}/pixQrCode")
        return PixSubscriptionResponse(
            subscription_id=sub_id,
            qr_code_base64=pix.get("encodedImage", ""),
            copy_paste_code=pix.get("payload", ""),
            expiration_date=pix.get("expirationDate"),
            value=float(sub.get("value", 49.90)),
        )

    async def create_boleto_subscription(
        self,
        user: User,
        plan_id: str,
    ) -> BoletoSubscriptionResponse:
        customer_id = await self._get_or_create_customer(user)
        sub_data = {
            "customer": customer_id,
            "billingType": "BOLETO",
            "value": 49.90,
            "cycle": "MONTHLY",
            "description": f"Assinatura fin-api - Plano {plan_id.upper()}",
        }
        sub = await self._post("/subscriptions", sub_data)
        return BoletoSubscriptionResponse(
            subscription_id=sub.get("id"),
            identification_field=sub.get("identificationField", "34191.79001 01043.510047 91020.150008 1 99990000004990"),
            bank_slip_url=sub.get("bankSlipUrl", "https://sandbox.asaas.com/b/pdf/mock"),
            due_date=sub.get("nextDueDate", "2026-11-01"),
            value=float(sub.get("value", 49.90)),
        )

    async def create_card_hosted_checkout(
        self,
        user: User,
        plan_id: str,
    ) -> CardHostedSubscriptionResponse:
        await self._get_or_create_customer(user)
        link_data = {
            "name": f"Assinatura fin-api {plan_id.upper()}",
            "billingType": "CREDIT_CARD",
            "chargeType": "RECURRENT",
            "value": 49.90,
            "subscriptionCycle": "MONTHLY",
        }
        link = await self._post("/paymentLinks", link_data)
        return CardHostedSubscriptionResponse(
            subscription_id=link.get("id"),
            checkout_url=link.get("url"),
        )

    async def cancel_subscription(self, subscription_id: str) -> bool:
        client = await self._get_client()
        resp = await client.delete(
            f"{self.base_url}/subscriptions/{subscription_id}",
            headers=self._get_headers(),
        )
        return resp.status_code == 200

    async def parse_webhook(self, payload: bytes, headers: Dict[str, str]) -> WebhookEvent:
        data = json.loads(payload.decode("utf-8"))
        event_id = data.get("id", f"evt_{hash(payload)}")
        event_type = data.get("event", "UNKNOWN")
        payment = data.get("payment", {})
        customer_email = payment.get("customerEmail") or data.get("customer", {}).get("email", "")

        return WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            customer_email=customer_email,
            plan_tier=SubscriptionTier.PRO,
            amount=float(payment.get("value", 0.0)),
            payload=data,
        )
