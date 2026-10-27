from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.billing.schemas import WebhookEvent
from app.auth.models import SubscriptionTier
from app.core.logging import logger


class BillingService:
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client

    async def handle_webhook_event(
        self,
        event: WebhookEvent,
        db_session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Idempotent webhook event processor.
        Guarantees that duplicate gateway events don't duplicate transactions or upgrades.
        """
        # Step 1: Redis Idempotency Gate (24h TTL)
        if self.redis is not None:
            idempotency_key = f"webhook:{event.event_id}"
            acquired = await self.redis.set(idempotency_key, "1", nx=True, ex=86400)
            if not acquired:
                logger.info(f"Duplicate webhook {event.event_id} safely ignored.")
                return False

        logger.info(f"Processing webhook {event.event_id}: type={event.event_type}, email={event.customer_email}")

        # Step 2: Handle subscription upgrade on confirmation
        confirmed_events = ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED", "invoice.payment_succeeded")
        if event.event_type in confirmed_events and event.customer_email:
            if db_session is not None:
                stmt = text(
                    """
                    UPDATE core.usuario
                    SET tier = :tier, atualizado_em = NOW()
                    WHERE email = :email
                    """
                )
                try:
                    res = await db_session.execute(
                        stmt,
                        {"tier": event.plan_tier.value, "email": event.customer_email},
                    )
                    await db_session.commit()

                    # Query id_externo to invalidate external user ID cache key as well
                    id_res = await db_session.execute(
                        text("SELECT id_externo FROM core.usuario WHERE email = :email LIMIT 1"),
                        {"email": event.customer_email},
                    )
                    id_externo = id_res.scalar_one_or_none()
                    if id_externo and self.redis is not None:
                        await self.redis.delete(f"user:{id_externo}:profile")
                except Exception as e:
                    logger.error(f"Error updating user tier on webhook: {e}")

            # Invalidate Redis profile cache so next API call immediately sees new tier
            if self.redis is not None:
                await self.redis.delete(f"user:{event.customer_email}:profile")

        return True
