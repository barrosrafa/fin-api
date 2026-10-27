from abc import ABC, abstractmethod
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import User, UserClaims


class AuthProvider(ABC):
    """
    Abstract interface for authentication and identity providers.
    Ensures zero coupling between FastAPI routes and Supabase/Cognito/Auth0.
    """

    @abstractmethod
    async def validate_token(self, token: str) -> UserClaims:
        """Validates Bearer JWT signature, issuer, and expiration."""
        pass

    @abstractmethod
    async def get_or_create_user(
        self,
        claims: UserClaims,
        db_session: Optional[AsyncSession] = None,
    ) -> User:
        """Retrieves user profile with JIT provisioning in core.usuario."""
        pass
