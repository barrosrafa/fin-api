import hmac
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from app.config import Settings, get_settings
from app.core.exceptions import FinApiException
from app.core.redis import get_redis_client
from app.content.service import ContentService, DATASETS

router = APIRouter(prefix='/content', tags=['Content'])


class ContentMeta(BaseModel):
    source: str
    schema_version: str
    dataset_version: str
    as_of: str | None
    collected_at: str
    quality_status: str
    stale: bool


class ContentEnvelope(BaseModel):
    data: list[dict[str, Any]]
    meta: ContentMeta


async def content_service(settings: Annotated[Settings, Depends(get_settings)], redis=Depends(get_redis_client)):
    return ContentService(settings, redis)


@router.get('/articles', response_model=ContentEnvelope)
async def articles(service=Depends(content_service)):
    return await service.get('articles')


@router.get('/home', response_model=ContentEnvelope)
async def home(service=Depends(content_service)):
    return await service.get('home')


@router.get('/navigation', response_model=ContentEnvelope)
async def navigation(service=Depends(content_service)):
    return await service.get('navigation')


@router.get('/ui-texts', response_model=ContentEnvelope)
async def ui_texts(service=Depends(content_service)):
    return await service.get('ui-texts')


@router.get('/feature-flags', response_model=ContentEnvelope)
async def flags(service=Depends(content_service)):
    return await service.get('feature-flags')


@router.get('/glossary', response_model=ContentEnvelope)
async def glossary(service=Depends(content_service)):
    return await service.get('glossary')


@router.post('/webhook')
async def published(settings: Annotated[Settings, Depends(get_settings)],
                    authorization: Annotated[str | None, Header()] = None,
                    redis=Depends(get_redis_client)):
    # The Directus flow runs only after published mutations. Keep the previous
    # good snapshot while aliases refresh, so upstream outages can still fall back.
    expected = 'Bearer ' + settings.CMS_WEBHOOK_SECRET
    if not settings.CMS_WEBHOOK_SECRET or not hmac.compare_digest(authorization or '', expected):
        raise FinApiException('Invalid editorial webhook credential', status_code=401)
    service = ContentService(settings, redis)
    await redis.delete(*(service.key(dataset, 'current') for dataset in DATASETS))
    return {'status': 'invalidated'}
