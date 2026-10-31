"""API produces durable market commands; only fin-ingestion executes collection."""
import re
from uuid import UUID
from sqlalchemy import text
from app.core.exceptions import FinApiException, AssetNotListedException


def normalize_ticker(ticker):
    normalized = ticker.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.^=-]{0,19}', normalized):
        raise FinApiException('Invalid ticker', status_code=422)
    return normalized


async def enqueue_refresh(session, ticker):
    ticker = normalize_ticker(ticker)
    exists = await session.execute(text('SELECT 1 FROM core.ativo WHERE ticker=:ticker LIMIT 1'), {'ticker': ticker})
    if exists.scalar() is None:
        raise AssetNotListedException(ticker)
    result = await session.execute(text("""
        INSERT INTO ingestion.ingestion_task
            (policy_id,task_key,dataset_name,target_entity,reference_date,priority,max_attempts)
        SELECT policy_id,
            'api-refresh:' || :ticker || ':' || floor(extract(epoch FROM now()) / 300)::bigint::text,
            dataset_name, :ticker, (now() AT TIME ZONE 'America/Sao_Paulo')::date,
            priority, max_retries
        FROM ingestion.ingestion_policy
        WHERE policy_id='b3_daily_quotes' AND is_active
        ON CONFLICT(task_key) DO UPDATE SET task_key=EXCLUDED.task_key
        RETURNING task_id,status,attempts,created_at,updated_at
    """), {'ticker': ticker})
    row = result.mappings().first()
    if row is None:
        raise FinApiException('Market ingestion policy is unavailable', status_code=503)
    await session.commit()
    return dict(row)


async def get_task(session, task_id: UUID):
    result = await session.execute(text("""
        SELECT task_id,dataset_name,target_entity,status,attempts,max_attempts,
               created_at,updated_at,locked_until
        FROM ingestion.ingestion_task
        WHERE task_id=:task_id AND task_key LIKE 'api-refresh:%'
    """), {'task_id': task_id})
    row = result.mappings().first()
    if row is None:
        raise FinApiException('Task not found', status_code=404)
    return dict(row)
