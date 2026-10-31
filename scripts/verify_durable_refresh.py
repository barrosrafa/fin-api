"""Exercise the HTTP refresh contract and concurrent idempotency on real PostgreSQL.

TEST_DATABASE_URL must point to an isolated, empty disposable database. Does not
use the application's DATABASE_URL and refuses to overwrite existing schemas.
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from httpx import ASGITransport, AsyncClient
from app.main import create_app
from app.core.database import get_async_session


async def main():
    url = os.environ['TEST_DATABASE_URL']
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA core'))
        await conn.execute(text('CREATE SCHEMA ingestion'))
        await conn.execute(text('CREATE TABLE core.ativo(ticker text PRIMARY KEY)'))
        await conn.execute(text("INSERT INTO core.ativo VALUES ('PETR4')"))
        await conn.execute(text('''CREATE TABLE ingestion.ingestion_policy(
            policy_id text PRIMARY KEY,dataset_name text,is_active boolean,
            priority integer,max_retries integer)'''))
        await conn.execute(text("INSERT INTO ingestion.ingestion_policy VALUES ('b3_daily_quotes','cotacao_diaria',true,2,5)"))
        await conn.execute(text('''CREATE TABLE ingestion.ingestion_task(
            task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),policy_id text,
            task_key text UNIQUE,dataset_name text,target_entity text,reference_date date,
            priority integer,max_attempts integer,status text DEFAULT 'PENDING',
            attempts integer DEFAULT 0,created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now(),locked_until timestamptz)'''))
    factory = async_sessionmaker(engine)
    async def session():
        async with factory() as db:
            yield db
    app = create_app()
    app.dependency_overrides[get_async_session] = session
    # The test has no Redis dependency: rate limiting has its own focused suite.
    from app.core.rate_limit import ApiRateLimitMiddleware
    app.user_middleware = [m for m in app.user_middleware if m.cls is not ApiRateLimitMiddleware]
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        first, second = await asyncio.gather(*[
            client.post('/api/v1/ingestion/refresh', json={'ticker': ' petr4 '}) for _ in range(2)
        ])
        assert first.status_code == second.status_code == 202
        assert first.json()['task_id'] == second.json()['task_id']
        response = await client.get(first.headers['Location'])
        assert response.status_code == 200 and response.json()['status'] == 'PENDING'
        unknown = await client.post('/api/v1/ingestion/refresh', json={'ticker': 'UNKNOWN99'})
        assert unknown.status_code == 404
        malformed = await client.post('/api/v1/ingestion/refresh', json={'ticker': 'x;DROP TABLE'})
        assert malformed.status_code == 422
        async with factory() as db:
            assert (await db.execute(text('SELECT count(*) FROM ingestion.ingestion_task'))).scalar() == 1
    await engine.dispose()
    print('PASS: real PostgreSQL HTTP 202, committed task, concurrent idempotency, UUID status, invalid/unknown ticker; one durable row.')


if __name__ == '__main__':
    asyncio.run(main())
