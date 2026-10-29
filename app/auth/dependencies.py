from typing import Annotated, Callable, Optional
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.core.database import get_async_session, bind_tenant
from app.core.redis import get_redis_client
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.auth.contracts import AuthProvider
from app.auth.adapters.supabase import SupabaseAuthAdapter
from app.auth.models import User, UserRole, SubscriptionTier

security_scheme = HTTPBearer(auto_error=False)


async def get_auth_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthProvider:
    redis = await get_redis_client()
    return SupabaseAuthAdapter(
        jwt_secret=settings.SUPABASE_JWT_SECRET,
        jwks_url=settings.SUPABASE_JWKS_URL,
        redis_client=redis,
    )


async def get_current_user(
    auth_header: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security_scheme)],
    auth_provider: Annotated[AuthProvider, Depends(get_auth_provider)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    if not auth_header or not auth_header.credentials:
        raise UnauthorizedException("Missing Authorization Bearer token")

    claims = await auth_provider.validate_token(auth_header.credentials)
    user = await auth_provider.get_or_create_user(claims, db_session=db)
    
    # Enforce PostgreSQL Row-Level Security (RLS) tenant isolation
    if db is not None:
        await bind_tenant(db, str(user.id))
    
    return user


def require_role(min_role: UserRole) -> Callable[[User], bool]:
    async def role_checker(user: User = Depends(get_current_user)) -> bool:
        if min_role == UserRole.ADMIN and user.role != UserRole.ADMIN:
            raise ForbiddenException("Administrator role required")
        if min_role == UserRole.ANALYST and user.role not in (UserRole.ANALYST, UserRole.ADMIN):
            raise ForbiddenException("Analyst or higher role required")
        return True

    return role_checker


def require_tier(min_tier: SubscriptionTier) -> Callable[[User], bool]:
    async def tier_checker(user: User = Depends(get_current_user)) -> bool:
        if user.tier.rank < min_tier.rank:
            raise ForbiddenException(f"Subscription tier '{min_tier.value}' or higher required")
        return True

    return tier_checker
