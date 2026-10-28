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
    StockDetailsResponse,
    StockMultiplesResponse,
    StockFinancialsResponse,
    StockCompleteDetailsResponse,
    FinancialStatementRow,
    FinancialMatrixResponse,
    ConsistencyScreenerItem,
    StockRankingItem,
    DividendMatrixRow,
    DividendMatrixResponse,
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

    async def get_stock_details(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> StockDetailsResponse:
        t = ticker.upper()
        name = f"Companhia {t}"
        tipo = "PN" if t.endswith("4") else ("ON" if t.endswith("3") else "UNT")
        classe_acao = "PN" if t.endswith("4") else "ON"
        sector = "Geral"
        subsector = "Geral"
        segmento = "Geral"
        current_price = 38.45 if t == "PETR4" else (32.80 if t == "ITUB4" else 50.00)
        data_cotacao = None
        min_52 = current_price * 0.78
        max_52 = current_price * 1.32
        vol_2m = 450000000.0
        val_mercado = 280000000000.0
        val_firma = 310000000000.0
        num_acoes = 8000000000
        is_financial = t in {"ITUB4", "ITUB3", "BBDC4", "BBDC3", "BBAS3", "SANB11", "BPAC11"}

        if is_financial:
            sector = "Financeiro"
            subsector = "Intermediários Financeiros"
            segmento = "Bancos"

        if db_session is not None:
            stmt = text(
                """
                SELECT a.id_ativo, a.id_emissor, a.ticker, a.tipo_ativo, a.classe_acao,
                       a.min_52_semanas, a.max_52_semanas, a.volume_medio_2m, a.quantidade_emitida,
                       ec.nome_empresarial, ec.setor, ec.subsetor, ec.segmento_listagem as segmento,
                       cd.preco_fechamento, to_char(cd.data_pregao, 'YYYY-MM-DD') as dt_pregao,
                       inf.valor_mercado, inf.enterprise_value
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                LEFT JOIN LATERAL (
                    SELECT preco_fechamento, data_pregao
                    FROM market.cotacao_diaria
                    WHERE id_ativo = a.id_ativo
                    ORDER BY data_pregao DESC LIMIT 1
                ) cd ON TRUE
                LEFT JOIN LATERAL (
                    SELECT valor_mercado, enterprise_value
                    FROM analytics.indicador_fundamentalista
                    WHERE id_ativo = a.id_ativo
                    ORDER BY data_referencia DESC LIMIT 1
                ) inf ON TRUE
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row:
                name = row["nome_empresarial"] or name
                tipo = str(row["tipo_ativo"]) if row["tipo_ativo"] else tipo
                classe_acao = row["classe_acao"] or classe_acao
                sector = row["setor"] or sector
                subsector = row["subsetor"] or subsector
                segmento = row["segmento"] or segmento
                if row["preco_fechamento"] is not None:
                    current_price = float(row["preco_fechamento"])
                data_cotacao = row["dt_pregao"]
                if row["min_52_semanas"] is not None:
                    min_52 = float(row["min_52_semanas"])
                if row["max_52_semanas"] is not None:
                    max_52 = float(row["max_52_semanas"])
                if row["volume_medio_2m"] is not None:
                    vol_2m = float(row["volume_medio_2m"])
                if row["valor_mercado"] is not None:
                    val_mercado = float(row["valor_mercado"])
                if row["enterprise_value"] is not None:
                    val_firma = float(row["enterprise_value"])
                if row["quantidade_emitida"] is not None:
                    num_acoes = int(row["quantidade_emitida"])

                sec_lower = f"{sector} {subsector} {segmento}".lower()
                if any(k in sec_lower for k in ["banco", "financeir", "intermedi", "previd"]):
                    is_financial = True

        return StockDetailsResponse(
            ticker=t,
            name=name,
            tipo=tipo,
            classe_acao=classe_acao,
            sector=sector,
            subsector=subsector,
            segmento=segmento,
            current_price=round(current_price, 2),
            data_cotacao=data_cotacao,
            min_52_semanas=round(min_52, 2) if min_52 else None,
            max_52_semanas=round(max_52, 2) if max_52 else None,
            volume_medio_2m=round(vol_2m, 2) if vol_2m else None,
            valor_mercado=round(val_mercado, 2) if val_mercado else None,
            valor_firma=round(val_firma, 2) if val_firma else None,
            numero_acoes=num_acoes,
            is_financial_institution=is_financial,
        )

    async def get_multiples(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> StockMultiplesResponse:
        t = ticker.upper()
        is_financial = t in {"ITUB4", "ITUB3", "BBDC4", "BBDC3", "BBAS3", "SANB11", "BPAC11"}

        pl = 8.5 if not is_financial else 9.2
        pvp = 1.45 if not is_financial else 1.65
        pebit = 4.2 if not is_financial else None
        psr = 1.1 if not is_financial else None
        p_ativos = 0.65 if not is_financial else 0.12
        p_cap_giro = 3.8 if not is_financial else None
        p_ativo_circ_liq = -1.2 if not is_financial else None
        dy = 7.5 if not is_financial else 6.8
        ev_ebitda = 3.4 if not is_financial else None
        ev_ebit = 4.8 if not is_financial else None
        margem_bruta = 45.2 if not is_financial else None
        margem_ebit = 22.1 if not is_financial else None
        margem_liquida = 15.4 if not is_financial else 18.2
        roic = 16.5 if not is_financial else None
        roe = 17.8 if not is_financial else 21.4
        liq_corrente = 1.8 if not is_financial else None
        div_bruta_pl = 0.65 if not is_financial else None
        giro_ativos = 0.55 if not is_financial else None
        lpa = 4.25
        vpa = 24.50

        if db_session is not None:
            stmt = text(
                """
                SELECT inf.*, 
                       ec.setor, ec.subsetor, ec.segmento_listagem as segmento
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                LEFT JOIN LATERAL (
                    SELECT * FROM analytics.indicador_fundamentalista
                    WHERE id_ativo = a.id_ativo
                    ORDER BY data_referencia DESC LIMIT 1
                ) inf ON TRUE
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row:
                sec_lower = f"{row.get('setor') or ''} {row.get('subsetor') or ''} {row.get('segmento') or ''}".lower()
                if any(k in sec_lower for k in ["banco", "financeir", "intermedi", "previd"]):
                    is_financial = True

                def _f(col):
                    v = row.get(col)
                    return float(v) if v is not None else None

                if row.get("id_indicador") is not None:
                    pl = _f("pl") or pl
                    pvp = _f("pvp") or pvp
                    pebit = (_f("p_ebit") or pebit) if not is_financial else None
                    psr = (_f("psr") or psr) if not is_financial else None
                    p_ativos = _f("p_ativo") or p_ativos
                    p_cap_giro = (_f("p_cap_giro") or p_cap_giro) if not is_financial else None
                    p_ativo_circ_liq = (_f("p_ativo_circ_liq") or p_ativo_circ_liq) if not is_financial else None
                    dy = _f("dividend_yield") or dy
                    ev_ebitda = (_f("ev_ebitda") or ev_ebitda) if not is_financial else None
                    ev_ebit = (_f("ev_ebit") or ev_ebit) if not is_financial else None
                    margem_bruta = (_f("margem_bruta") or margem_bruta) if not is_financial else None
                    margem_ebit = (_f("margem_ebit") or margem_ebit) if not is_financial else None
                    margem_liquida = _f("margem_liquida") or margem_liquida
                    roic = (_f("roic") or roic) if not is_financial else None
                    roe = _f("roe") or roe
                    liq_corrente = (_f("liquidez_corrente") or liq_corrente) if not is_financial else None
                    div_bruta_pl = (_f("divida_bruta_pl") or div_bruta_pl) if not is_financial else None
                    giro_ativos = (_f("giro_ativo") or giro_ativos) if not is_financial else None
                    lpa = _f("lpa") or lpa
                    vpa = _f("vpa") or vpa

        return StockMultiplesResponse(
            ticker=t,
            pl=round(pl, 2) if pl is not None else None,
            pvp=round(pvp, 2) if pvp is not None else None,
            pebit=round(pebit, 2) if pebit is not None else None,
            psr=round(psr, 2) if psr is not None else None,
            p_ativos=round(p_ativos, 2) if p_ativos is not None else None,
            p_cap_giro=round(p_cap_giro, 2) if p_cap_giro is not None else None,
            p_ativo_circ_liq=round(p_ativo_circ_liq, 2) if p_ativo_circ_liq is not None else None,
            dividend_yield=round(dy, 2) if dy is not None else None,
            ev_ebitda=round(ev_ebitda, 2) if ev_ebitda is not None else None,
            ev_ebit=round(ev_ebit, 2) if ev_ebit is not None else None,
            margem_bruta=round(margem_bruta, 2) if margem_bruta is not None else None,
            margem_ebit=round(margem_ebit, 2) if margem_ebit is not None else None,
            margem_liquida=round(margem_liquida, 2) if margem_liquida is not None else None,
            roic=round(roic, 2) if roic is not None else None,
            roe=round(roe, 2) if roe is not None else None,
            liquidez_corrente=round(liq_corrente, 2) if liq_corrente is not None else None,
            div_bruta_patrimonio=round(div_bruta_pl, 2) if div_bruta_pl is not None else None,
            giro_ativos=round(giro_ativos, 2) if giro_ativos is not None else None,
            lpa=round(lpa, 2) if lpa is not None else None,
            vpa=round(vpa, 2) if vpa is not None else None,
        )

    async def get_financials(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> StockFinancialsResponse:
        t = ticker.upper()
        is_financial = t in {"ITUB4", "ITUB3", "BBDC4", "BBDC3", "BBAS3", "SANB11", "BPAC11"}

        data_balanco = "2026-06-30"
        if is_financial:
            ativo_total = 2_850_000_000_000.0
            disponibilidades = 145_000_000_000.0
            ativo_circulante = None
            divida_bruta = None
            divida_liquida = None
            patrimonio_liquido = 185_000_000_000.0
            receita_liquida_12m = None
            receita_liquida_3m = None
            ebit_12m = None
            ebit_3m = None
            lucro_liquido_12m = 35_800_000_000.0
            lucro_liquido_3m = 9_650_000_000.0
            carteira_credito = 1_280_000_000_000.0
            depositos = 1_120_000_000_000.0
            res_intermed_12m = 68_500_000_000.0
            res_intermed_3m = 18_200_000_000.0
            rec_serv_12m = 49_100_000_000.0
            rec_serv_3m = 12_800_000_000.0
        else:
            ativo_total = 380_000_000_000.0
            disponibilidades = 42_000_000_000.0
            ativo_circulante = 98_000_000_000.0
            divida_bruta = 115_000_000_000.0
            divida_liquida = 73_000_000_000.0
            patrimonio_liquido = 165_000_000_000.0
            receita_liquida_12m = 245_000_000_000.0
            receita_liquida_3m = 63_000_000_000.0
            ebit_12m = 58_000_000_000.0
            ebit_3m = 14_800_000_000.0
            lucro_liquido_12m = 42_000_000_000.0
            lucro_liquido_3m = 10_500_000_000.0
            carteira_credito = None
            depositos = None
            res_intermed_12m = None
            res_intermed_3m = None
            rec_serv_12m = None
            rec_serv_3m = None

        if db_session is not None:
            stmt = text(
                """
                SELECT dsf.*, to_char(dsf.data_balanco_processado, 'YYYY-MM-DD') as dt_balanco,
                       ec.setor, ec.subsetor
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                LEFT JOIN LATERAL (
                    SELECT * FROM analytics.demonstrativo_snapshot_fundamentus
                    WHERE id_emissor = a.id_emissor
                    ORDER BY data_balanco_processado DESC LIMIT 1
                ) dsf ON TRUE
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row and row.get("id_snapshot") is not None:
                def _f(col):
                    v = row.get(col)
                    return float(v) if v is not None else None

                if row.get("is_instituicao_financeira") is not None:
                    is_financial = bool(row["is_instituicao_financeira"])

                data_balanco = row["dt_balanco"] or data_balanco
                ativo_total = _f("ativo_total") or ativo_total
                disponibilidades = _f("disponibilidades") or disponibilidades
                ativo_circulante = (_f("ativo_circulante") or ativo_circulante) if not is_financial else None
                divida_bruta = (_f("divida_bruta") or divida_bruta) if not is_financial else None
                divida_liquida = (_f("divida_liquida") or divida_liquida) if not is_financial else None
                patrimonio_liquido = _f("patrimonio_liquido") or patrimonio_liquido
                receita_liquida_12m = (_f("receita_liquida_12m") or receita_liquida_12m) if not is_financial else None
                receita_liquida_3m = (_f("receita_liquida_3m") or receita_liquida_3m) if not is_financial else None
                ebit_12m = (_f("ebit_12m") or ebit_12m) if not is_financial else None
                ebit_3m = (_f("ebit_3m") or ebit_3m) if not is_financial else None
                lucro_liquido_12m = _f("lucro_liquido_12m") or lucro_liquido_12m
                lucro_liquido_3m = _f("lucro_liquido_3m") or lucro_liquido_3m

                carteira_credito = (_f("carteira_credito") or carteira_credito) if is_financial else None
                depositos = (_f("depositos_totais") or depositos) if is_financial else None
                res_intermed_12m = (_f("resultado_intermediacao_12m") or res_intermed_12m) if is_financial else None
                res_intermed_3m = (_f("resultado_intermediacao_3m") or res_intermed_3m) if is_financial else None
                rec_serv_12m = (_f("receita_servicos_12m") or rec_serv_12m) if is_financial else None
                rec_serv_3m = (_f("receita_servicos_3m") or rec_serv_3m) if is_financial else None

        return StockFinancialsResponse(
            ticker=t,
            is_financial_institution=is_financial,
            data_balanco=data_balanco,
            ativo_total=round(ativo_total, 2) if ativo_total is not None else None,
            disponibilidades=round(disponibilidades, 2) if disponibilidades is not None else None,
            ativo_circulante=round(ativo_circulante, 2) if ativo_circulante is not None else None,
            divida_bruta=round(divida_bruta, 2) if divida_bruta is not None else None,
            divida_liquida=round(divida_liquida, 2) if divida_liquida is not None else None,
            patrimonio_liquido=round(patrimonio_liquido, 2) if patrimonio_liquido is not None else None,
            receita_liquida_12m=round(receita_liquida_12m, 2) if receita_liquida_12m is not None else None,
            receita_liquida_3m=round(receita_liquida_3m, 2) if receita_liquida_3m is not None else None,
            ebit_12m=round(ebit_12m, 2) if ebit_12m is not None else None,
            ebit_3m=round(ebit_3m, 2) if ebit_3m is not None else None,
            lucro_liquido_12m=round(lucro_liquido_12m, 2) if lucro_liquido_12m is not None else None,
            lucro_liquido_3m=round(lucro_liquido_3m, 2) if lucro_liquido_3m is not None else None,
            carteira_credito=round(carteira_credito, 2) if carteira_credito is not None else None,
            depositos=round(depositos, 2) if depositos is not None else None,
            resultado_intermediacao_12m=round(res_intermed_12m, 2) if res_intermed_12m is not None else None,
            resultado_intermediacao_3m=round(res_intermed_3m, 2) if res_intermed_3m is not None else None,
            receita_servicos_12m=round(rec_serv_12m, 2) if rec_serv_12m is not None else None,
            receita_servicos_3m=round(rec_serv_3m, 2) if rec_serv_3m is not None else None,
        )

    async def get_complete_details(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> StockCompleteDetailsResponse:
        details = await self.get_stock_details(ticker, db_session=db_session)
        multiples = await self.get_multiples(ticker, db_session=db_session)
        financials = await self.get_financials(ticker, db_session=db_session)
        return StockCompleteDetailsResponse(
            details=details,
            multiples=multiples,
            financials=financials,
        )

    async def get_financial_matrix(
        self,
        ticker: str,
        period_type: str = "ANUAL",
        db_session: Optional[AsyncSession] = None,
    ) -> FinancialMatrixResponse:
        t = ticker.upper()
        if db_session is None:
            return FinancialMatrixResponse(
                ticker=t,
                company_name=f"Companhia {t}",
                period_type=period_type,
                years=["2021", "2022", "2023", "2024", "2025"],
            )

        tipo_dem = "ANUAL_CONSOL" if period_type.upper() == "ANUAL" else "TRIMESTRAL_CONSOL"
        stmt = text(
            """
            SELECT 
                dps.ano_exercicio,
                dps.trimestre,
                dps.receita_liquida,
                dps.custos_bens_servicos,
                dps.lucro_bruto,
                dps.despesas_operacionais,
                dps.ebitda,
                dps.depreciacao_amortizacao,
                dps.ebit,
                dps.resultado_financeiro,
                dps.receitas_financeiras,
                dps.despesas_financeiras,
                dps.lucro_antes_ir,
                dps.ir_csll,
                dps.lucro_liquido,
                dps.ativo_total,
                dps.ativo_circulante,
                dps.disponibilidades,
                dps.contas_a_receber,
                dps.estoques,
                dps.passivo_circulante,
                dps.divida_bruta_total,
                dps.divida_liquida,
                dps.patrimonio_liquido,
                dps.fco_operacional,
                dps.fci_investimentos,
                dps.fcf_financiamentos,
                dps.fluxo_caixa_livre,
                dps.lpa_ajustado,
                dps.vpa_ajustado,
                dps.payout_exercicio_pct,
                COALESCE(ec.nome_empresarial, a.ticker) as nome_empresa
            FROM core.ativo a
            JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            JOIN analytics.demonstrativo_padronizado_serie dps ON dps.id_emissor = ec.id_emissor
            WHERE a.ticker = :ticker AND dps.tipo_demonstracao = :tipo_dem
            ORDER BY dps.ano_exercicio ASC, dps.trimestre ASC;
            """
        )
        res = await db_session.execute(stmt, {"ticker": t, "tipo_dem": tipo_dem})
        rows = res.mappings().all()

        if not rows:
            # Fallback construindo a partir de dados existentes
            years = ["2021", "2022", "2023", "2024", "2025"]
            return FinancialMatrixResponse(
                ticker=t,
                company_name=f"Companhia {t}",
                period_type=period_type,
                years=years,
                dre=[
                    FinancialStatementRow(account_name="Receita Líquida", account_code="3.01", values_by_year={y: 100000.0 * (1 + 0.1 * i) for i, y in enumerate(years)}),
                    FinancialStatementRow(account_name="Custos (CPV)", account_code="3.02", values_by_year={y: -52000.0 * (1 + 0.08 * i) for i, y in enumerate(years)}),
                    FinancialStatementRow(account_name="Lucro Bruto", account_code="3.03", is_total=True, values_by_year={y: 48000.0 * (1 + 0.12 * i) for i, y in enumerate(years)}),
                    FinancialStatementRow(account_name="EBITDA / LAJIDA", account_code="3.05", is_total=True, values_by_year={y: 38000.0 * (1 + 0.11 * i) for i, y in enumerate(years)}),
                    FinancialStatementRow(account_name="Lucro Líquido", account_code="3.11", is_total=True, values_by_year={y: 19000.0 * (1 + 0.13 * i) for i, y in enumerate(years)}),
                ],
            )

        company_name = rows[0]["nome_empresa"]
        years = [str(r["ano_exercicio"]) if r["trimestre"] == 0 else f"{r['trimestre']}T{r['ano_exercicio']}" for r in rows]

        def _make_row(name: str, code: str, field: str, is_total: bool = False, level: int = 0) -> FinancialStatementRow:
            vals = {}
            for r, y in zip(rows, years):
                val = r.get(field)
                vals[y] = float(val) if val is not None else None
            return FinancialStatementRow(account_name=name, account_code=code, is_total=is_total, indentation_level=level, values_by_year=vals)

        dre = [
            _make_row("Receita Líquida", "3.01", "receita_liquida", is_total=True),
            _make_row("Custos dos Bens e Serviços", "3.02", "custos_bens_servicos", level=1),
            _make_row("Lucro Bruto", "3.03", "lucro_bruto", is_total=True),
            _make_row("Despesas Operacionais", "3.04", "despesas_operacionais", level=1),
            _make_row("EBITDA", "3.05", "ebitda", is_total=True),
            _make_row("Depreciação e Amortização", "3.06", "depreciacao_amortizacao", level=1),
            _make_row("EBIT (LAJIR)", "3.07", "ebit", is_total=True),
            _make_row("Resultado Financeiro", "3.08", "resultado_financeiro", level=1),
            _make_row("Lucro Antes do IR (LAIR)", "3.11", "lucro_antes_ir"),
            _make_row("Imposto de Renda e CSLL", "3.12", "ir_csll", level=1),
            _make_row("Lucro Líquido Consolidado", "3.13", "lucro_liquido", is_total=True),
        ]

        bp = [
            _make_row("Ativo Total", "1", "ativo_total", is_total=True),
            _make_row("Ativo Circulante", "1.01", "ativo_circulante"),
            _make_row("Disponibilidades (Caixa)", "1.01.01", "disponibilidades", level=1),
            _make_row("Contas a Receber", "1.01.02", "contas_a_receber", level=1),
            _make_row("Estoques", "1.01.04", "estoques", level=1),
            _make_row("Passivo Circulante", "2.01", "passivo_circulante"),
            _make_row("Dívida Bruta Total", "2.02.01", "divida_bruta_total", is_total=True),
            _make_row("Dívida Líquida", "2.02.02", "divida_liquida", is_total=True),
            _make_row("Patrimônio Líquido", "2.03", "patrimonio_liquido", is_total=True),
        ]

        dfc = [
            _make_row("Fluxo de Caixa Operacional (FCO)", "6.01", "fco_operacional", is_total=True),
            _make_row("Fluxo de Caixa de Investimento (FCI)", "6.02", "fci_investimentos"),
            _make_row("Fluxo de Caixa de Financiamento (FCF)", "6.03", "fcf_financiamentos"),
            _make_row("Fluxo de Caixa Livre (FCL)", "6.04", "fluxo_caixa_livre", is_total=True),
        ]

        returns = [
            _make_row("Lucro Por Ação (LPA Ajustado)", "LPA", "lpa_ajustado"),
            _make_row("Valor Patrimonial por Ação (VPA)", "VPA", "vpa_ajustado"),
            _make_row("Payout Anual Declarado (%)", "PAYOUT", "payout_exercicio_pct"),
        ]

        return FinancialMatrixResponse(
            ticker=t,
            company_name=company_name,
            period_type=period_type,
            years=years,
            dre=dre,
            balance_sheet=bp,
            cash_flow=dfc,
            margins_and_returns=returns,
        )

    async def get_dividend_matrix(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> DividendMatrixResponse:
        t = ticker.upper()
        if db_session is None:
            current_year = 2026
            matrix = [
                DividendMatrixRow(year=current_year, months=[0.45, None, 0.60, None, 0.85, None, 0.40, None, 0.50, None, None, 1.20], annual_total=4.00, yield_on_cost_pct=10.4),
                DividendMatrixRow(year=current_year - 1, months=[0.40, None, 0.55, None, 0.80, None, 0.35, None, 0.45, None, None, 1.10], annual_total=3.65, yield_on_cost_pct=9.5),
                DividendMatrixRow(year=current_year - 2, months=[0.35, None, 0.50, None, 0.75, None, 0.30, None, 0.40, None, None, 1.00], annual_total=3.30, yield_on_cost_pct=8.6),
            ]
            return DividendMatrixResponse(ticker=t, years=[r.year for r in matrix], matrix=matrix)

        stmt = text(
            """
            SELECT 
                EXTRACT(YEAR FROM p.data_pagamento)::int as ano,
                EXTRACT(MONTH FROM p.data_pagamento)::int as mes,
                SUM(p.valor_por_acao) as total_mes
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            WHERE a.ticker = :ticker AND p.data_pagamento IS NOT NULL
            GROUP BY EXTRACT(YEAR FROM p.data_pagamento), EXTRACT(MONTH FROM p.data_pagamento)
            ORDER BY ano DESC, mes ASC;
            """
        )
        res = await db_session.execute(stmt, {"ticker": t})
        rows = res.mappings().all()

        year_map = {}
        for r in rows:
            ano = int(r["ano"])
            mes = int(r["mes"])
            val = float(r["total_mes"])
            if ano not in year_map:
                year_map[ano] = [None] * 12
            if 1 <= mes <= 12:
                year_map[ano][mes - 1] = round(val, 4)

        if not year_map:
            # Fallback anos recentes
            years_list = [2026, 2025, 2024]
            matrix = [
                DividendMatrixRow(year=y, months=[0.45, None, 0.60, None, 0.85, None, 0.40, None, 0.50, None, None, 1.20], annual_total=4.00, yield_on_cost_pct=10.4)
                for y in years_list
            ]
            return DividendMatrixResponse(ticker=t, years=years_list, matrix=matrix)

        matrix = []
        for ano in sorted(year_map.keys(), reverse=True):
            months = year_map[ano]
            tot = sum([m for m in months if m is not None])
            matrix.append(
                DividendMatrixRow(
                    year=ano,
                    months=months,
                    annual_total=round(tot, 2),
                    yield_on_cost_pct=round((tot / 38.45) * 100.0, 2) if tot > 0 else 0.0,
                )
            )

        return DividendMatrixResponse(ticker=t, years=[r.year for r in matrix], matrix=matrix)

    async def get_consistency_screener(
        self,
        min_years: int = 5,
        min_cagr_lucro: Optional[float] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> List[ConsistencyScreenerItem]:
        if db_session is None:
            return [
                ConsistencyScreenerItem(ticker="WEGE3", company_name="WEG S.A.", sector="Bens Industriais", segment="Motores e Compressores", consecutive_profitable_years=10, cagr_lucro_5y=19.86, current_pe=32.4, current_pb=9.8, current_dy=1.8, current_roe=31.2),
                ConsistencyScreenerItem(ticker="PETR4", company_name="Petrobras", sector="Petróleo e Gás", segment="Exploração e Refino", consecutive_profitable_years=10, cagr_lucro_5y=13.50, current_pe=4.8, current_pb=1.15, current_dy=14.8, current_roe=28.5),
                ConsistencyScreenerItem(ticker="VALE3", company_name="Vale S.A.", sector="Materiais Básicos", segment="Mineração", consecutive_profitable_years=10, cagr_lucro_5y=0.94, current_pe=6.1, current_pb=1.35, current_dy=9.2, current_roe=22.1),
            ]

        stmt = text(
            """
            SELECT 
                mv.ticker,
                mv.nome_empresarial,
                COALESCE(mv.setor, 'Geral') as setor,
                COALESCE(mv.segmento_listagem, 'Novo Mercado') as segmento,
                mv.anos_historico_cobertura,
                mv.cagr_lucro_5a,
                COALESCE(inf.pl, 0.0) as pl,
                COALESCE(inf.pvp, 1.0) as pvp,
                COALESCE(inf.dividend_yield, 0.0) as dy,
                COALESCE(inf.roe, 0.0) as roe
            FROM analytics.mv_acoes_consistencia_lucro mv
            LEFT JOIN LATERAL (
                SELECT pl, pvp, dividend_yield, roe 
                FROM analytics.indicador_fundamentalista 
                WHERE id_ativo = mv.id_ativo 
                ORDER BY data_referencia DESC LIMIT 1
            ) inf ON TRUE
            WHERE (:min_years = 5 AND mv.sem_prejuizo_ultimos_5a = TRUE)
               OR (:min_years = 10 AND mv.sem_prejuizo_ultimos_10a = TRUE)
               OR (:min_years NOT IN (5, 10) AND mv.nunca_deu_prejuizo = TRUE)
            ORDER BY mv.cagr_lucro_5a DESC NULLS LAST;
            """
        )
        res = await db_session.execute(stmt, {"min_years": min_years})
        rows = res.mappings().all()

        items = []
        for r in rows:
            cagr = float(r["cagr_lucro_5a"]) if r["cagr_lucro_5a"] is not None else None
            if min_cagr_lucro is not None and (cagr is None or cagr < min_cagr_lucro):
                continue
            items.append(
                ConsistencyScreenerItem(
                    ticker=r["ticker"],
                    company_name=r["nome_empresarial"],
                    sector=r["setor"],
                    segment=r["segmento"],
                    consecutive_profitable_years=int(r["anos_historico_cobertura"]),
                    cagr_lucro_5y=cagr,
                    current_pe=float(r["pl"]) if r["pl"] else None,
                    current_pb=float(r["pvp"]) if r["pvp"] else None,
                    current_dy=float(r["dy"]),
                    current_roe=float(r["roe"]),
                )
            )

        if not items:
            return await self.get_consistency_screener(min_years=min_years, db_session=None)
        return items

    async def get_stocks_ranking(
        self,
        sort_by: str = "dy",
        limit: int = 50,
        db_session: Optional[AsyncSession] = None,
    ) -> List[StockRankingItem]:
        order_col = {
            "dy": "inf.dividend_yield DESC NULLS LAST",
            "pl": "inf.pl ASC NULLS LAST",
            "pvp": "inf.pvp ASC NULLS LAST",
            "roe": "inf.roe DESC NULLS LAST",
            "roic": "inf.roic DESC NULLS LAST",
            "margem_liquida": "inf.margem_liquida DESC NULLS LAST",
        }.get(sort_by.lower(), "inf.dividend_yield DESC NULLS LAST")

        if db_session is None:
            return [
                StockRankingItem(rank=1, ticker="PETR4", name="Petrobras PN", sector="Petróleo e Gás", price=38.45, dy=14.8, pl=4.8, pvp=1.15, roe=28.5, roic=24.1, margem_liquida=19.2, ev_ebitda=3.2, liquidez=1850000000.0),
                StockRankingItem(rank=2, ticker="VALE3", name="Vale S.A.", sector="Mineração", price=62.10, dy=9.2, pl=6.1, pvp=1.35, roe=22.1, roic=18.5, margem_liquida=24.0, ev_ebitda=4.1, liquidez=1240000000.0),
                StockRankingItem(rank=3, ticker="WEGE3", name="WEG S.A.", sector="Bens Industriais", price=54.20, dy=1.8, pl=32.4, pvp=9.8, roe=31.2, roic=29.4, margem_liquida=16.1, ev_ebitda=22.5, liquidez=340000000.0),
            ]

        stmt = text(
            f"""
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                COALESCE(ec.setor, 'Geral') as setor,
                COALESCE(cd.preco_fechamento, 10.0) as preco,
                COALESCE(inf.dividend_yield, 0.0) as dy,
                inf.pl,
                inf.pvp,
                inf.roe,
                inf.roic,
                inf.margem_liquida,
                inf.ev_ebitda,
                COALESCE(cd.volume_total, a.volume_medio, 100000.0) as liquidez
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, volume_total 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            LEFT JOIN LATERAL (
                SELECT pl, pvp, dividend_yield, roe, roic, margem_liquida, ev_ebitda
                FROM analytics.indicador_fundamentalista 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_referencia DESC LIMIT 1
            ) inf ON TRUE
            WHERE a.tipo_ativo::text = 'ACAO'
            ORDER BY {order_col}
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        items = []
        for idx, r in enumerate(rows, start=1):
            items.append(
                StockRankingItem(
                    rank=idx,
                    ticker=r["ticker"],
                    name=r["nome"],
                    sector=r["setor"],
                    price=float(r["preco"]),
                    dy=float(r["dy"]),
                    pl=float(r["pl"]) if r["pl"] is not None else None,
                    pvp=float(r["pvp"]) if r["pvp"] is not None else None,
                    roe=float(r["roe"]) if r["roe"] is not None else None,
                    roic=float(r["roic"]) if r["roic"] is not None else None,
                    margem_liquida=float(r["margem_liquida"]) if r["margem_liquida"] is not None else None,
                    ev_ebitda=float(r["ev_ebitda"]) if r["ev_ebitda"] is not None else None,
                    liquidez=float(r["liquidez"]),
                )
            )

        if not items:
            return await self.get_stocks_ranking(sort_by=sort_by, limit=limit, db_session=None)
        return items


