"""Run only against a disposable database named fin_audit_test (never application data)."""
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database as database

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not os.getenv('TEST_POSTGRES_URL'), reason='Requires disposable PostgreSQL fin_audit_test')]


async def test_pool_one_rls_and_concurrent_order_uniqueness(monkeypatch):
    url = os.environ['TEST_POSTGRES_URL']
    assert url.split('?', 1)[0].endswith('/fin_audit_test'), 'Disposable database required'
    admin = await asyncpg.connect(url)
    suffix = uuid4().hex
    schema, role = 'audit_' + suffix, 'reader_' + suffix
    user_a, user_b, wallet = uuid4(), uuid4(), uuid4()
    engine = None
    try:
        await admin.execute(f'CREATE SCHEMA {schema}')
        await admin.execute(f'CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS')
        await admin.execute(f'''CREATE TABLE {schema}.usuario (id_usuario uuid PRIMARY KEY, id_externo text UNIQUE);
            CREATE TABLE {schema}.carteira (id_carteira uuid PRIMARY KEY, id_usuario uuid);
            ALTER TABLE {schema}.carteira ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {schema}.carteira FORCE ROW LEVEL SECURITY;
            CREATE POLICY owner ON {schema}.carteira USING
                (id_usuario = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
            GRANT USAGE ON SCHEMA {schema} TO {role};
            GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role};''')
        await admin.executemany(f'INSERT INTO {schema}.usuario VALUES ($1,$2)', [(user_a, 'subject-a'), (user_b, 'subject-b')])
        await admin.execute(f'INSERT INTO {schema}.carteira VALUES ($1,$2)', wallet, user_a)
        monkeypatch.setattr(database, 'TENANT_SQL', text(str(database.TENANT_SQL).replace('core.usuario', f'{schema}.usuario')))
        engine = create_async_engine(url.replace('postgresql://', 'postgresql+asyncpg://', 1),
            pool_size=1, max_overflow=0, connect_args={'server_settings': {'role': role}})
        factory = async_sessionmaker(engine, class_=AsyncSession, sync_session_class=database.TenantSession)
        query = text(f'SELECT id_carteira FROM {schema}.carteira')

        async def read(subject):
            async with factory() as session:
                if subject:
                    await database.bind_tenant(session, subject)
                expected = [wallet] if subject in ('subject-a', str(user_a)) else []
                for finish in (session.commit, session.rollback, session.commit):
                    assert list((await session.execute(query)).scalars()) == expected
                    await finish()
                return expected
        await read('subject-a')
        await read('subject-b')
        await read(None)
        await read(str(user_a))  # Local JWT subjects already contain internal IDs.
        await asyncio.gather(*(read('subject-a' if i % 2 else 'subject-b') for i in range(30)))
        await read(None)

        # Apply the actual additive migration twice and race five database clients.
        migration = Path(os.environ.get('FIN_DB_MIGRATION_PATH', Path(__file__).resolve().parents[2] / 'fin/sql/17_orders_idempotency/01_up.sql'))
        await admin.execute(f'CREATE TABLE {schema}.ordem (id_ordem bigserial PRIMARY KEY, id_carteira uuid NOT NULL)')
        parts = migration.read_text().replace('core.', schema + '.').split('-- Execute outside')
        for _ in range(2):
            await admin.execute(parts[0])
            await admin.execute('-- Execute outside' + parts[1])
        pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        try:
            async def insert():
                async with pool.acquire() as connection:
                    try:
                        await connection.execute(f'INSERT INTO {schema}.ordem (id_carteira,idempotency_key) VALUES ($1,$2)', wallet, 'same-intent')
                        return 'created'
                    except asyncpg.UniqueViolationError:
                        return 'duplicate'
            results = await asyncio.gather(*(insert() for _ in range(5)))
            assert results.count('created') == 1
            assert results.count('duplicate') == 4
            # Legacy NULL keys and identical keys in other wallets remain compatible.
            await admin.execute(f'INSERT INTO {schema}.ordem (id_carteira) VALUES ($1),($1)', wallet)
            await admin.execute(f'INSERT INTO {schema}.ordem (id_carteira,idempotency_key) VALUES ($1,$2)', uuid4(), 'same-intent')
        finally:
            await pool.close()
    finally:
        if engine:
            await engine.dispose()
        await admin.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await admin.execute(f'DROP ROLE IF EXISTS {role}')
        await admin.close()
