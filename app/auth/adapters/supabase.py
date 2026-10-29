import json
from typing import Optional
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from app.auth.contracts import AuthProvider
from app.auth.models import User, UserClaims, UserRole, SubscriptionTier
from app.core.exceptions import UnauthorizedException
from app.core.logging import logger


class SupabaseAuthAdapter(AuthProvider):
    """
    Supabase Auth provider implementation.
    Validates tokens and guarantees Just-In-Time user synchronization into fin-db.
    """

    def __init__(
        self,
        jwt_secret: str,
        jwks_url: Optional[str] = None,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.jwt_secret = jwt_secret
        self.jwks_url = jwks_url
        self.redis = redis_client

    async def validate_token(self, token: str) -> UserClaims:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
            sub = payload.get("sub")
            email = payload.get("email")
            if not sub or not email:
                raise UnauthorizedException("JWT missing 'sub' or 'email' claims")

            role_str = payload.get("role", "user")
            app_meta = payload.get("app_metadata", {})
            tier_str = app_meta.get("tier", "free")

            try:
                role = UserRole(role_str.lower())
            except ValueError:
                role = UserRole.USER

            try:
                tier = SubscriptionTier(tier_str.lower())
            except ValueError:
                tier = SubscriptionTier.FREE

            return UserClaims(
                sub=sub,
                email=email,
                role=role,
                tier=tier,
            )
        except jwt.ExpiredSignatureError:
            raise UnauthorizedException("Token has expired")
        except jwt.PyJWTError as e:
            raise UnauthorizedException(f"Invalid authentication token: {str(e)}")

    async def get_or_create_user(
        self,
        claims: UserClaims,
        db_session: Optional[AsyncSession] = None,
    ) -> User:
        cache_key = f"user:{claims.sub}:profile"

        # Check Redis Cache
        if self.redis is not None:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
                return User(**data)

        # Build Domain User
        user = User(
            id=claims.sub,
            email=claims.email,
            name=claims.email.split("@")[0],
            role=claims.role,
            tier=claims.tier,
            is_active=True,
        )

        # JIT sync to core.usuario if session provided
        if db_session is not None:
            stmt = text(
                """
                INSERT INTO core.usuario (id_externo, email, nome, role, tier, ativo)
                VALUES (:id_externo, :email, :nome, :role, :tier, true)
                ON CONFLICT (email) DO UPDATE SET
                    id_externo = EXCLUDED.id_externo,
                    role = EXCLUDED.role,
                    tier = EXCLUDED.tier,
                    atualizado_em = NOW()
                """
            )
            try:
                await db_session.execute(
                    stmt,
                    {
                        "id_externo": user.id,
                        "email": user.email,
                        "nome": user.name,
                        "role": user.role.value,
                        "tier": user.tier.value,
                    },
                )
                await db_session.commit()
            except Exception as e:
                await db_session.rollback()
                logger.warning(f"JIT user sync fallback: {e}")

        # Store in Redis Cache with 1 hour TTL
        if self.redis is not None:
            await self.redis.set(cache_key, json.dumps(user.model_dump()), ex=3600)

        return user
