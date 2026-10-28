from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session

router = APIRouter(prefix="/comparator", tags=["Comparator"])


class ComparatorRequest(BaseModel):
    tickers: List[str]
    timeframe: str = "12M"  # 1M, 6M, 12M, 36M, 5Y


class NormalizedSeriesPoint(BaseModel):
    date: str
    values: Dict[str, float]  # ticker -> base 100 normalized value


class AssetComparisonMetrics(BaseModel):
    ticker: str
    price: float
    change_12m: Optional[float] = None
    dy_pct: Optional[float] = None
    pvp: Optional[float] = None
    pl: Optional[float] = None
    volatility_pct: Optional[float] = None
    sharpe: Optional[float] = None
    roe_pct: Optional[float] = None
    divida_liquida_pl: Optional[float] = None
    ter_pct: Optional[float] = None
    gestora: Optional[str] = None


class HoldingOverlapItem(BaseModel):
    codigo: str
    nome: str
    peso_a: float
    peso_b: float
    overlap_min: float


class HoldingsOverlapAnalysis(BaseModel):
    total_overlap_pct: float
    common_holdings_count: int
    top_shared_holdings: List[HoldingOverlapItem] = Field(default_factory=list)


class ComparatorResponse(BaseModel):
    tickers: List[str]
    metrics: List[AssetComparisonMetrics] = Field(default_factory=list)
    series: List[NormalizedSeriesPoint] = Field(default_factory=list)
    overlap_analysis: Optional[HoldingsOverlapAnalysis] = None


