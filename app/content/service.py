"""Published editorial contracts with bounded cache and explicit stale fallback."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import httpx
from app.core.exceptions import FinApiException
from app.core.logging import logger

DATASETS = {
    'ui-texts': ('ui_texts', 'text_key,value,published_at,date_updated'),
    'articles': ('articles', 'id,slug,title,excerpt,body,author_name,category,tags,reading_time_minutes,is_premium,published_at,date_updated'),
    'home': ('home_settings', 'slug,title,subtitle,banner,published_at,date_updated'),
    'navigation': ('navigation', 'slug,label,href,position,published_at,date_updated'),
    'feature-flags': ('feature_flags', 'flag_key,enabled,environment,published_at,date_updated'),
    'glossary': ('glossary_terms', 'id,slug,term,short_definition,definition,category,formula,published_at,date_updated'),
}


class ContentService:
    def __init__(self, settings, redis, client=None):
        self.settings, self.redis, self.client = settings, redis, client

    def key(self, dataset, variant):
        return f'content:{dataset}:pt-BR:{self.settings.ENVIRONMENT}:{variant}'

    async def cached(self, dataset, variant):
        try:
            async with asyncio.timeout(0.25):
                raw = await self.redis.get(self.key(dataset, variant))
            if raw and len(raw) <= 2097152:
                return json.loads(raw)
        except Exception:
            logger.warning('Editorial cache read unavailable')
        return None

    async def get(self, dataset):
        cached = await self.cached(dataset, 'current')
        if cached:
            return cached
        try:
            if not self.settings.DIRECTUS_URL or not self.settings.DIRECTUS_API_TOKEN:
                raise RuntimeError('CMS not configured')
            collection, fields = DATASETS[dataset]
            params = {'fields': fields, 'limit': 1000, 'filter[status][_eq]': 'published', 'filter[locale][_eq]': 'pt-BR'}
            if dataset == 'navigation':
                params['sort'] = 'position,id'
            if dataset == 'ui-texts':
                params['sort'] = 'text_key'
            if dataset == 'feature-flags':
                params['sort'] = 'flag_key'
                params['filter[environment][_eq]'] = self.settings.ENVIRONMENT
            async def fetch(client):
                rows = []
                size = 0
                # Bounded pagination: catalogs must not silently stop after 100 records.
                for page in range(1, 21):
                    response = await client.get(f'{self.settings.DIRECTUS_URL.rstrip("/")}/items/{collection}',
                        params={**params, 'page': page}, headers={'Authorization': f'Bearer {self.settings.DIRECTUS_API_TOKEN}'})
                    response.raise_for_status()
                    size += len(response.content)
                    if size > 2097152:
                        raise ValueError('Editorial snapshot exceeds limit')
                    data = response.json()['data']
                    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                        raise ValueError('Invalid CMS contract')
                    allowed = set(fields.split(','))
                    rows.extend({key: value for key, value in row.items() if key in allowed} for row in data)
                    if len(data) < 1000:
                        return rows
                raise ValueError('Editorial catalog exceeds page limit')
            if self.client:
                data = await fetch(self.client)
            else:
                async with httpx.AsyncClient(timeout=3.0, follow_redirects=False) as client:
                    data = await fetch(client)
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:20]
            published = [row['published_at'] for row in data if row.get('published_at')]
            result = {'data': data, 'meta': {'source': 'directus', 'schema_version': '1',
                'dataset_version': digest, 'as_of': max(published) if published else None,
                'collected_at': datetime.now(timezone.utc).isoformat(), 'quality_status': 'published', 'stale': False}}
            try:
                async with asyncio.timeout(0.5):
                    raw = json.dumps(result)
                    await self.redis.set(self.key(dataset, 'last-valid'), raw, ex=604800)
                    await self.redis.set(self.key(dataset, 'current'), raw, ex=60)
            except Exception:
                logger.warning('Editorial cache write unavailable')
            return result
        except Exception:
            cached = await self.cached(dataset, 'last-valid')
            if cached:
                cached['meta']['stale'] = True
                return cached
            raise FinApiException('Editorial content temporarily unavailable', status_code=503) from None
