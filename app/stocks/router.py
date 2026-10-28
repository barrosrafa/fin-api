from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.market.schemas import DividendCalendarItem
from app.market.service import MarketService
from app.stocks.schemas import (
    StockValuationResponse,
    StockDetailsResponse,
    StockMultiplesResponse,
    StockFinancialsResponse,
    StockCompleteDetailsResponse,
    FinancialMatrixResponse,
    ConsistencyScreenerItem,
    StockRankingItem,
    DividendMatrixResponse,
    USEquityItem,
    REITItem,
)
from app.stocks.service import StockService

router = APIRouter(prefix="/stocks", tags=["Stocks"])


def get_stock_service() -> StockService:
    return StockService()


@router.get("/us", response_model=List[USEquityItem])
async def get_us_stocks(
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_us_stocks(db_session=db)


@router.get("/reits", response_model=List[REITItem])
async def get_reits(
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_reits(db_session=db)


@router.get("/ranking", response_model=List[StockRankingItem])
async def get_stocks_ranking(
    response: Response,
    sort_by: str = Query("dy", description="Critério de ordenação: dy, pl, pvp, roe, roic, margem_liquida"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    min_dy: Optional[float] = Query(None),
    max_pl: Optional[float] = Query(None),
    max_pvp: Optional[float] = Query(None),
    min_roe: Optional[float] = Query(None),
    min_roic: Optional[float] = Query(None),
    min_margem: Optional[float] = Query(None),
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Ranking dinâmico de ações por múltiplos fundamentalistas com ordenação configurável."""
    items, total = await service.get_stocks_ranking(
        sort_by=sort_by,
        limit=limit,
        offset=offset,
        search=search,
        sector=sector,
        min_dy=min_dy,
        max_pl=max_pl,
        max_pvp=max_pvp,
        min_roe=min_roe,
        min_roic=min_roic,
        min_margem=min_margem,
        db_session=db,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return items


@router.get("/screener/consistency", response_model=List[ConsistencyScreenerItem])
async def get_consistency_screener(
    min_years: int = Query(5, ge=1, le=15, description="Anos consecutivos com lucro positivo (5, 10 ou histórico completo)"),
    min_cagr: Optional[float] = Query(None, description="CAGR mínimo de lucro dos últimos 5 anos"),
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Filtro de Consistência Oceans14: Empresas sem histórico de prejuízo na janela selecionada."""
    return await service.get_consistency_screener(min_years=min_years, min_cagr_lucro=min_cagr, db_session=db)


@router.get("/{ticker}", response_model=StockCompleteDetailsResponse)
async def get_stock_complete_details(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_complete_details(ticker=ticker, db_session=db)


@router.get("/{ticker}/financials/matrix", response_model=FinancialMatrixResponse)
async def get_financial_matrix(
    ticker: str,
    period_type: str = Query("ANUAL", pattern="^(ANUAL|TRIMESTRAL)$"),
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna as Demonstrações Contábeis Históricas de 10 anos (DRE, Balanço Patrimonial e DFC) em matriz estruturada."""
    return await service.get_financial_matrix(ticker=ticker, period_type=period_type, db_session=db)


@router.get("/{ticker}/dividends/matrix", response_model=DividendMatrixResponse)
async def get_dividend_matrix(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna o histórico de proventos agrupados em matriz de 12 meses (Janeiro a Dezembro) por ano com total e yield on cost."""
    return await service.get_dividend_matrix(ticker=ticker, db_session=db)


@router.get("/{ticker}/dividends", response_model=List[DividendCalendarItem])
async def get_stock_dividends(
    ticker: str,
    response: Response,
    status: Optional[str] = Query(None, description="FUTURO, PAGO ou ALL"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna o histórico integral paginado de proventos de um ativo específico."""
    m_svc = MarketService()
    items, total = await m_svc.get_dividend_calendar(
        limit=limit,
        offset=offset,
        ticker=ticker,
        status=status,
        db_session=db,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return items


@router.get("/{ticker}/dividends/export")
async def export_stock_dividends(
    ticker: str,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """Exporta o histórico completo de proventos do ativo para formato CSV oficial."""
    m_svc = MarketService()
    items, _ = await m_svc.get_dividend_calendar(
        limit=5000,
        offset=0,
        ticker=ticker,
        status=status,
        db_session=db,
    )
    csv_lines = [
        "Ticker;Tipo;Mes_Referencia;Data_Com;Data_Ex;Data_Pagamento;Valor_Por_Acao;Yield_On_Cost_Pct;Status;Documento_Origem"
    ]
    for it in items:
        csv_lines.append(
            f"{it.assetTicker};{it.type};{it.referenceMonth};{it.dateCom};{it.dateEx or ''};{it.paymentDate};{it.valuePerShare:.4f};{it.yieldOnCostPct:.2f}%;{it.status};{it.sourceUrl or ''}"
        )
    csv_content = "\r\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=historico_proventos_{ticker.upper()}.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@router.get("/{ticker}/details", response_model=StockDetailsResponse)
async def get_stock_details(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_stock_details(ticker=ticker, db_session=db)


@router.get("/{ticker}/indicators", response_model=StockMultiplesResponse)
async def get_stock_indicators(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_multiples(ticker=ticker, db_session=db)


@router.get("/{ticker}/financials", response_model=StockFinancialsResponse)
async def get_stock_financials(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_financials(ticker=ticker, db_session=db)


@router.get("/{ticker}/valuation", response_model=StockValuationResponse)
async def get_stock_valuation(
    ticker: str,
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_valuation(ticker=ticker, db_session=db)


