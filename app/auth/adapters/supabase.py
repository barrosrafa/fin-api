import json
from typing import Optional
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from app.auth.contracts import AuthProvider
from app.auth.models import User, UserClaims, UserRole, SubscriptionTier
from app.core.exceptions import UnauthorizedException, FinApiException
from app.core.logging import logger
from app.core.database import bind_tenant


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
        if db_session is not None:
            await bind_tenant(db_session, claims.sub)
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
                INSERT INTO core.usuario (id_externo, email, nome, role, tier, status)
                VALUES (:id_externo, :email, :nome, :role, :tier, 'Ativo')
                ON CONFLICT (email) DO UPDATE SET
                    id_externo = EXCLUDED.id_externo,
                    ultimo_acesso = NOW()
                RETURNING id_usuario, nome, email, role, tier, status
                """
            )
            try:
                result = await db_session.execute(
                    stmt,
                    {
                        "id_externo": user.id,
                        "email": user.email,
                        "nome": user.name,
                        "role": UserRole.USER.value,
                        "tier": SubscriptionTier.FREE.value,
                    },
                )
                profile = result.mappings().one()
                user = User(id=str(profile["id_usuario"]), email=profile["email"], name=profile["nome"],
                            role=profile["role"] or "user", tier=profile["tier"] or "free",
                            is_active=(profile["status"] or "").lower() in {"ativo", "active"})
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                logger.error("JIT user synchronization failed")
                raise FinApiException("User profile temporarily unavailable", status_code=503) from None
            if not user.is_active:
                raise UnauthorizedException("Account is inactive")

        # Store in Redis Cache with 1 hour TTL
        if self.redis is not None:
            await self.redis.set(cache_key, json.dumps(user.model_dump()), ex=60)

        return user
