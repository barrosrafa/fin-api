"""Real HTTP registration + tenant tests using the actual restricted runtime role.

Only an isolated local fin_ci database is accepted. Apply migration 18 first.
"""
import asyncio
import os
from urllib.parse import urlsplit
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.core.database import get_async_session, TenantSession, bind_tenant
from app.core.rate_limit import ApiRateLimitMiddleware


async def main():
    url = os.environ['TEST_RUNTIME_DATABASE_URL']
    parsed = urlsplit(url)
    assert parsed.hostname in ('localhost', '127.0.0.1') and parsed.path == '/fin_ci'
    admin = create_async_engine(url)
    engine = create_async_engine(url, pool_size=1, max_overflow=0,
        connect_args={'server_settings': {'role': 'fin_api_rw'}})
    factory = async_sessionmaker(engine, class_=AsyncSession, sync_session_class=TenantSession)
    async def session():
        async with factory() as db:
            yield db
    app = create_app()
    app.dependency_overrides[get_async_session] = session
    app.user_middleware = [m for m in app.user_middleware if m.cls is not ApiRateLimitMiddleware]
    ids = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            for _ in range(2):
                email = 'rls-' + uuid4().hex + '@fin.com'
                response = await client.post('/api/v1/auth/register', json={
                    'name': 'Disposable runtime verification', 'email': email, 'password': 'Runtime-Isolation-123!'})
                assert response.status_code == 201, (response.status_code, response.text)
                ids.append(response.json()['user']['id'])
                login = await client.post('/api/v1/auth/login', json={'email': email, 'password': 'Runtime-Isolation-123!'})
                assert login.status_code == 200
                wallets = await client.get('/api/v1/portfolio/wallets', headers={'Authorization': 'Bearer ' + login.json()['token']})
                assert wallets.status_code == 200
                assert len(wallets.json()) == 1
        for subject in [ids[0], ids[1], None, ids[0], None]:
            async with factory() as db:
                if subject:
                    await bind_tenant(db, subject)
                for finish in (db.commit, db.rollback, db.commit):
                    rows = (await db.execute(text('SELECT id_usuario::text FROM core.carteira'))).scalars().all()
                    assert set(rows) == ({subject} if subject else set()), rows
                    await finish()
                if subject == ids[0]:
                    changed = await db.execute(text('UPDATE core.carteira SET nome_carteira=nome_carteira WHERE id_usuario=:other'), {'other': ids[1]})
                    assert changed.rowcount == 0
                    await db.rollback()
                if subject:
                    try:
                        async with db.begin_nested():
                            await db.execute(text("UPDATE core.usuario SET role='admin' WHERE id_usuario=:id"), {'id': subject})
                    except DBAPIError as error:
                        assert getattr(error.orig, 'sqlstate', None) == '42501'
                    else:
                        raise AssertionError('Runtime was allowed to grant administrator role')
                try:
                    async with db.begin_nested():
                        await db.execute(text('CREATE TABLE core._forbidden_runtime_ddl(id integer)'))
                except DBAPIError as error:
                    assert getattr(error.orig, 'sqlstate', None) == '42501'
                else:
                    raise AssertionError('Runtime was allowed DDL')
        print('PASS: real restricted runtime registration/login, private wallets, no tenant leakage across pool reuse, cross-user update denied and DDL denied.')
    finally:
        async with admin.begin() as connection:
            for identifier in ids:
                await connection.execute(text('DELETE FROM core.carteira WHERE id_usuario=:id'), {'id': identifier})
                await connection.execute(text('DELETE FROM core.usuario WHERE id_usuario=:id'), {'id': identifier})
        await engine.dispose()
        await admin.dispose()


if __name__ == '__main__':
    asyncio.run(main())
