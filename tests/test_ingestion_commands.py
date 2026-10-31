from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.ingestion.commands import enqueue_refresh
from app.core.exceptions import FinApiException
from app.market.service import MarketService


def result(row=None, scalar=None):
    value = MagicMock()
    value.scalar.return_value = scalar
    value.mappings.return_value.first.return_value = row
    return value


@pytest.mark.asyncio
async def test_enqueue_commits_real_task_before_return():
    task_id = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [result(scalar=1), result({'task_id': task_id, 'status': 'PENDING'})]
    task = await enqueue_refresh(db, ' petr4 ')
    assert task['task_id'] == task_id
    db.commit.assert_awaited_once()
    assert db.execute.call_args.args[1]['ticker'] == 'PETR4'


@pytest.mark.asyncio
async def test_inactive_policy_cannot_claim_accepted_work():
    db = AsyncMock()
    db.execute.side_effect = [result(scalar=1), result()]
    with pytest.raises(FinApiException) as error:
        await enqueue_refresh(db, 'PETR4')
    assert error.value.status_code == 503
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_ticker_never_opens_queue():
    db = AsyncMock()
    with pytest.raises(FinApiException):
        await enqueue_refresh(db, 'invalid; DROP TABLE')
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('state,expected,progress', [(None,'idle',0), ('PENDING','in_progress',0), ('RUNNING','in_progress',0), ('FAILED','failed',0), ('COMPLETED','completed',100)])
async def test_legacy_status_uses_actual_ledger(state, expected, progress):
    db = AsyncMock()
    db.execute.return_value = result(scalar=state)
    status = await MarketService().get_sync_status('PETR4', db_session=db)
    assert status.status == expected
    assert status.progress == progress
