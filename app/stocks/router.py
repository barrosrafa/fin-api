from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
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
)
from app.stocks.service import StockService

router = APIRouter(prefix="/stocks", tags=["Stocks"])


def get_stock_service() -> StockService:
    return StockService()


@router.get("/ranking", response_model=List[StockRankingItem])
async def get_stocks_ranking(
    sort_by: str = Query("dy", description="Critério de ordenação: dy, pl, pvp, roe, roic, margem_liquida"),
    limit: int = Query(50, ge=1, le=200),
    service: StockService = Depends(get_stock_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Ranking dinâmico de ações por múltiplos fundamentalistas com ordenação configurável."""
    return await service.get_stocks_ranking(sort_by=sort_by, limit=limit, db_session=db)


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


