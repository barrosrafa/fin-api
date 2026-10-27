import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import jwt
from datetime import datetime, timezone, timedelta
from app.auth.models import User, UserRole, SubscriptionTier, UserClaims
from app.auth.contracts import AuthProvider
from app.auth.adapters.supabase import SupabaseAuthAdapter
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.auth.dependencies import require_role, require_tier

SECRET_KEY = "test-secret-at-least-32-chars-long"

def generate_test_jwt(sub: str, email: str, role: str = "user", tier: str = "free") -> str:
    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "app_metadata": {"tier": tier},
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

@pytest.mark.asyncio
async def test_validate_token_success():
    adapter = SupabaseAuthAdapter(jwt_secret=SECRET_KEY)
    token = generate_test_jwt("user_123", "investor@example.com", "analyst", "pro")
    
    claims = await adapter.validate_token(token)
    assert claims.sub == "user_123"
    assert claims.email == "investor@example.com"
    assert claims.role == UserRole.ANALYST
    assert claims.tier == SubscriptionTier.PRO

@pytest.mark.asyncio
async def test_validate_token_expired():
    adapter = SupabaseAuthAdapter(jwt_secret=SECRET_KEY)
    expired_payload = {
        "sub": "user_123",
        "email": "investor@example.com",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm="HS256")
    
    with pytest.raises(UnauthorizedException):
        await adapter.validate_token(expired_token)

@pytest.mark.asyncio
async def test_jit_user_creation_and_redis_cache():
    mock_redis = AsyncMock()
    # Cache miss on first call
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    mock_db = AsyncMock()
    # Mock DB query returning None (user not yet in core.usuario), then commits insert
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    adapter = SupabaseAuthAdapter(
        jwt_secret=SECRET_KEY,
        redis_client=mock_redis,
    )

    claims = UserClaims(
        sub="user_abc_789",
        email="newuser@fin.com",
        role=UserRole.USER,
        tier=SubscriptionTier.FREE,
    )

    user = await adapter.get_or_create_user(claims, db_session=mock_db)
    assert user.id == "user_abc_789"
    assert user.email == "newuser@fin.com"
    assert user.role == UserRole.USER
    assert user.tier == SubscriptionTier.FREE
    
    # Assert Redis cache set was called with 1 hour TTL
    mock_redis.set.assert_called_once()
    assert "user:user_abc_789:profile" in mock_redis.set.call_args[0][0]

@pytest.mark.asyncio
async def test_require_role_and_tier_guards():
    regular_user = User(
        id="u1",
        email="free@fin.com",
        role=UserRole.USER,
        tier=SubscriptionTier.FREE,
    )
    admin_user = User(
        id="u2",
        email="admin@fin.com",
        role=UserRole.ADMIN,
        tier=SubscriptionTier.ENTERPRISE,
    )

    # Role checks
    admin_checker = require_role(UserRole.ADMIN)
    assert await admin_checker(admin_user) is True
    with pytest.raises(ForbiddenException):
        await admin_checker(regular_user)

    # Tier checks
    pro_checker = require_tier(SubscriptionTier.PRO)
    assert await pro_checker(admin_user) is True
    with pytest.raises(ForbiddenException):
        await pro_checker(regular_user)
