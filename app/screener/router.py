from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session

router = APIRouter(prefix="/screener", tags=["Screener"])


class ScreenerQueryRequest(BaseModel):
    asset_class: str = "ALL"  # ACAO, FII, ETF, ALL
    min_dy: Optional[float] = None
    max_pl: Optional[float] = None
    max_pvp: Optional[float] = None
    min_roe: Optional[float] = None
    sector: Optional[str] = None
    limit: int = 100


class ScreenerItemResponse(BaseModel):
    ticker: str
    name: str
    asset_class: str
    sector: str
    price: float
    change_24h: float
    dy_pct: float
    pvp: Optional[float] = None
    pl: Optional[float] = None
    roe_pct: Optional[float] = None
    liquidity_daily: float


class ScreenerQueryResponse(BaseModel):
    total: int
    items: List[ScreenerItemResponse] = Field(default_factory=list)


@router.post("/query", response_model=ScreenerQueryResponse)
async def query_screener(
    request: ScreenerQueryRequest,
    db: AsyncSession = Depends(get_async_session),
):
    type_clause = ""
    params = {"limit": request.limit}
    if request.asset_class and request.asset_class not in ("ALL", "TODOS"):
        type_clause = "AND a.tipo_ativo::text = :tipo_ativo"
        params["tipo_ativo"] = request.asset_class

    stmt = text(
        f"""
        SELECT 
            a.ticker,
            COALESCE(ec.nome_empresarial, a.ticker) as nome,
            a.tipo_ativo::text as tipo,
            COALESCE(ec.setor, CASE a.tipo_ativo::text WHEN 'FII' THEN 'Imobiliário' WHEN 'ETF' THEN 'Índice B3' ELSE 'Geral' END) as setor,
            COALESCE(cd.preco_fechamento, 10.0) as preco,
            COALESCE(cd.variacao_percentual, 0.0) as var24h,
            COALESCE(inf.dividend_yield, df.dividend_yield, 0.0) as dy,
            COALESCE(inf.pvp, df.pvp, 1.0) as pvp,
            COALESCE(inf.pl, 0.0) as pl,
            COALESCE(inf.roe, 0.0) as roe,
            COALESCE(cd.volume_total, a.volume_medio, 100000.0) as liquidez
        FROM core.ativo a
        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
        LEFT JOIN LATERAL (
            SELECT preco_fechamento, variacao_percentual, volume_total 
            FROM market.cotacao_diaria 
            WHERE id_ativo = a.id_ativo 
            ORDER BY data_pregao DESC LIMIT 1
        ) cd ON TRUE
        LEFT JOIN LATERAL (
            SELECT dividend_yield, pvp, pl, roe 
            FROM analytics.indicador_fundamentalista 
            WHERE id_ativo = a.id_ativo 
            ORDER BY data_referencia DESC LIMIT 1
        ) inf ON TRUE
        LEFT JOIN LATERAL (
            SELECT dividend_yield, pvp 
            FROM asset_details.detalhe_fii 
            WHERE id_ativo = a.id_ativo 
            LIMIT 1
        ) df ON TRUE
        WHERE a.tipo_ativo::text IN ('ACAO', 'FII', 'ETF')
        {type_clause}
        ORDER BY cd.volume_total DESC NULLS LAST
        LIMIT :limit;
        """
    )

    res = await db.execute(stmt, params)
    rows = res.mappings().all()

    items: List[ScreenerItemResponse] = []
    for r in rows:
        dy = float(r["dy"])
        pvp = float(r["pvp"]) if r["pvp"] is not None else None
        pl = float(r["pl"]) if r["pl"] is not None else None
        roe = float(r["roe"]) if r["roe"] is not None else None

        if request.min_dy is not None and dy < request.min_dy:
            continue
        if request.max_pvp is not None and pvp is not None and pvp > request.max_pvp:
            continue
        if request.max_pl is not None and pl is not None and pl > request.max_pl:
            continue
        if request.min_roe is not None and roe is not None and roe < request.min_roe:
            continue

        items.append(
            ScreenerItemResponse(
                ticker=r["ticker"],
                name=r["nome"],
                asset_class=r["tipo"],
                sector=r["setor"],
                price=float(r["preco"]),
                change_24h=float(r["var24h"]),
                dy_pct=dy,
                pvp=pvp,
                pl=pl,
                roe_pct=roe,
                liquidity_daily=float(r["liquidez"]),
            )
        )

    return ScreenerQueryResponse(total=len(items), items=items)
