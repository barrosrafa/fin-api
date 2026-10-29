import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize('secret', ['', 'short', 'test-jwt-secret-key-at-least-32-chars-long'])
def test_production_rejects_missing_or_development_jwt_secret(secret):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, ENVIRONMENT='production', SUPABASE_JWT_SECRET=secret)
    assert 'input_value=' not in str(error.value)


def test_generated_secret_is_accepted_without_exposing_it_in_repr():
    secret = secrets.token_urlsafe(64)
    settings = Settings(_env_file=None, ENVIRONMENT='production', SUPABASE_JWT_SECRET=secret)
    assert settings.SUPABASE_JWT_SECRET == secret
    assert secret not in repr(settings)


def test_development_keeps_local_authentication_compatible():
    settings = Settings(_env_file=None, ENVIRONMENT='development')
    assert settings.SUPABASE_JWT_SECRET
