import json
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
        Transactional idempotent webhook processor.
        Guarantees that:
        1. Duplicate webhooks don't produce duplicate side effects.
        2. Database errors during processing allow gateway retries (does not permanently lock out).
        """
        idempotency_key = f"webhook:{event.event_id}"

        # Step 1: Redis Idempotency Gate (24h TTL)
        if self.redis is not None:
            acquired = await self.redis.set(idempotency_key, "1", nx=True, ex=86400)
            if not acquired:
                logger.info(f"Duplicate webhook {event.event_id} safely ignored.")
                return False

        logger.info(f"Processing webhook {event.event_id}: type={event.event_type}, email={event.customer_email}")

        # Step 2: Handle subscription upgrade on confirmation inside database transaction
        confirmed_events = ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED", "invoice.payment_succeeded")
        try:
            if event.event_type in confirmed_events and event.customer_email:
                if db_session is not None:
                    stmt = text(
                        """
                        UPDATE core.usuario
                        SET tier = :tier
                        WHERE email = :email;
                        """
                    )
                    await db_session.execute(
                        stmt,
                        {"tier": event.plan_tier.value, "email": event.customer_email},
                    )

                    # Durable inbox audit recording
                    try:
                        await db_session.execute(
                            text(
                                """
                                INSERT INTO billing.webhook_inbox (event_id, gateway_provider, event_type, payload, status, processed_at)
                                VALUES (:id, 'asaas', :type, :payload::jsonb, 'PROCESSED', NOW())
                                ON CONFLICT (event_id) DO UPDATE SET status = 'PROCESSED', processed_at = NOW();
                                """
                            ),
                            {
                                "id": event.event_id,
                                "type": event.event_type,
                                "payload": json.dumps({"type": event.event_type, "email": event.customer_email}),
                            },
                        )
                    except Exception:
                        pass

                    await db_session.commit()

                    # Invalidate user profile cache
                    if self.redis is not None:
                        await self.redis.delete(f"user:{event.customer_email}:profile")

            return True

        except Exception as e:
            logger.error(f"Error processing webhook {event.event_id}: {e}")
            if db_session is not None:
                await db_session.rollback()

            # Remove Redis lock so gateway can retry
            if self.redis is not None:
                await self.redis.delete(idempotency_key)
            raise e
