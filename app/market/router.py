import asyncio
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Response, status, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from app.config import get_settings, Settings
from app.core.database import get_async_session
from app.core.redis import get_redis_client
from app.core.catalog import TickerCatalog
from app.market.service import MarketService
from app.market.schemas import (
    QuoteResponse,
    SyncStatusResponse,
    IndicatorsResponse,
    BenchmarkItem,
    AssetSummaryResponse,
    DividendCalendarItem,
    IbovPEResponse,
    InvestorFlowResponse,
    EarningsCalendarResponse,
    QuoteHistoryResponse,
)

router = APIRouter(prefix="/market", tags=["Market"])


async def get_market_service(
    settings: Annotated[Settings, Depends(get_settings)],
    redis: Annotated[aioredis.Redis, Depends(get_redis_client)],
) -> MarketService:
    catalog = TickerCatalog(redis_client=redis)
    return MarketService(ticker_catalog=catalog, redis_client=redis)


@router.get("/benchmarks", response_model=list[BenchmarkItem])
async def get_market_benchmarks(
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    service = MarketService()
    return await service.get_benchmarks(db_session=db)


@router.get("/assets", response_model=list[AssetSummaryResponse])
async def get_market_assets(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    sector: Optional[str] = None,
    subsector: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = "desc",
):
    service = MarketService()
    items, total = await service.get_assets_with_count(
        asset_type=asset_type,
        limit=limit,
        offset=offset,
        search=search,
        sector=sector,
        subsector=subsector,
        sort_by=sort_by,
        sort_dir=sort_dir,
        db_session=db,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return items


@router.get("/sectors", response_model=list[str])
async def get_market_sectors(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_type: Optional[str] = None,
):
    service = MarketService()
    return await service.get_sectors(asset_type=asset_type, db_session=db)


@router.get("/highlights")
async def get_market_highlights(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_type: str = "FII",
):
    service = MarketService()
    return await service.get_highlights(asset_type=asset_type, db_session=db)


@router.get("/dividends", response_model=list[DividendCalendarItem])
async def get_dividend_calendar(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    ticker: Optional[str] = Query(None, description="Filtro opcional por ticker"),
    status: Optional[str] = Query(None, description="FUTURO, PAGO ou ALL"),
    event_type: Optional[str] = Query(None, description="DIVIDENDO, JCP, RENDIMENTO ou ALL"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    service = MarketService()
    items, total = await service.get_dividend_calendar(
        limit=limit,
        offset=offset,
        ticker=ticker,
        status=status,
        event_type=event_type,
        db_session=db,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return items


@router.get("/dividends/export")
async def export_dividend_calendar(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    ticker: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
):
    """Exporta o calendário e histórico de dividendos para formato CSV oficial."""
    service = MarketService()
    items, _ = await service.get_dividend_calendar(
        limit=5000,
        offset=0,
        ticker=ticker,
        status=status,
        event_type=event_type,
        db_session=db,
    )
    csv_lines = ["Ticker;Tipo;Mes_Referencia;Data_Com;Data_Ex;Data_Pagamento;Valor_Por_Acao;Yield_On_Cost_Pct;Status;Documento_Origem"]
    for it in items:
        csv_lines.append(
            f"{it.assetTicker};{it.type};{it.referenceMonth};{it.dateCom};{it.dateEx or ''};{it.paymentDate};{it.valuePerShare:.4f};{it.yieldOnCostPct:.2f}%;{it.status};{it.sourceUrl or ''}"
        )
    csv_content = "\r\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=agenda_proventos_{ticker or 'b3'}.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@router.get("/ibov-pe-history", response_model=IbovPEResponse)
async def get_ibov_pe_history(
    limit: int = 60,
    db: AsyncSession = Depends(get_async_session),
):
    """Série histórica do P/L Ponderado do Ibovespa com média de 5 anos e bandas de +-1 e +-2 desvios padrão."""
    service = MarketService()
    return await service.get_ibov_pe_history(limit=limit, db_session=db)


@router.get("/investor-flows", response_model=InvestorFlowResponse)
async def get_investor_flows(
    limit: int = 60,
    db: AsyncSession = Depends(get_async_session),
):
    """Participação e fluxo líquido de investidores na B3 (Estrangeiro, Institucional, Pessoa Física, Instituições Financeiras)."""
    service = MarketService()
    return await service.get_investor_flows(limit=limit, db_session=db)


@router.get("/earnings-calendar", response_model=EarningsCalendarResponse)
async def get_earnings_calendar(
    limit: int = 50,
    db: AsyncSession = Depends(get_async_session),
):
    """Agenda de divulgação de resultados trimestrais (DFP/ITR) e webcasts com investidores."""
    service = MarketService()
    return await service.get_earnings_calendar(limit=limit, db_session=db)


@router.get("/news")
async def get_market_news(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    category: Optional[str] = Query(None, description="ALL, FATO_RELEVANTE, COMUNICADO, RESULTADO, PROVENTO"),
    ticker: Optional[str] = Query(None, description="Filtro opcional por ticker"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Retorna documentos oficiais da CVM/B3 (canonical.disclosure_document) e avisos
    de proventos com metadados auditáveis, protocolos reais e links diretos para os originais.
    """
    news_items = []
    
    # 1. Consulta documentos oficiais em canonical.disclosure_document
    doc_conds = ["1=1"]
    doc_params = {"limit": limit, "offset": offset}
    
    if ticker:
        doc_conds.append("a.ticker = :ticker")
        doc_params["ticker"] = ticker.upper()
        
    cat_upper = (category or "ALL").upper()
    if cat_upper == "FATO_RELEVANTE":
        doc_conds.append("(d.document_type ILIKE '%Fato Relevante%' OR d.document_type ILIKE '%FR%')")
    elif cat_upper == "COMUNICADO":
        doc_conds.append("(d.document_type ILIKE '%Comunicado%' OR d.document_type ILIKE '%Aviso%')")
    elif cat_upper == "RESULTADO":
        doc_conds.append("(d.document_type ILIKE '%Demonstra%' OR d.document_type ILIKE '%ITR%' OR d.document_type ILIKE '%DFP%')")

    if cat_upper != "PROVENTO":
        doc_sql = f"""
            SELECT 
                d.document_id::text as id,
                COALESCE(a.ticker, 'MERCADO') as ticker,
                COALESCE(ec.nome_empresarial, a.ticker, 'Companhia B3') as empresa,
                d.document_type,
                d.title,
                d.document_date,
                d.published_at,
                d.source_url,
                d.external_id,
                d.ai_summary,
                d.ai_sentiment
            FROM canonical.disclosure_document d
            LEFT JOIN core.ativo a ON a.canonical_instrument_id = d.instrument_id
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            WHERE {' AND '.join(doc_conds)}
            ORDER BY COALESCE(d.published_at, d.document_date::timestamp with time zone) DESC
            LIMIT :limit OFFSET :offset;
        """
        doc_res = await db.execute(text(doc_sql), doc_params)
        for r in doc_res.mappings().all():
            doc_t = (r["document_type"] or "COMUNICADO").upper()
            if "FATO RELEVANTE" in doc_t:
                tipo_enum = "FATO_RELEVANTE"
            elif "DEMONSTRA" in doc_t or "ITR" in doc_t or "DFP" in doc_t:
                tipo_enum = "RESULTADO"
            else:
                tipo_enum = "COMUNICADO"
                
            sent = (r["ai_sentiment"] or "NEUTRO").upper()
            if "BULLISH" in sent or "POSITIVO" in sent:
                sent_enum = "POSITIVO"
            elif "BEARISH" in sent or "NEGATIVO" in sent:
                sent_enum = "NEGATIVO"
            else:
                sent_enum = "NEUTRO"
                
            dt_str = r["published_at"].strftime("%d/%m/%Y %H:%M") if r["published_at"] else (
                r["document_date"].strftime("%d/%m/%Y") if r["document_date"] else "Recente"
            )

            news_items.append({
                "id": r["id"],
                "ticker": r["ticker"],
                "empresa": r["empresa"],
                "titulo": r["title"],
                "tipo": tipo_enum,
                "sentimento": sent_enum,
                "data_hora": dt_str,
                "resumo": r["ai_summary"] or "Documento protocolado perante a CVM/B3.",
                "cvm_protocolo": r["external_id"],  # Protocolo real se existente, senão None (sem faker)
                "source_url": r["source_url"],
            })

    # 2. Se a categoria for ALL ou PROVENTO, complementa com avisos legítimos de proventos
    if cat_upper in ("ALL", "PROVENTO") and len(news_items) < limit:
        prov_limit = limit - len(news_items)
        prov_conds = ["1=1"]
        prov_params = {"limit": prov_limit}
        if ticker:
            prov_conds.append("a.ticker = :ticker")
            prov_params["ticker"] = ticker.upper()

        stmt_prov = text(f"""
            SELECT 
                p.id_provento as id,
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as empresa,
                p.tipo_provento,
                p.valor_por_acao,
                p.data_com,
                p.data_pagamento
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            WHERE {' AND '.join(prov_conds)}
            ORDER BY p.data_com DESC
            LIMIT :limit;
        """)
        res_prov = await db.execute(stmt_prov, prov_params)
        for r in res_prov.mappings().all():
            tipo_prov = r["tipo_provento"] or "DIVIDENDO"
            val = float(r["valor_por_acao"]) if r["valor_por_acao"] else 0.0
            data_com_str = r["data_com"].strftime("%d/%m/%Y") if r["data_com"] else "A definir"
            data_pag_str = r["data_pagamento"].strftime("%d/%m/%Y") if r["data_pagamento"] else "A definir"

            news_items.append({
                "id": f"prov-{r['id']}",
                "ticker": r["ticker"],
                "empresa": r["empresa"],
                "titulo": f"Aviso de Proventos: {r['ticker']} ({tipo_prov}) — R$ {val:.4f} por cota",
                "tipo": "PROVENTO",
                "sentimento": "NEUTRO",  # Honest: não presume sentimento
                "data_hora": f"Data-Com: {data_com_str}",
                "resumo": f"Distribuição aprovada com data de corte (data-com) em {data_com_str} e liquidação financeira prevista para {data_pag_str}.",
                "cvm_protocolo": None,  # Não inventa protocolo falso
                "source_url": "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/empresas-listadas.htm",
            })

    return {"total": len(news_items), "items": news_items}


@router.get("/{ticker}/history", response_model=QuoteHistoryResponse)
async def get_ticker_quote_history(
    ticker: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    service: Annotated[MarketService, Depends(get_market_service)],
    timeframe: str = Query("1Y", description="1M, 3M, 6M, 1Y, 2Y, 5Y, MAX"),
    adjusted: bool = Query(True, description="Usar cotação ajustada"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Série histórica diária completa de cotações OHLCV com eventos corporativos e ajustes."""
    return await service.get_quote_history(
        ticker=ticker,
        timeframe=timeframe,
        adjusted=adjusted,
        limit=limit,
        offset=offset,
        db_session=db,
    )


@router.get("/{ticker}/history/export")
async def export_ticker_quote_history(
    ticker: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    service: Annotated[MarketService, Depends(get_market_service)],
    timeframe: str = Query("1Y"),
    adjusted: bool = Query(True),
):
    """Exporta o histórico diário de cotações para formato CSV oficial com eventos corporativos."""
    res = await service.get_quote_history(
        ticker=ticker,
        timeframe=timeframe,
        adjusted=adjusted,
        limit=5000,
        offset=0,
        db_session=db,
    )
    csv_lines = [
        "Data;Abertura;Maxima;Minima;Fechamento;Fechamento_Ajustado;Volume;Variacao_Pct;Negocios;Eventos_Corporativos"
    ]
    for q in res.data:
        ev = q.corporate_events or ""
        csv_lines.append(
            f"{q.date};{q.open:.2f};{q.high:.2f};{q.low:.2f};{q.close:.2f};{q.close_adjusted:.2f};{q.volume:.2f};{q.pct_change:.2f}%;{q.num_trades or ''};{ev}"
        )
    csv_content = "\r\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=historico_cotacoes_{ticker.upper()}_{timeframe}.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@router.get("/{ticker}", response_model=QuoteResponse)
async def get_market_quote(
    ticker: str,
    response: Response,
    service: Annotated[MarketService, Depends(get_market_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    asset_class: str = "stock",
):
    result = await service.get_quote(ticker=ticker, asset_class=asset_class, db_session=db)
    if result.status == "syncing":
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/{ticker}/sync-status", response_model=SyncStatusResponse)
async def get_ticker_sync_status(
    ticker: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    service: Annotated[MarketService, Depends(get_market_service)],
):
    return await service.get_sync_status(ticker, db_session=db)


@router.get("/{ticker}/indicators", response_model=IndicatorsResponse)
async def get_market_indicators(
    ticker: str,
    service: Annotated[MarketService, Depends(get_market_service)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    return await service.get_indicators(ticker=ticker, db_session=db)


@router.get("/{ticker}/stream")
async def stream_ticker_sync_progress(
    ticker: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    from app.ingestion.commands import normalize_ticker
    normalized = normalize_ticker(ticker)
    service = MarketService()

    async def event_generator():
        # Compatibility events reflect the durable task rather than an obsolete
        # Redis channel. A closed stream never manufactures completion.
        for _ in range(60):
            current = await service.get_sync_status(normalized, db_session=db)
            await db.rollback()
            yield {"event": "status", "data": current.model_dump_json()}
            if current.status in ("completed", "failed", "idle"):
                return
            await asyncio.sleep(2)
        yield {"event": "timeout", "data": '{"status":"in_progress"}'}

    return EventSourceResponse(event_generator())
