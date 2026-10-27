from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.auth.models import SubscriptionTier


class PaymentMethod(str, Enum):
    PIX = "PIX"
    BOLETO = "BOLETO"
    CREDIT_CARD = "CREDIT_CARD"


class SubscriptionCreate(BaseModel):
    plan_tier: SubscriptionTier
    payment_method: PaymentMethod


class PixSubscriptionResponse(BaseModel):
    subscription_id: str
    qr_code_base64: str
    copy_paste_code: str
    expiration_date: Optional[str] = None
    value: float


class BoletoSubscriptionResponse(BaseModel):
    subscription_id: str
    identification_field: str
    bank_slip_url: str
    due_date: str
    value: float


class CardHostedSubscriptionResponse(BaseModel):
    subscription_id: str
    checkout_url: str


class WebhookEvent(BaseModel):
    event_id: str
    event_type: str
    customer_email: str
    plan_tier: SubscriptionTier = SubscriptionTier.PRO
    amount: float = 0.0
    payload: Dict[str, Any] = {}
