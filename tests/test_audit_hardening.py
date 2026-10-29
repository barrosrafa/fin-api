import asyncio
import os
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from app.config import Settings
from app.core.database import TenantSession, _apply_tenant, bind_tenant
from app.core.rate_limit import ApiRateLimitMiddleware, TOKEN_BUCKET_LUA
from app.main import create_app


@pytest.mark.asyncio
async def test_tenant_binding_is_parameterized_and_reapplied():
    db = AsyncMock()
    db.info = {}
    await bind_tenant(db, "subject'; RESET ALL; --")
    assert db.info['auth_subject'] == "subject'; RESET ALL; --"
    sql, params = db.execute.call_args.args
    assert params['subject'] not in str(sql)
    assert 'id_usuario::text' in str(sql)
    assert 'set_config' in str(sql) and ', true)' in str(sql)
    connection = MagicMock()
    session = TenantSession()
    _apply_tenant(session, None, connection)
    assert "'', true" in str(connection.execute.call_args.args[0])
    session.info['auth_subject'] = 'A'
    for _ in range(3):
        _apply_tenant(session, None, connection)
        assert connection.execute.call_args.args[1] == {'subject': 'A'}
    session.close()


@pytest.mark.asyncio
async def test_private_cache_and_readiness_status():
    app = create_app()
    with patch('app.core.rate_limit.get_redis_client', AsyncMock(side_effect=ConnectionError())), \
         patch('app.main.get_redis_client', AsyncMock(side_effect=ConnectionError())), \
         patch('app.core.database.get_session_factory', side_effect=RuntimeError('offline')):
        async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
            response = await client.get('/api/v1/portfolio/demo/positions')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'private, no-store'
            assert (await client.get('/ready')).status_code == 503
            assert (await client.get('/health')).status_code == 200


@pytest.mark.asyncio
async def test_outage_fallback_and_forwarded_header_cannot_bypass_limit():
    settings = Settings(API_RATE_LIMIT_BURST=2, API_RATE_LIMIT_PER_MINUTE=1)
    app = create_app()
    # Use one explicitly configured instance for deterministic limits.
    from fastapi import FastAPI
    app = FastAPI()
    app.add_middleware(ApiRateLimitMiddleware, settings=settings)
    @app.get('/api/v1/ping')
    async def ping():
        return {'ok': True}
    with patch('app.core.rate_limit.get_redis_client', AsyncMock(side_effect=ConnectionError())):
        async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
            assert (await client.get('/api/v1/ping')).status_code == 200
            assert (await client.get('/api/v1/ping')).status_code == 200
            response = await client.get('/api/v1/ping', headers={'X-Forwarded-For': '1.2.3.4'})
            assert response.status_code == 429
            assert int(response.headers['retry-after']) > 0


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('TEST_REDIS_URL'), reason='Requires isolated test Redis')
async def test_atomic_bucket_across_simultaneous_clients():
    a, b = Redis.from_url(os.environ['TEST_REDIS_URL']), Redis.from_url(os.environ['TEST_REDIS_URL'])
    key = 'test:api:' + uuid4().hex
    try:
        results = await asyncio.gather(*[
            (a if i % 2 else b).eval(TOKEN_BUCKET_LUA, 1, key, 3, 0.01) for i in range(20)
        ])
        assert results.count(0) == 3
        assert await a.ttl(key) > 0
    finally:
        await a.delete(key)
        await a.aclose()
        await b.aclose()
