from ipaddress import ip_network
import pytest
from pydantic import ValidationError
from starlette.requests import Request
from app.config import Settings
from app.core.rate_limit import client_address


def address(peer, chain, trusted):
    request = Request({'type': 'http', 'client': (peer, 1234), 'headers': [(b'x-forwarded-for', chain.encode())]})
    return client_address(request, [ip_network(c) for c in trusted])


def test_forwarded_spoof_does_not_override_untrusted_socket():
    assert address('203.0.113.1', '1.2.3.4', ['10.0.0.0/8']) == '203.0.113.1'


def test_proxy_chain_uses_nearest_untrusted_client():
    assert address('10.0.0.2', '1.2.3.4, 203.0.113.9, 10.0.0.1', ['10.0.0.0/8']) == '203.0.113.9'
    assert address('10.0.0.2', 'invalid', ['10.0.0.0/8']) == '10.0.0.2'


@pytest.mark.parametrize('origin', ['*', 'https://*.vercel.app', 'https://site.test/path', 'https://user:pass@site.test'])
def test_rejects_non_exact_origins(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS=[origin])


def test_production_rejects_administrator_even_with_real_jwt():
    with pytest.raises(ValidationError, match='non-administrator'):
        Settings(_env_file=None, ENVIRONMENT='production', DEBUG=False,
                 CORS_ORIGINS=['https://fin.com.br'], SUPABASE_JWT_SECRET='a'*64,
                 DATABASE_URL='postgresql+asyncpg://avnadmin:private@db.test/fin')
