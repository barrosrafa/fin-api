"""Load only the checked-in public snapshot into an empty, local fin_ci database."""
import asyncio
import gzip
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/public_market_snapshot.json.gz'


async def load():
    url = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    target = urlsplit(url)
    if target.hostname not in ('localhost', '127.0.0.1', 'postgres') or target.path != '/fin_ci':
        raise RuntimeError('Fixture loading is restricted to a local disposable fin_ci database')
    snapshot = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    connection = await asyncpg.connect(url)
    try:
        if await connection.fetchval("SELECT to_regclass('core.ativo') IS NOT NULL"):
            raise RuntimeError('Fixture requires an empty database; no existing data will be replaced')
        async with connection.transaction():
            for schema in sorted({table['name'].split('.')[0] for table in snapshot['tables']}):
                await connection.execute(f'CREATE SCHEMA "{schema}"')
            for table in snapshot['tables']:
                columns = []
                for column in table['columns']:
                    default = column['default']
                    if default:
                        default = default.replace("uuid_generate_v4()", "gen_random_uuid()")
                    if default and any(schema + '.' in default for schema in ('core', 'canonical', 'analytics')):
                        default = None
                    if default and not (
                        default.startswith(("'", "ARRAY[", "now()", "gen_random_uuid()", "true", "false"))
                        or re.fullmatch(r"[-+]?[0-9.]+", default)
                    ):
                        # Generated expressions are captured as snapshot values, not DEFAULTs.
                        default = None
                    column_type = column['type']
                    if any(column_type.startswith(schema + '.') for schema in ('core', 'canonical', 'analytics', 'asset_details', 'market', 'suitability', 'cms')):
                        column_type = 'text[]' if column_type.endswith('[]') else 'text'
                    if column_type.startswith('vector'):
                        column_type = 'text'
                    columns.append('"' + column['name'] + '" ' + column_type + (f' DEFAULT {default}' if default else ''))
                await connection.execute('CREATE TABLE ' + table['name'] + ' (' + ','.join(columns) + ')')
                if table['rows']:
                    await connection.execute(
                        f"INSERT INTO {table['name']} SELECT * FROM jsonb_populate_recordset(NULL::{table['name']}, $1::jsonb)",
                        json.dumps(table['rows'], ensure_ascii=False),
                    )
            scenarios = FIXTURE.with_name('scenarios.sql')
            await connection.execute(scenarios.read_text())
        print(f"Loaded {len(snapshot['tables'])} public reference tables; no private customer data")
    finally:
        await connection.close()


if __name__ == '__main__':
    asyncio.run(load())
