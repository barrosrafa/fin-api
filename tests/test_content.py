import json
from unittest.mock import AsyncMock
import httpx
import pytest
from app.config import Settings
from app.content.service import ContentService
from app.core.exceptions import FinApiException


def settings():
    return Settings(_env_file=None, DIRECTUS_URL='http://cms.test', DIRECTUS_API_TOKEN='private')


@pytest.mark.asyncio
async def test_contract_only_exposes_published_fields_and_preserves_source_timestamp():
    async def respond(request):
        assert request.headers['authorization'] == 'Bearer private'
        assert request.url.params['filter[status][_eq]'] == 'published'
        return httpx.Response(200, json={'data': [{'title': 'Fin', 'published_at': '2026-10-30T20:00:00Z', 'private_field': 'must not escape'}]})
    redis = AsyncMock()
    redis.get.return_value = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        content = await ContentService(settings(), redis, client).get('home')
    assert content['meta']['as_of'] == '2026-10-30T20:00:00Z'
    assert content['meta']['stale'] is False
    assert 'private_field' not in content['data'][0]
    assert redis.set.await_count == 2


@pytest.mark.asyncio
async def test_cms_outage_returns_last_snapshot_as_stale_without_changing_version():
    snapshot = {'data': [{'title': 'Last valid'}], 'meta': {'stale': False, 'dataset_version': 'v1', 'as_of': '2026-10-29T00:00:00Z'}}
    redis = AsyncMock()
    redis.get.side_effect = [None, json.dumps(snapshot)]
    async def unavailable(request):
        return httpx.Response(503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        content = await ContentService(settings(), redis, client).get('home')
    assert content['meta']['stale'] is True
    assert content['meta']['dataset_version'] == 'v1'
    assert content['meta']['as_of'] == snapshot['meta']['as_of']


@pytest.mark.asyncio
async def test_unavailable_without_snapshot_is_503_never_empty_success():
    redis = AsyncMock()
    redis.get.return_value = None
    async def unavailable(request):
        return httpx.Response(503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(FinApiException) as error:
            await ContentService(settings(), redis, client).get('home')
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_valid_empty_dataset_is_distinct_from_upstream_failure():
    redis = AsyncMock()
    redis.get.return_value = None
    async def empty(request):
        return httpx.Response(200, json={'data': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(empty)) as client:
        content = await ContentService(settings(), redis, client).get('home')
    assert content['data'] == [] and content['meta']['stale'] is False


@pytest.mark.asyncio
async def test_ui_catalog_paginates_and_keeps_only_declared_fields():
    pages = []
    async def respond(request):
        page = int(request.url.params['page'])
        pages.append(page)
        assert request.url.params['sort'] == 'text_key'
        data = [{'text_key': f'text.{i}', 'value': 'Texto', 'private': 'secret'} for i in range(1000)] if page == 1 else [{'text_key': 'last', 'value': ''}]
        return httpx.Response(200, json={'data': data})
    redis = AsyncMock()
    redis.get.return_value = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await ContentService(settings(), redis, client).get('ui-texts')
    assert pages == [1, 2]
    assert len(result['data']) == 1001
    assert result['data'][-1]['value'] == ''
    assert 'private' not in result['data'][0]


@pytest.mark.asyncio
async def test_false_flag_survives_contract_and_environment_filter():
    async def respond(request):
        assert request.url.params['filter[environment][_eq]'] == settings().ENVIRONMENT
        return httpx.Response(200, json={'data': [{'flag_key': 'route./acoes', 'enabled': False}]})
    redis = AsyncMock()
    redis.get.return_value = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await ContentService(settings(), redis, client).get('feature-flags')
    assert result['data'][0]['enabled'] is False
