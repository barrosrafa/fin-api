from typing import List, Optional
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
    Returns ranked Top 20 list of assets according to ETFs Brasil specifications.
    """
    # Sample ranked items matching ETFs Brasil top universe
    base_etfs = [
        {"ticker": "BOVA11", "nome": "iShares Ibovespa", "cat": "Ações", "pl": 18947.8, "r30d": 3.5, "rano": 9.1, "r12m": 20.57, "r24m": 34.0, "sharpe": 0.26, "taxa": 0.10, "cot": 104623, "liq": 1376.4},
        {"ticker": "IVVB11", "nome": "iShares S&P 500", "cat": "Ações Internacionais", "pl": 6540.2, "r30d": 4.1, "rano": 24.5, "r12m": 38.2, "r24m": 58.4, "sharpe": 1.45, "taxa": 0.23, "cot": 195430, "liq": 820.5},
        {"ticker": "SMAL11", "nome": "iShares Small Cap", "cat": "Ações", "pl": 5210.0, "r30d": -0.8, "rano": -4.2, "r12m": 8.4, "r24m": 14.2, "sharpe": -0.15, "taxa": 0.50, "cot": 82400, "liq": 210.3},
        {"ticker": "BLFT11", "nome": "Bradesco B-Index Teva LFT CP", "cat": "Renda Fixa", "pl": 1420.5, "r30d": 1.15, "rano": 9.8, "r12m": 12.1, "r24m": 25.8, "sharpe": 1.80, "taxa": 0.10, "cot": 14200, "liq": 45.0},
        {"ticker": "LFTS11", "nome": "Investo Teva Tesouro Selic", "cat": "Renda Fixa", "pl": 2840.1, "r30d": 1.14, "rano": 9.7, "r12m": 12.0, "r24m": 25.6, "sharpe": 1.75, "taxa": 0.19, "cot": 31500, "liq": 95.2},
        {"ticker": "CDIB11", "nome": "IT NOW Teva ITBR Selic 800", "cat": "Renda Fixa", "pl": 408.7, "r30d": 1.15, "rano": 9.9, "r12m": 12.3, "r24m": 26.1, "sharpe": 1.85, "taxa": 0.15, "cot": 5268, "liq": 9.2},
        {"ticker": "DEBB11", "nome": "ETF Teva Debêntures DI", "cat": "Renda Fixa", "pl": 850.3, "r30d": 1.25, "rano": 10.8, "r12m": 13.5, "r24m": 28.4, "sharpe": 1.95, "taxa": 0.30, "cot": 12500, "liq": 18.4},
        {"ticker": "HASH11", "nome": "Hashdex Nasdaq Crypto Index", "cat": "Alternativos", "pl": 3120.4, "r30d": 8.4, "rano": 65.2, "r12m": 112.4, "r24m": 180.5, "sharpe": 1.20, "taxa": 0.60, "cot": 145000, "liq": 120.0},
        {"ticker": "CMDB11", "nome": "Teva Ações Commodities", "cat": "Ações", "pl": 280.0, "r30d": 4.46, "rano": 23.0, "r12m": 37.78, "r24m": 42.0, "sharpe": 0.95, "taxa": 0.50, "cot": 3400, "liq": 5.8},
        {"ticker": "B5P211", "nome": "IT NOW IMA-B 5 P2", "cat": "Renda Fixa", "pl": 4250.0, "r30d": 1.45, "rano": 11.2, "r12m": 14.1, "r24m": 29.5, "sharpe": 1.60, "taxa": 0.20, "cot": 45100, "liq": 88.0},
    ]

    # Filter by category if not Todos
    if categoria != "Todos":
        filtered = [x for x in base_etfs if x["cat"].lower() == categoria.lower()]
    else:
        filtered = list(base_etfs)

    # Sort based on order
    reverse = True
    sort_key = "r30d"
    if ordem == "retorno_12m":
        sort_key = "r12m"
    elif ordem == "pl":
        sort_key = "pl"
    elif ordem == "taxa_adm":
        sort_key = "taxa"
        reverse = False  # lowest is best
    elif ordem == "cotistas":
        sort_key = "cot"

    filtered.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

    items = []
    for idx, f in enumerate(filtered[:limit], 1):
        items.append(
            RankingAssetItem(
                pos=idx,
                ticker=f["ticker"],
                nome=f["nome"],
                patrimonio_liquido_mm=f["pl"],
                retorno_30d=f["r30d"],
                retorno_ano=f["rano"],
                retorno_12m=f["r12m"],
                retorno_24m=f["r24m"],
                sharpe_12m=f["sharpe"],
                taxa_adm_total=f["taxa"],
                categoria=f["cat"],
                cotistas=f["cot"],
                negociacao_diaria_mm=f["liq"],
            )
        )

    return RankingsResponse(
        tipo_ativo=tipo_ativo,
        ordem=ordem,
        categoria=categoria,
        total_assets=len(items),
        items=items,
    )
