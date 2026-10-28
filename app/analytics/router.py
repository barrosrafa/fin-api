from typing import List, Optional
from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.analytics.schemas import (
    DividendSimulationRequest,
    DividendSimulationResponse,
    DividendMapResponse,
    DividendCalendarDetailItem,
)
from app.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


@router.post("/simulate-dividends", response_model=DividendSimulationResponse)
async def simulate_dividends(
    request: DividendSimulationRequest,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return service.simulate_dividends(request)


@router.get("/dividend-map", response_model=DividendMapResponse)
async def get_dividend_map(
    month: Optional[int] = None,
    min_probability: float = 0.0,
    service: AnalyticsService = Depends(get_analytics_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_dividend_map(db_session=db, month=month, min_probability=min_probability)


@router.get("/dividend-calendar", response_model=List[DividendCalendarDetailItem])
async def get_dividend_calendar(
    response: Response,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    event_type: str = Query("ALL"),
    status: Optional[str] = Query(None, description="FUTURO, PAGO ou ALL"),
    ticker: Optional[str] = Query(None, description="Ticker opcional"),
    service: AnalyticsService = Depends(get_analytics_service),
    db: AsyncSession = Depends(get_async_session),
):
    items, total = await service.get_dividend_calendar(
        db_session=db,
        limit=limit,
        offset=offset,
        event_type=event_type,
        status=status,
        ticker=ticker,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return items


@router.get("/dividend-calendar/export")
async def export_dividend_calendar(
    event_type: str = Query("ALL"),
    status: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    service: AnalyticsService = Depends(get_analytics_service),
    db: AsyncSession = Depends(get_async_session),
):
    """Exporta o calendário detalhado de dividendos em formato CSV oficial."""
    items, _ = await service.get_dividend_calendar(
        db_session=db,
        limit=5000,
        offset=0,
        event_type=event_type,
        status=status,
        ticker=ticker,
    )
    csv_lines = [
        "Ticker;Tipo;Data_Com;Data_Ex;Data_Pagamento;Status;Valor_Bruto;Aliquota_IR_Pct;Valor_Liquido;Yield_Evento_Pct"
    ]
    for it in items:
        yield_str = f"{it.yield_evento_pct:.2f}%" if it.yield_evento_pct is not None else ""
        csv_lines.append(
            f"{it.ticker};{it.tipo};{it.data_com or ''};{it.data_ex or ''};{it.data_pagamento or ''};{it.status};{it.valor_bruto:.4f};{it.aliquota_ir_pct:.2f}%;{it.valor_liquido:.4f};{yield_str}"
        )
    csv_content = "\r\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=agenda_dividendos_detalhada_{ticker or 'b3'}.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )
