import math
from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.analytics.schemas import (
    DividendSimulationRequest,
    DividendSimulationResponse,
    MagicNumberInfo,
    MonthlyMilestone,
    DividendMapResponse,
    DividendMapEntry,
    MonthlyHeatmapItem,
    DividendCalendarDetailItem,
)


class AnalyticsService:
    def simulate_dividends(self, req: DividendSimulationRequest) -> DividendSimulationResponse:
        """
        Executes discrete monthly compound projection of dividend reinvestment,
        inflation-indexed contributions, dividend growth, and magic number calculation.
        """
        taxa_inflacao_mensal = (1.0 + req.annual_inflation_rate) ** (1.0 / 12.0) - 1.0
        taxa_dgr_mensal = (1.0 + req.annual_dividend_growth_rate) ** (1.0 / 12.0) - 1.0

        preco_cota = req.initial_stock_price
        cotas_totais = req.initial_capital / preco_cota if preco_cota > 0 else 0.0
        total_investido_bolso = req.initial_capital
        total_dividendos_recebidos = 0.0

        magic_number_atingido = False
        mes_magic_number = None
        cotas_magic_number = None

        evolucao: List[MonthlyMilestone] = []

        for mes in range(1, req.time_horizon_months + 1):
            # 1. Ajuste do aporte e do provento unitário
            aporte_mes = req.monthly_contribution * ((1.0 + taxa_inflacao_mensal) ** (mes - 1))
            dividendo_unitario = req.monthly_dividend_per_unit * ((1.0 + taxa_dgr_mensal) ** (mes - 1))

            # 2. Provento do mês
            provento_bruto = cotas_totais * dividendo_unitario
            provento_liquido = provento_bruto * (1.0 - req.tax_rate)
            total_dividendos_recebidos += provento_liquido

            # 3. Magic Number
            if not magic_number_atingido and provento_liquido >= preco_cota:
                magic_number_atingido = True
                mes_magic_number = mes
                cotas_magic_number = cotas_totais

            # 4. Reinvestimento
            capital_para_compras = aporte_mes + (provento_liquido if req.reinvest_dividends else 0.0)
            novas_cotas = capital_para_compras / preco_cota if preco_cota > 0 else 0.0
            cotas_totais += novas_cotas
            total_investido_bolso += aporte_mes

            # 5. Saldo
            patrimonio_mes = cotas_totais * preco_cota
            yoc = (provento_liquido * 12.0 / total_investido_bolso) * 100 if total_investido_bolso > 0 else 0.0

            evolucao.append(
                MonthlyMilestone(
                    mes=mes,
                    cotas=round(cotas_totais, 4),
                    patrimonio=round(patrimonio_mes, 2),
                    aporte_realizado=round(aporte_mes, 2),
                    provento_recebido=round(provento_liquido, 2),
                    total_investido_bolso=round(total_investido_bolso, 2),
                    yield_on_cost_pct=round(yoc, 2),
                )
            )

        # Renda final mensal
        dividendo_final_unitario = req.monthly_dividend_per_unit * ((1.0 + taxa_dgr_mensal) ** req.time_horizon_months)
        renda_final = cotas_totais * dividendo_final_unitario * (1.0 - req.tax_rate)

        # Se não atingiu durante o período, calcula a meta teórica
        cotas_alvo_magic = math.ceil(preco_cota / (req.monthly_dividend_per_unit * (1.0 - req.tax_rate))) if req.monthly_dividend_per_unit > 0 else 0

        return DividendSimulationResponse(
            patrimonio_final=round(cotas_totais * preco_cota, 2),
            total_aportado_bolso=round(total_investido_bolso, 2),
            total_proventos_gerados=round(total_dividendos_recebidos, 2),
            cotas_finais=round(cotas_totais, 4),
            renda_mensal_final=round(renda_final, 2),
            magic_number=MagicNumberInfo(
                atingido=magic_number_atingido,
                mes=mes_magic_number,
                cotas_necessarias=round(cotas_magic_number, 2) if cotas_magic_number else float(cotas_alvo_magic),
            ),
            evolucao=evolucao,
        )

    async def get_dividend_map(
        self,
        db_session: AsyncSession,
        month: Optional[int] = None,
        min_probability: float = 0.0,
    ) -> DividendMapResponse:
        """
        Retrieves pre-aggregated dividend seasonality matrix from analytics.mapa_sazonalidade_dividendo.
        """
        month_filter = ""
        params = {"min_prob": min_probability}
        if month:
            month_filter = "AND s.mes_calendario = :month"
            params["month"] = month

        stmt = text(
            f"""
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                a.tipo_ativo::text as tipo,
                s.mes_calendario,
                s.tipo_evento,
                s.probabilidade_pct,
                s.valor_medio_provento,
                s.ultimo_ano_pago
            FROM analytics.mapa_sazonalidade_dividendo s
            JOIN core.ativo a ON a.id_ativo = s.id_ativo
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            WHERE s.probabilidade_pct >= :min_prob
              {month_filter}
            ORDER BY a.ticker, s.mes_calendario, s.tipo_evento;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        grouped: dict[str, dict] = {}
        for r in rows:
            ticker = r["ticker"]
            if ticker not in grouped:
                grouped[ticker] = {
                    "ticker": ticker,
                    "asset_name": r["nome"],
                    "asset_type": r["tipo"],
                    "months": {},
                }

            m = int(r["mes_calendario"])
            if m not in grouped[ticker]["months"]:
                grouped[ticker]["months"][m] = {
                    "month": m,
                    "record_date_probability_pct": 0.0,
                    "payment_probability_pct": 0.0,
                    "average_payout_per_unit": 0.0,
                    "last_payment_year": None,
                }

            prob = float(r["probabilidade_pct"])
            val = float(r["valor_medio_provento"])
            last_yr = int(r["ultimo_ano_pago"]) if r["ultimo_ano_pago"] else None

            entry = grouped[ticker]["months"][m]
            if r["tipo_evento"] == "DATA_COM":
                entry["record_date_probability_pct"] = prob
            elif r["tipo_evento"] == "PAGAMENTO":
                entry["payment_probability_pct"] = prob

            if val > entry["average_payout_per_unit"]:
                entry["average_payout_per_unit"] = val
            if last_yr and (entry["last_payment_year"] is None or last_yr > entry["last_payment_year"]):
                entry["last_payment_year"] = last_yr

        items = []
        for ticker, data in grouped.items():
            month_items = [
                MonthlyHeatmapItem(**entry)
                for entry in sorted(data["months"].values(), key=lambda x: x["month"])
            ]
            items.append(
                DividendMapEntry(
                    ticker=data["ticker"],
                    asset_name=data["asset_name"],
                    asset_type=data["asset_type"],
                    monthly_heatmap=month_items,
                )
            )

        return DividendMapResponse(total=len(items), items=items)

    async def get_dividend_calendar(
        self,
        db_session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        event_type: str = "ALL",
        status: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> tuple[List[DividendCalendarDetailItem], int]:
        """
        Returns full detailed corporate actions agenda with gross/net, tax rate, status and event yields.
        """
        where_clauses = ["p.data_com IS NOT NULL"]
        params: dict = {"limit": limit, "offset": offset}

        if event_type and event_type.upper() != "ALL":
            where_clauses.append("p.tipo_provento::text = :event_type")
            params["event_type"] = event_type.upper()

        if status and status.upper() == "FUTURO":
            where_clauses.append("p.data_pagamento >= CURRENT_DATE")
        elif status and status.upper() == "PAGO":
            where_clauses.append("p.data_pagamento < CURRENT_DATE")

        if ticker and ticker.strip():
            where_clauses.append("a.ticker = :ticker")
            params["ticker"] = ticker.strip().upper()

        where_sql = " AND ".join(where_clauses)

        count_stmt = text(
            f"""
            SELECT count(*)
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            WHERE {where_sql};
            """
        )
        count_res = await db_session.execute(
            count_stmt, {k: v for k, v in params.items() if k not in ("limit", "offset")}
        )
        total = count_res.scalar_one_or_none() or 0

        stmt = text(
            f"""
            SELECT 
                p.id_provento,
                a.ticker,
                p.tipo_provento::text as tipo,
                to_char(p.data_com, 'YYYY-MM-DD') as dt_com,
                to_char(p.data_ex, 'YYYY-MM-DD') as dt_ex,
                to_char(p.data_pagamento, 'YYYY-MM-DD') as dt_pag,
                CASE WHEN p.data_pagamento >= CURRENT_DATE THEN 'FUTURO' ELSE 'PAGO' END as status_prov,
                COALESCE(p.valor_por_acao, 0.0) as valor_bruto,
                COALESCE(p.aliquota_retencao_fonte, CASE WHEN p.tipo_provento::text = 'JCP' THEN 15.0 ELSE 0.0 END) as aliquota_ir,
                cd.preco_fechamento as cotacao,
                COALESCE(p.moeda, 'BRL') as moeda
            FROM market.provento p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            WHERE {where_sql}
            ORDER BY 
                CASE WHEN p.data_pagamento >= CURRENT_DATE THEN 0 ELSE 1 END,
                p.data_com DESC
            LIMIT :limit OFFSET :offset;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        items: List[DividendCalendarDetailItem] = []
        for r in rows:
            bruto = float(r["valor_bruto"])
            aliquota = float(r["aliquota_ir"])
            liquido = bruto * (1.0 - (aliquota / 100.0))
            cotacao = float(r["cotacao"]) if r["cotacao"] is not None else None
            yield_ev = (liquido / cotacao * 100.0) if cotacao and cotacao > 0 else 0.0

            items.append(
                DividendCalendarDetailItem(
                    id_provento=r["id_provento"],
                    ticker=r["ticker"],
                    tipo=r["tipo"],
                    data_com=r["dt_com"],
                    data_ex=r["dt_ex"],
                    data_pagamento=r["dt_pag"],
                    status=r["status_prov"],
                    valor_bruto=round(bruto, 4),
                    aliquota_ir_pct=round(aliquota, 2),
                    valor_liquido=round(liquido, 4),
                    moeda=r["moeda"],
                    cotacao_atual=round(cotacao, 2) if cotacao is not None else None,
                    yield_evento_pct=round(yield_ev, 2) if cotacao is not None else None,
                )
            )
        return items, total
