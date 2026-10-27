import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.billing.contracts import PaymentProvider
from app.billing.adapters.asaas import AsaasPaymentProvider
from app.billing.service import BillingService
from app.billing.schemas import (
    SubscriptionCreate,
    PaymentMethod,
    PixSubscriptionResponse,
    BoletoSubscriptionResponse,
    CardHostedSubscriptionResponse,
    WebhookEvent,
)
from app.auth.models import User, UserRole, SubscriptionTier

@pytest.mark.asyncio
async def test_asaas_create_pix_subscription():
    provider = AsaasPaymentProvider(api_key="test_key", environment="sandbox")
    
    mock_customer_resp = {"id": "cus_12345"}
    mock_sub_resp = {
        "id": "sub_67890",
        "value": 49.90,
        "status": "ACTIVE",
    }
    mock_pix_resp = {
        "encodedImage": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
        "payload": "00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000",
        "expirationDate": "2026-10-27 23:59:59",
    }

    with patch.object(provider, "_post", AsyncMock(side_effect=[mock_customer_resp, mock_sub_resp])):
        with patch.object(provider, "_get", AsyncMock(return_value=mock_pix_resp)):
            user = User(id="u1", email="investor@fin.com")
            result = await provider.create_pix_subscription(user=user, plan_id="plan_pro")

            assert isinstance(result, PixSubscriptionResponse)
            assert result.subscription_id == "sub_67890"
            assert result.qr_code_base64.startswith("data:image/png;base64")
            assert "br.gov.bcb.pix" in result.copy_paste_code

@pytest.mark.asyncio
async def test_asaas_create_card_hosted_checkout():
    provider = AsaasPaymentProvider(api_key="test_key", environment="sandbox")
    
    mock_customer_resp = {"id": "cus_12345"}
    mock_link_resp = {
        "id": "link_123",
        "url": "https://sandbox.asaas.com/c/abc123xyz",
    }

    with patch.object(provider, "_post", AsyncMock(side_effect=[mock_customer_resp, mock_link_resp])):
        user = User(id="u2", email="carduser@fin.com")
        result = await provider.create_card_hosted_checkout(user=user, plan_id="plan_pro")

        assert isinstance(result, CardHostedSubscriptionResponse)
        assert result.checkout_url == "https://sandbox.asaas.com/c/abc123xyz"

@pytest.mark.asyncio
async def test_webhook_idempotency_and_tier_upgrade():
    mock_redis = AsyncMock()
    # First time: setnx returns 1 (new event). Second time: returns 0 (duplicate).
    mock_redis.set = AsyncMock(side_effect=[True, False])
    mock_redis.delete = AsyncMock()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    service = BillingService(redis_client=mock_redis)

    event = WebhookEvent(
        event_id="evt_pay_999",
        event_type="PAYMENT_RECEIVED",
        customer_email="subscriber@fin.com",
        plan_tier=SubscriptionTier.PRO,
        amount=49.90,
    )

    # First delivery: processed, tier upgraded
    processed = await service.handle_webhook_event(event, db_session=mock_db)
    assert processed is True
    mock_db.commit.assert_called_once()
    mock_redis.delete.assert_called_with("user:subscriber@fin.com:profile")

    # Second delivery: duplicate ignored
    processed_duplicate = await service.handle_webhook_event(event, db_session=mock_db)
    assert processed_duplicate is False


@pytest.mark.asyncio
async def test_webhook_unauthorized_without_secret():
    from app.main import create_app
    from httpx import AsyncClient, ASGITransport

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Calling webhook without asaas-access-token header must return 401
        res = await client.post("/api/v1/billing/webhooks/asaas", json={"event": "TEST"})
        assert res.status_code == 401
        assert "Invalid or missing asaas-access-token" in res.json()["message"]
