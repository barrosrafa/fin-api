from enum import Enum
from pydantic import BaseModel, EmailStr
from typing import Optional


class UserRole(str, Enum):
    USER = "user"
    ANALYST = "analyst"
    ADMIN = "admin"


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    @property
    def rank(self) -> int:
        ranks = {
            SubscriptionTier.FREE: 1,
            SubscriptionTier.PRO: 2,
            SubscriptionTier.ENTERPRISE: 3,
        }
        return ranks.get(self, 1)


class UserClaims(BaseModel):
    sub: str
    email: EmailStr
    role: UserRole = UserRole.USER
    tier: SubscriptionTier = SubscriptionTier.FREE


class User(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    role: UserRole = UserRole.USER
    tier: SubscriptionTier = SubscriptionTier.FREE
    is_active: bool = True
