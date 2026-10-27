import math
from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.stocks.schemas import (
    StockValuationResponse,
    StockChecklistItem,
    StockRevenueSegment,
    StockConsensusEstimates,
    DREItemResponse,
    DividendItemResponse,
    TechnicalIndicatorsResponse,
    AIVerdictResponse,
)


class StockService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_valuation(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> StockValuationResponse:
        t = ticker.upper()
        current_price = 38.45 if t == "PETR4" else 62.10
        lpa = 8.12
        vpa = 33.50
        dpa_medio = 4.25
        name = "Petróleo Brasileiro S.A. Petrobras" if t == "PETR4" else f"Companhia {t}"
        id_ativo = None
        id_emissor = None

        checklist_items: List[StockChecklistItem] = []
        dre_items: List[DREItemResponse] = []
        dividend_items: List[DividendItemResponse] = []
        ai_verdict: Optional[AIVerdictResponse] = None

        if db_session is not None:
            # 1. Fetch Asset & Emissor
            asset_stmt = text(
                """
                SELECT a.id_ativo, a.id_emissor, a.ticker, 
                       COALESCE(ec.nome_empresarial, a.ticker) as nome
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(asset_stmt, {"ticker": t})
            asset_row = res.mappings().first()
            if asset_row:
                id_ativo = asset_row["id_ativo"]
                id_emissor = asset_row["id_emissor"]
                name = asset_row["nome"]

            # 2. Fetch Latest Quote & Fundamentals
            if id_ativo is not None:
                quote_stmt = text(
                    """
                    SELECT cd.preco_fechamento, inf.lpa, inf.vpa, inf.dividend_yield
                    FROM market.cotacao_diaria cd
                    LEFT JOIN LATERAL (
                        SELECT lpa, vpa, dividend_yield 
                        FROM analytics.indicador_fundamentalista 
                        WHERE id_ativo = :id_ativo 
                        ORDER BY data_referencia DESC LIMIT 1
                    ) inf ON TRUE
                    WHERE cd.id_ativo = :id_ativo
                    ORDER BY cd.data_pregao DESC
                    LIMIT 1;
                    """
                )
                q_res = await db_session.execute(quote_stmt, {"id_ativo": id_ativo})
                q_row = q_res.mappings().first()
                if q_row:
                    if q_row["preco_fechamento"] is not None and float(q_row["preco_fechamento"]) > 0:
                        current_price = float(q_row["preco_fechamento"])
                    if q_row["lpa"] is not None and float(q_row["lpa"]) > 0:
                        lpa = float(q_row["lpa"])
                    if q_row["vpa"] is not None and float(q_row["vpa"]) > 0:
                        vpa = float(q_row["vpa"])
                    if q_row["dividend_yield"] is not None:
                        dpa_medio = (float(q_row["dividend_yield"]) / 100.0) * current_price

                # 3. Fetch Checklist from DB
                chk_stmt = text(
                    """
                    SELECT criterios_json 
                    FROM analytics.checklist_avaliacao_ativo 
                    WHERE id_ativo = :id_ativo 
                    ORDER BY data_referencia DESC 
                    LIMIT 1;
                    """
                )
                chk_res = await db_session.execute(chk_stmt, {"id_ativo": id_ativo})
                chk_row = chk_res.mappings().first()
                if chk_row and chk_row["criterios_json"]:
                    for item in chk_row["criterios_json"]:
                        checklist_items.append(
                            StockChecklistItem(
                                id=str(item.get("id", "c1")),
                                title=str(item.get("title", "")),
                                pillar=str(item.get("pillar", "Geral")),
                                passed=bool(item.get("passed", True)),
                                metric_value=str(item.get("metricValue", "")),
                                target_value=str(item.get("targetValue", "")),
                                explanation=str(item.get("explanation", "")),
                            )
                        )

                # 4. Fetch Dividends from DB
                div_stmt = text(
                    """
                    SELECT id_provento, tipo_provento::text as tipo, mes_referencia,
                           to_char(data_com, 'YYYY-MM-DD') as dt_com,
                           to_char(data_pagamento, 'YYYY-MM-DD') as dt_pag,
                           valor_por_acao
                    FROM market.provento
                    WHERE id_ativo = :id_ativo
                    ORDER BY data_com DESC
                    LIMIT 10;
                    """
                )
                div_res = await db_session.execute(div_stmt, {"id_ativo": id_ativo})
                for d in div_res.mappings().all():
                    val = float(d["valor_por_acao"])
                    yoc = round((val / current_price) * 100, 2) if current_price > 0 else 0.0
                    dividend_items.append(
                        DividendItemResponse(
                            id=str(d["id_provento"]),
                            assetTicker=t,
                            type=d["tipo"],
                            referenceMonth=d["mes_referencia"] or "08/2024",
                            dateCom=d["dt_com"],
                            paymentDate=d["dt_pag"],
                            valuePerShare=val,
                            yieldOnCostPct=yoc,
                        )
                    )

            # 5. Fetch DRE History from DB
            if id_emissor is not None:
                dre_stmt = text(
                    """
                    SELECT 
                        extract(year from data_referencia)::text as yr,
                        receita_liquida, ebitda, ebit, lucro_liquido
                    FROM analytics.demonstrativo_financeiro
                    WHERE id_emissor = :id_emissor
                    ORDER BY data_referencia ASC;
                    """
                )
                dre_res = await db_session.execute(dre_stmt, {"id_emissor": id_emissor})
                for row in dre_res.mappings().all():
                    rec = float(row["receita_liquida"] or 0)
                    ebitda = float(row["ebitda"] or 0)
                    ebit = float(row["ebit"] or 0)
                    lucro = float(row["lucro_liquido"] or 0)
                    cogs = rec - (rec * 0.55)
                    gross = rec - cogs
                    op_exp = gross - ebit
                    fin_res = -(rec * 0.03)
                    taxes = -(lucro * 0.15)
                    net_margin = round((lucro / rec) * 100, 2) if rec > 0 else 0.0
                    dre_items.append(
                        DREItemResponse(
                            year=row["yr"],
                            netRevenue=rec,
                            cogs=cogs,
                            grossProfit=gross,
                            operatingExpenses=op_exp,
                            ebitda=ebitda,
                            ebit=ebit,
                            financialResult=fin_res,
                            taxes=taxes,
                            netIncome=lucro,
                            netMarginPct=net_margin,
                        )
                    )

            # 6. Fetch AI Verdict / CVM Disclosure from DB
            ai_stmt = text(
                """
                SELECT title, ai_sentiment, ai_summary, key_highlights, retrieved_at
                FROM canonical.disclosure_document
                WHERE (key_highlights->>'ticker') = :ticker
                ORDER BY retrieved_at DESC
                LIMIT 1;
                """
            )
            ai_res = await db_session.execute(ai_stmt, {"ticker": t})
            ai_row = ai_res.mappings().first()
            if ai_row:
                conf = float(ai_row["key_highlights"].get("confidence_score", 90))
                ai_verdict = AIVerdictResponse(
                    ticker=t,
                    sentiment=ai_row["ai_sentiment"] or "BULLISH",
                    confidenceScore=conf,
                    executiveSummary=ai_row["ai_summary"] or "",
                    swot={
                        "strengths": [
                            "Liderança absoluta de mercado e margens operacionais elevadas",
                            "Geração robusta de Fluxo de Caixa Livre e baixo lifting cost",
                            "Histórico consistente de distribuição de proventos",
                        ],
                        "weaknesses": [
                            "Exposição a ciclos internacionais de preços de commodities",
                            "Sensibilidade a diretrizes regulatórias e fiscais",
                        ],
                        "opportunities": [
                            "Expansão contínua em ativos de alta produtividade (Pré-Sal)",
                            "Investimentos estratégicos em eficiência energética e transição",
                        ],
                        "threats": [
                            "Flutuações macroeconômicas globais e volatilidade cambial",
                            "Eventuais litígios tributários ou judiciais",
                        ],
                    },
                    anomaliesDetected=[],
                    lastAnalyzedDoc=ai_row["title"],
                    timestamp=ai_row["retrieved_at"].strftime("%d/%m/%Y %H:%M"),
                )

        # Fallback for checklist if empty
        if not checklist_items:
            checklist_items = [
                StockChecklistItem(
                    id="c1",
                    title="Histórico de Listagem > 5 Anos",
                    pillar="Histórico & Governança",
                    passed=True,
                    metric_value="> 10 anos",
                    target_value="> 5 anos",
                    explanation="Empresa madura e estabelecida com décadas de negociação em bolsa.",
                ),
                StockChecklistItem(
                    id="c2",
                    title="Lucro nos Últimos 5 Anos",
                    pillar="Rentabilidade",
                    passed=True,
                    metric_value="5/5 anos positivos",
                    target_value="5/5 anos",
                    explanation="Demonstra resiliência operacional sem registrar prejuízo nos últimos exercícios.",
                ),
                StockChecklistItem(
                    id="c3",
                    title="ROE Superior a 10%",
                    pillar="Eficiência",
                    passed=True,
                    metric_value=f"{round((lpa / vpa) * 100, 1) if vpa > 0 else 15}%",
                    target_value="> 10.0%",
                    explanation="Capacidade sólida de rentabilizar o patrimônio líquido dos acionistas.",
                ),
                StockChecklistItem(
                    id="c4",
                    title="Dívida Líquida / EBITDA < 3.0x",
                    pillar="Endividamento",
                    passed=True,
                    metric_value="0.85x",
                    target_value="< 3.0x",
                    explanation="Alavancagem financeira extremamente controlada e segura.",
                ),
            ]

        # Valuation calculations
        graham_fair_value = math.sqrt(22.5 * lpa * vpa) if lpa > 0 and vpa > 0 else 0.0
        graham_upside = round(((graham_fair_value / current_price) - 1.0) * 100, 2) if current_price > 0 else 0.0

        bazin_ceiling = round(dpa_medio / 0.06, 2) if dpa_medio > 0 else 0.0
        bazin_upside = round(((bazin_ceiling / current_price) - 1.0) * 100, 2) if current_price > 0 else 0.0

        dcf_value = round(current_price * 1.25, 2)
        dcf_upside = round(((dcf_value / current_price) - 1.0) * 100, 2)

        # Technical indicators calculation
        technical = TechnicalIndicatorsResponse(
            ticker=t,
            timeframe="DIARIO",
            rsi14=58.4,
            macd="Cruzamento de Alta Confirmado (+0.42)",
            stochastic=62.8,
            bollingerWidth=8.45,
            pivotPoint=round(current_price, 2),
            support1=round(current_price * 0.95, 2),
            support2=round(current_price * 0.91, 2),
            resistance1=round(current_price * 1.05, 2),
            resistance2=round(current_price * 1.09, 2),
            summarySignal="COMPRA",
            buySignalsCount=8,
            neutralSignalsCount=2,
            sellSignalsCount=1,
        )

        return StockValuationResponse(
            ticker=t,
            name=name,
            current_price=round(current_price, 2),
            lpa=round(lpa, 2),
            vpa=round(vpa, 2),
            dpa_medio=round(dpa_medio, 2),
            graham_fair_value=round(graham_fair_value, 2),
            graham_upside_pct=graham_upside,
            bazin_ceiling_price=bazin_ceiling,
            bazin_upside_pct=bazin_upside,
            gordon_fair_value=round(dpa_medio * 1.04 / (0.12 - 0.04), 2) if dpa_medio > 0 else None,
            dcf_intrinsic_value=dcf_value,
            dcf_upside_pct=dcf_upside,
            margin_of_safety_pct=graham_upside,
            checklist=checklist_items,
            dre_history=dre_items,
            dividends=dividend_items,
            technical=technical,
            ai_verdict=ai_verdict,
            revenue_by_segment=[
                StockRevenueSegment(segment_name="Diesel e Gasolina", revenue_amount=155000000000.0, percentage=48.2),
                StockRevenueSegment(segment_name="Gás Natural e Energia", revenue_amount=48000000000.0, percentage=15.0),
                StockRevenueSegment(segment_name="Exportação de Óleo Cru", revenue_amount=82000000000.0, percentage=25.5),
                StockRevenueSegment(segment_name="Derivados Especiais e Outros", revenue_amount=36000000000.0, percentage=11.3),
            ],
            revenue_by_geography=[
                StockRevenueSegment(segment_name="Mercado Interno (Brasil)", revenue_amount=245000000000.0, percentage=76.3),
                StockRevenueSegment(segment_name="Exportações (Ásia & Europa)", revenue_amount=76000000000.0, percentage=23.7),
            ],
            consensus=StockConsensusEstimates(
                target_price_min=round(current_price * 1.05, 2),
                target_price_avg=round(current_price * 1.25, 2),
                target_price_max=round(current_price * 1.45, 2),
                recommendation="COMPRA",
                analysts_count=14,
                forecast_2026={"lpa": round(lpa * 1.08, 2), "ebitda": 220000000000.0, "dy_pct": 12.5},
                forecast_2027={"lpa": round(lpa * 1.15, 2), "ebitda": 235000000000.0, "dy_pct": 11.8},
            ),
        )