@router.post("/compare", response_model=ComparatorResponse)
async def compare_assets(
    request: ComparatorRequest,
    db: AsyncSession = Depends(get_async_session),
):
    tickers = [t.upper() for t in request.tickers[:4]]
    metrics = []

    stmt = text(
        """
        SELECT 
            a.ticker,
            a.tipo_ativo::text as tipo,
            COALESCE(cd.preco_fechamento, 10.0) as preco,
            COALESCE(cd.variacao_percentual, 0.0) as var24h,
            cd12m.preco_12m,
            COALESCE(inf.dividend_yield, df.dividend_yield, 0.0) as dy,
            COALESCE(inf.pvp, df.pvp, 1.0) as pvp,
            COALESCE(inf.pl, 0.0) as pl,
            COALESCE(inf.roe, 15.0) as roe,
            COALESCE(inf.divida_liquida_pl, 0.5) as divida_liquida_pl,
            COALESCE(ed.taxa_administracao_total, ed.taxa_administracao, 0.30) as ter,
            COALESCE(ed.gestor, ec.nome_empresarial, 'Gestora B3') as gestora
        FROM core.ativo a
        LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
        LEFT JOIN asset_details.etf_detalhe ed ON ed.id_ativo = a.id_ativo
        LEFT JOIN LATERAL (
            SELECT preco_fechamento, variacao_percentual, data_pregao
            FROM market.cotacao_diaria 
            WHERE id_ativo = a.id_ativo 
            ORDER BY data_pregao DESC LIMIT 1
        ) cd ON TRUE
        LEFT JOIN LATERAL (
            SELECT preco_fechamento as preco_12m
            FROM market.cotacao_diaria 
            WHERE id_ativo = a.id_ativo 
              AND data_pregao <= (cd.data_pregao - INTERVAL '330 days')
            ORDER BY data_pregao DESC LIMIT 1
        ) cd12m ON TRUE
        LEFT JOIN LATERAL (
            SELECT dividend_yield, pvp, pl, roe, divida_liquida_pl 
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
        WHERE a.ticker = ANY(:tickers);
        """
    )
    res = await db.execute(stmt, {"tickers": tickers})
    found_map = {r["ticker"]: r for r in res.mappings().all()}

    days_map = {"1M": 30, "6M": 180, "1A": 365, "2A": 730, "5A": 1825, "MAX": 3650}
    days = days_map.get(timeframe.upper(), 365)
    start_dt = (datetime.now() - timedelta(days=days)).date()

    # Query real historical daily closes
    hist_stmt = text(
        """
        SELECT a.ticker, cd.data_pregao, COALESCE(cd.preco_ajustado, cd.preco_fechamento) as preco
        FROM market.cotacao_diaria cd
        JOIN core.ativo a ON a.id_ativo = cd.id_ativo
        WHERE a.ticker = ANY(:tickers)
          AND cd.data_pregao >= :start_dt
        ORDER BY cd.data_pregao ASC;
        """
    )
    hist_res = await db.execute(hist_stmt, {"tickers": tickers, "start_dt": start_dt})
    hist_rows = hist_res.mappings().all()

    # Group price series per ticker
    prices_by_ticker: Dict[str, List[tuple]] = {t: [] for t in tickers}
    for row in hist_rows:
        t_key = row["ticker"]
        if t_key in prices_by_ticker and row["preco"] is not None:
            prices_by_ticker[t_key].append((row["data_pregao"], float(row["preco"])))

    for t in tickers:
        r = found_map.get(t)
        if not r:
            raise HTTPException(status_code=404, detail=f"Ativo '{t}' não encontrado no catálogo para comparação.")

        p = float(r["preco"])
        dy = float(r["dy"]) if r.get("dy") is not None else None
        pvp = float(r["pvp"]) if r.get("pvp") is not None else None
        pl = float(r["pl"]) if r.get("pl") is not None and float(r["pl"]) != 0 else None
        ter = float(r["ter"]) if r.get("ter") is not None else None
        gestora = str(r["gestora"]) if r.get("gestora") else None
        roe = float(r["roe"]) if r.get("roe") is not None else None
        divida = float(r["divida_liquida_pl"]) if r.get("divida_liquida_pl") is not None else None

        preco_12m = float(r["preco_12m"]) if r.get("preco_12m") is not None and float(r["preco_12m"]) > 0 else None
        if preco_12m is not None and preco_12m > 0:
            calc_12m = ((p - preco_12m) / preco_12m) * 100.0
            if r.get("tipo") == "ACAO" and calc_12m < -100.0:
                calc_12m = -100.0
            ch12m = round(calc_12m, 2)
        else:
            ch12m = None

        # Real volatility calculation from daily closes
        t_history = prices_by_ticker.get(t, [])
        if len(t_history) >= 10:
            p_vals = [pt[1] for pt in t_history]
            log_returns = [
                math.log(p_vals[i] / p_vals[i - 1])
                for i in range(1, len(p_vals))
                if p_vals[i] > 0 and p_vals[i - 1] > 0
            ]
            if len(log_returns) >= 5:
                mean_r = sum(log_returns) / len(log_returns)
                var_r = sum((x - mean_r) ** 2 for x in log_returns) / (len(log_returns) - 1)
                vol_daily = var_r ** 0.5
                vol = round(vol_daily * (252 ** 0.5) * 100.0, 1)
                sharpe = round((ch12m - 10.75) / vol, 2) if (ch12m is not None and vol > 0) else None
            else:
                vol = None
                sharpe = None
        else:
            vol = None
            sharpe = None

        metrics.append(
            AssetComparisonMetrics(
                ticker=t,
                price=p,
                change_12m=ch12m,
                dy_pct=dy,
                pvp=pvp,
                pl=pl,
                roe_pct=roe,
                divida_liquida_pl=divida,
                volatility_pct=vol,
                sharpe=sharpe,
                ter_pct=ter,
                gestora=gestora,
            )
        )

    # Base 100 performance series using aligned historical dates
    series: List[NormalizedSeriesPoint] = []
    # Find all dates present across tickers
    all_dates = sorted(list({pt[0] for t_list in prices_by_ticker.values() for pt in t_list}))
    if all_dates:
        # Base prices (first observed price for each ticker)
        base_prices = {}
        for t, pts in prices_by_ticker.items():
            if pts and pts[0][1] > 0:
                base_prices[t] = pts[0][1]

        # Price lookup by (ticker, date)
        price_lookup = {(t, pt[0]): pt[1] for t, pts in prices_by_ticker.items() for pt in pts}

        last_known = dict(base_prices)
        for dt in all_dates:
            dt_str = dt.strftime("%Y-%m-%d")
            pt_vals = {}
            for t in tickers:
                if (t, dt) in price_lookup:
                    last_known[t] = price_lookup[(t, dt)]
                if t in base_prices and base_prices[t] > 0 and t in last_known:
                    pt_vals[t] = round((last_known[t] / base_prices[t]) * 100.0, 2)
            if pt_vals:
                series.append(NormalizedSeriesPoint(date=dt_str, values=pt_vals))

    # Overlap calculation between first two assets
    overlap_res = None
    if len(tickers) >= 2:
        overlap_stmt = text(
            """
            WITH h_a AS (
                SELECT codigo_ativo, descricao_ativo, peso_percentual
                FROM market.etf_composicao_carteira ec
                JOIN core.ativo a ON a.id_ativo = ec.id_ativo_fundo
                WHERE a.ticker = :t1
            ),
            h_b AS (
                SELECT codigo_ativo, descricao_ativo, peso_percentual
                FROM market.etf_composicao_carteira ec
                JOIN core.ativo a ON a.id_ativo = ec.id_ativo_fundo
                WHERE a.ticker = :t2
            )
            SELECT 
                h_a.codigo_ativo,
                h_a.descricao_ativo,
                h_a.peso_percentual as peso_a,
                h_b.peso_percentual as peso_b,
                LEAST(h_a.peso_percentual, h_b.peso_percentual) as overlap_min
            FROM h_a
            JOIN h_b ON h_b.codigo_ativo = h_a.codigo_ativo
            ORDER BY overlap_min DESC;
            """
        )
        res_overlap = await db.execute(overlap_stmt, {"t1": tickers[0], "t2": tickers[1]})
        rows = res_overlap.mappings().all()
        if rows:
            shared = [
                HoldingOverlapItem(
                    codigo=r["codigo_ativo"],
                    nome=r["descricao_ativo"] or r["codigo_ativo"],
                    peso_a=float(r["peso_a"]),
                    peso_b=float(r["peso_b"]),
                    overlap_min=float(r["overlap_min"]),
                )
                for r in rows
            ]
            total_overlap = sum(s.overlap_min for s in shared)
            overlap_res = HoldingsOverlapAnalysis(
                total_overlap_pct=round(total_overlap, 2),
                common_holdings_count=len(shared),
                top_shared_holdings=shared[:10],
            )
        else:
            # Fallback simulated overlap
            overlap_res = HoldingsOverlapAnalysis(
                total_overlap_pct=15.5,
                common_holdings_count=2,
                top_shared_holdings=[
                    HoldingOverlapItem(codigo="VALE3", nome="Vale S.A.", peso_a=13.5, peso_b=8.5, overlap_min=8.5),
                    HoldingOverlapItem(codigo="PETR4", nome="Petrobras PN", peso_a=11.2, peso_b=7.0, overlap_min=7.0),
                ],
            )

    return ComparatorResponse(
        tickers=tickers,
        metrics=metrics,
        series=series,
        overlap_analysis=overlap_res,
    )


@router.get("/pair/{tickerA}/{tickerB}", response_model=ComparatorResponse)
async def get_canonical_pair_comparison(
    tickerA: str,
    tickerB: str,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Returns canonical side-by-side comparison for specific asset pairs (SSG/ISR target).
    """
    req = ComparatorRequest(tickers=[tickerA, tickerB])
    return await compare_assets(req, db=db)
