"""Explicit, read-only refresh of allowlisted public reference data for CI. Never exports private user/portfolio/billing rows."""
import asyncio,json,re,gzip,os
from pathlib import Path
import asyncpg
ROOT=Path(__file__).resolve().parents[1]
PRIVATE={'core.usuario','core.carteira','core.posicao_custodia'}
ALLOWED={'core','analytics','asset_details','market','cms','suitability','canonical'}
async def main():
 value=os.environ['PUBLIC_FIXTURE_DATABASE_URL']
 value=value.replace('postgresql+asyncpg://','postgresql://').replace('sslmode=require','ssl=require')
 tables=set()
 for path in (ROOT/'app').rglob('*.py'):
  for schema,name in re.findall(r'\b(?:FROM|JOIN|INSERT INTO)\s+([a-z_][a-z_0-9]*)\.([a-z_][a-z_0-9]*)',path.read_text(),re.I):
   table=schema+'.'+name
   if schema in ALLOWED and table not in PRIVATE:tables.add(table)
 tickers=set()
 for path in (ROOT/'tests').glob('test_*.py'):
  tickers.update(re.findall(r'["\']([A-Z]{3,6}[0-9]{1,2}[A-Z]?)["\']',path.read_text()))
 c=await asyncpg.connect(value,timeout=15)
 result={'description':'Public market/reference snapshot only; no users, portfolios, billing or support records. CI is isolated from production.','snapshot_date':'2026-10-29','tables':[]}
 async with c.transaction(readonly=True):
  ids=[r[0] for r in await c.fetch('SELECT id_ativo FROM core.ativo WHERE ticker=ANY($1::text[])',sorted(tickers))]
  for table in sorted(tables):
   schema,name=table.split('.')
   columns=await c.fetch('''SELECT a.attname AS name,format_type(a.atttypid,a.atttypmod) AS type,t.typtype,pg_get_expr(d.adbin,d.adrelid) AS default,a.attidentity AS identity
     FROM pg_attribute a JOIN pg_type t ON a.atttypid=t.oid LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
     WHERE a.attrelid=to_regclass($1) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''',table)
   if not columns:continue
   fields=[]
   for col in columns:
    typ='text' if col['typtype']=='e' else col['type']
    if typ.startswith(('canonical.','core.','analytics.')):typ='text'
    default=col['default']
    if default and default.startswith('nextval('):typ='bigserial';default=None
    fields.append({'name':col['name'],'type':typ,'default':default})
   names=[x['name'] for x in fields]
   args=[];where=''
   if 'id_ativo' in names and table in {'market.cotacao_diaria','market.provento','market.desdobramento_split'}:where='WHERE id_ativo=ANY($1::int[])';args=[ids]
   if table=='cms.ticket_suporte':query=f'SELECT * FROM {table} WHERE false'
   elif table=='market.cotacao_diaria':query=f"SELECT DISTINCT ON(id_ativo,date_trunc('month',data_pregao)) * FROM {table} {where} ORDER BY id_ativo,date_trunc('month',data_pregao),data_pregao DESC"
   else:query=f'SELECT * FROM {table} {where} LIMIT 6000'
   rows=await c.fetch('SELECT row_to_json(snapshot)::text FROM ('+query+') snapshot',*args)
   data=[json.loads(r[0]) for r in rows]
   result['tables'].append({'name':table,'columns':fields,'rows':data})
   print(table,len(data),flush=True)
 await c.close()
 path=ROOT/'tests/fixtures/public_market_snapshot.json.gz';path.parent.mkdir(exist_ok=True)
 with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f:f.write(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode())
 print('Snapshot bytes:',path.stat().st_size)
asyncio.run(main())
