"""The evidence gate is exercised against real isolated PostgreSQL, never production."""
from datetime import date, timedelta

import asyncpg
import pytest
from app.market.quality import verified_market_text


@pytest.fixture
def database(tmp_path):
    import pgserver
    server = pgserver.get_server(tmp_path / 'postgres', cleanup_mode='stop')
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.mark.asyncio
async def test_verified_quotes_use_exact_identity_date_currency_and_ohlc(database):
    conn = await asyncpg.connect(database)
    try:
        await conn.execute('''
            CREATE SCHEMA core; CREATE SCHEMA market;
            CREATE TABLE core.ativo(id_ativo int PRIMARY KEY, ticker text);
            CREATE TABLE market.cotacao_diaria(id_ativo int, data_pregao date,
              preco_fechamento numeric, preco_abertura numeric, preco_maximo numeric,
              preco_minimo numeric, is_backtest_simulado boolean DEFAULT false);
            CREATE TABLE market.nominal_bar(ticker text, reference_date date,
              source text, currency text, interval text, close numeric, open numeric, high numeric, low numeric);
            INSERT INTO core.ativo VALUES(1,'EXPENSIVE11B'),(2,'MISMATCH11'),(3,'OTHER11'),(4,'UNKNOWN11');
        ''')
        day = date.today() - timedelta(days=1)
        await conn.executemany('INSERT INTO market.cotacao_diaria VALUES($1,$2,$3,$3,$3,$3,$4)', [
            (1, day, 38133.72, False), (2, day, 100, False), (3, day, 100, False),
            (4, day, 100, False), (1, day + timedelta(days=2), 38133.72, False),
            (1, day-timedelta(days=1), 38133.72, True),
        ])
        await conn.executemany('INSERT INTO market.nominal_bar VALUES($1,$2,$3,$4,$5,$6,$6,$6,$6)', [
            ('EXPENSIVE11B',day,'b3','BRL','day',38133.72), ('MISMATCH11',day,'b3','BRL','day',200),
            ('OTHER11',day,'unverified','BRL','day',100), ('EXPENSIVE11B',day+timedelta(days=2),'b3','BRL','day',38133.72),
            ('EXPENSIVE11B',day-timedelta(days=1),'b3','BRL','day',38133.72),
        ])
        sql = str(verified_market_text('SELECT id_ativo FROM market.cotacao_diaria ORDER BY id_ativo'))
        assert [r[0] for r in await conn.fetch(sql)] == [1]
        await conn.execute("UPDATE market.nominal_bar SET currency='USD' WHERE ticker='EXPENSIVE11B'")
        assert await conn.fetch(sql) == []
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cvm_reference_rejects_ambiguous_identity_instead_of_choosing_a_fund(database):
    from pathlib import Path
    conn = await asyncpg.connect(database)
    try:
        await conn.execute('''CREATE SCHEMA market; CREATE SCHEMA public_staging;
            CREATE TABLE public_staging.stg_cvm_fii_mensal(ticker text, data_referencia date,
              versao int, cnpj_fundo text, razao_social text, patrimonio_liquido numeric,
              valor_patrimonial_cota numeric, cotistas_total numeric);
            INSERT INTO public_staging.stg_cvm_fii_mensal VALUES
              ('GOOD11',CURRENT_DATE-30,1,'1','Good',1000,100,0),
              ('AMBIGUOUS11',CURRENT_DATE-30,1,'2','First',1000,100,5),
              ('AMBIGUOUS11',CURRENT_DATE-30,1,'3','Other fund',10,0.74,5),
              ('FUTURE11',CURRENT_DATE+1,1,'4','Future',1000,100,5);
        ''')
        source = Path(__file__).parent / 'schema_contract/23_asset_serving_integrity/01_verified_fii_reference.sql'
        await conn.execute(source.read_text())
        rows = await conn.fetch('SELECT ticker,valor_patrimonial_cota,cotistas_total FROM market.fii_reference_verified')
        assert len(rows) == 1 and rows[0]['ticker'] == 'GOOD11'
        assert rows[0]['valor_patrimonial_cota'] == 100 and rows[0]['cotistas_total'] == 0
    finally:
        await conn.close()
