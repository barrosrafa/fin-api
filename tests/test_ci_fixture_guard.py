from unittest.mock import AsyncMock

import pytest

from scripts.load_ci_fixture import load


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'postgresql://user:secret@production.example/fin_ci',
    'postgresql://postgres@127.0.0.1/neondb',
    'postgresql://postgres@localhost/fin_audit_test',
])
async def test_reference_loader_refuses_non_disposable_targets_before_connecting(monkeypatch, url):
    connection = AsyncMock()
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr('scripts.load_ci_fixture.asyncpg.connect', connection)
    with pytest.raises(RuntimeError, match='local disposable fin_ci'):
        await load()
    connection.assert_not_called()
