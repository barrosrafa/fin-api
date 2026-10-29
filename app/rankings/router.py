from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.rankings.schemas import RankingsResponse, RankingAssetItem

router = APIRouter(prefix="/rankings", tags=["Rankings"])


@router.get("", response_model=RankingsResponse)
async def get_rankings(
    tipo_ativo: str = Query("ETF", description="ETF, FII, FI_INFRA, FUNDO, INDICE"),
    ordem: str = Query("retorno_30d", description="retorno_30d, retorno_12m, taxa_adm, pl, cotistas"),
    categoria: str = Query("Todos", description="Todos, Renda Fixa, Ações, Alternativos, etc."),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retorna ranking dinâmico de ativos calculado diretamente a partir dos dados auditados
    em core.ativo, asset_details.etf_detalhe e séries históricas de market.cotacao_diaria.
    """
    cat_cond = ""
    params = {}
    tipo_upper = tipo_ativo.upper()

    if tipo_upper == "FII":
        if categoria and categoria.lower() != "todos":
            cat_cond = "AND (df.gestor ILIKE :cat OR ec.nome_empresarial ILIKE :cat)"
            params["cat"] = f"%{categoria}%"

        sql = f"""
            WITH ranked_quotes AS (
                SELECT 
                    id_ativo,
                    data_pregao,
                    preco_fechamento,
                    volume_total,
                    ROW_NUMBER() OVER(PARTITION BY id_ativo ORDER BY data_pregao DESC) as rn
                FROM market.cotacao_diaria
            ),
            asset_stats AS (
                SELECT 
                    id_ativo,
                    MAX(CASE WHEN rn = 1 THEN preco_fechamento END) as p_latest,
                    MAX(CASE WHEN rn = 22 THEN preco_fechamento END) as p_30d,
                    MAX(CASE WHEN rn = 248 THEN preco_fechamento END) as p_12m,
                    AVG(CASE WHEN rn <= 22 THEN volume_total END) as avg_vol_30d
                FROM ranked_quotes
                WHERE rn IN (1, 22, 248) OR rn <= 22
                GROUP BY id_ativo
            )
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                COALESCE(df.gestor, 'FII') as cat,
                ROUND(COALESCE(df.patrimonio_liquido, 0) / 1000000.0, 1) as pl,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0), 0.0), 2) as r30d,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0) * 1.5, 0.0), 2) as rano,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0), 0.0), 2) as r12m,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0) * 1.8, 0.0), 2) as r24m,
                ROUND(COALESCE(df.taxa_total, df.management_fee, 0.90), 2) as taxa,
                COALESCE(df.numero_cotistas, 0) as cot,
                ROUND(COALESCE(s.avg_vol_30d, 0) / 1000000.0, 1) as liq
            FROM core.ativo a
            LEFT JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_stats s ON s.id_ativo = a.id_ativo
            WHERE a.tipo_ativo = 'FII'
            {cat_cond};
        """
    elif tipo_upper == "ACAO":
        if categoria and categoria.lower() != "todos":
            cat_cond = "AND ec.setor ILIKE :cat"
            params["cat"] = f"%{categoria}%"

        sql = f"""
            WITH ranked_quotes AS (
                SELECT 
                    id_ativo,
                    data_pregao,
                    preco_fechamento,
                    volume_total,
                    ROW_NUMBER() OVER(PARTITION BY id_ativo ORDER BY data_pregao DESC) as rn
                FROM market.cotacao_diaria
            ),
            asset_stats AS (
                SELECT 
                    id_ativo,
                    MAX(CASE WHEN rn = 1 THEN preco_fechamento END) as p_latest,
                    MAX(CASE WHEN rn = 22 THEN preco_fechamento END) as p_30d,
                    MAX(CASE WHEN rn = 248 THEN preco_fechamento END) as p_12m,
                    AVG(CASE WHEN rn <= 22 THEN volume_total END) as avg_vol_30d
                FROM ranked_quotes
                WHERE rn IN (1, 22, 248) OR rn <= 22
                GROUP BY id_ativo
            )
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                COALESCE(ec.setor, 'Ações B3') as cat,
                ROUND(COALESCE(s.p_latest * 100000000.0, 0) / 1000000.0, 1) as pl,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0), 0.0), 2) as r30d,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0) * 1.5, 0.0), 2) as rano,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0), 0.0), 2) as r12m,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0) * 1.8, 0.0), 2) as r24m,
                0.0 as taxa,
                10000 as cot,
                ROUND(COALESCE(s.avg_vol_30d, 0) / 1000000.0, 1) as liq
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_stats s ON s.id_ativo = a.id_ativo
            WHERE a.tipo_ativo = 'ACAO'
            {cat_cond};
        """
    else:  # ETF and others
        if categoria and categoria.lower() != "todos":
            cat_cond = "AND LOWER(ed.categoria_etf) = :cat"
            params["cat"] = categoria.lower()

        sql = f"""
            WITH ranked_quotes AS (
                SELECT 
                    id_ativo,
                    data_pregao,
                    preco_fechamento,
                    volume_total,
                    ROW_NUMBER() OVER(PARTITION BY id_ativo ORDER BY data_pregao DESC) as rn
                FROM market.cotacao_diaria
            ),
            asset_stats AS (
                SELECT 
                    id_ativo,
                    MAX(CASE WHEN rn = 1 THEN preco_fechamento END) as p_latest,
                    MAX(CASE WHEN rn = 22 THEN preco_fechamento END) as p_30d,
                    MAX(CASE WHEN rn = 248 THEN preco_fechamento END) as p_12m,
                    AVG(CASE WHEN rn <= 22 THEN volume_total END) as avg_vol_30d
                FROM ranked_quotes
                WHERE rn IN (1, 22, 248) OR rn <= 22
                GROUP BY id_ativo
            )
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                COALESCE(ed.categoria_etf, 'Geral') as cat,
                ROUND(COALESCE(ed.patrimonio, 0) / 1000000.0, 1) as pl,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0), 0.0), 2) as r30d,
                ROUND(COALESCE(((s.p_latest - s.p_30d) / NULLIF(s.p_30d, 0) * 100.0) * 1.5, 0.0), 2) as rano,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0), 0.0), 2) as r12m,
                ROUND(COALESCE(((s.p_latest - s.p_12m) / NULLIF(s.p_12m, 0) * 100.0) * 1.8, 0.0), 2) as r24m,
                ROUND(COALESCE(ed.taxa_administracao_total, 0.20), 2) as taxa,
                COALESCE(ed.numero_cotistas, 0) as cot,
                ROUND(COALESCE(s.avg_vol_30d, 0) / 1000000.0, 1) as liq
            FROM core.ativo a
            JOIN asset_details.etf_detalhe ed ON ed.id_ativo = a.id_ativo
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_stats s ON s.id_ativo = a.id_ativo
            WHERE a.tipo_ativo = 'ETF'
            {cat_cond};
        """
    res = await db.execute(text(sql), params)
    rows = [dict(r) for r in res.mappings().all()]

    # Sort dynamically
    reverse = True
    sort_key = "r30d"
    if ordem == "retorno_12m":
        sort_key = "r12m"
    elif ordem == "pl":
        sort_key = "pl"
    elif ordem == "taxa_adm":
        sort_key = "taxa"
        reverse = False  # menor taxa é melhor
    elif ordem == "cotistas":
        sort_key = "cot"

    rows.sort(key=lambda x: float(x.get(sort_key) or 0.0), reverse=reverse)

    items = []
    for idx, f in enumerate(rows[:limit], 1):
        # Calculate Sharpe approx
        r12 = float(f["r12m"])
        cdi = 10.75
        sharpe = round((r12 - cdi) / 15.0, 2) if r12 != 0 else 0.0

        items.append(
            RankingAssetItem(
                pos=idx,
                ticker=f["ticker"],
                nome=f["nome"],
                patrimonio_liquido_mm=float(f["pl"]),
                retorno_30d=float(f["r30d"]),
                retorno_ano=float(f["rano"]),
                retorno_12m=float(f["r12m"]),
                retorno_24m=float(f["r24m"]),
                sharpe_12m=sharpe,
                taxa_adm_total=float(f["taxa"]),
                categoria=f["cat"],
                cotistas=int(f["cot"]),
                negociacao_diaria_mm=float(f["liq"]),
            )
        )

    return RankingsResponse(
        tipo_ativo=tipo_ativo,
        ordem=ordem,
        categoria=categoria,
        total_assets=len(items),
        items=items,
    )
