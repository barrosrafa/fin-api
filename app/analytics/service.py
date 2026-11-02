import math
from typing import List, Optional
from app.market.quality import verified_market_text as text
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
            month_filter = "AND mes_calendario = :month"
            params["month"] = month

        stmt = text(
            f"""
            SELECT
                ticker,
                nome,
                tipo,
                mes_calendario,
                tipo_evento,
                probabilidade_pct,
                valor_medio_provento,
                ultimo_ano_pago
            FROM analytics.vw_dividend_map
            WHERE probabilidade_pct >= :min_prob
              {month_filter}
            ORDER BY ticker, mes_calendario, tipo_evento;
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
        """Returns the dividend calendar through the database table-valued function."""
        event_type_param = (event_type or "ALL").upper()
        status_param = status.upper() if status else None
        ticker_param = ticker.strip().upper() if ticker and ticker.strip() else None
        count_res = await db_session.execute(
            text("""
                SELECT analytics.fn_dividend_calendar_count(
                    :event_type, :status, :ticker
                )
            """),
            {"event_type": event_type_param, "status": status_param, "ticker": ticker_param},
        )
        total = count_res.scalar_one_or_none() or 0
        res = await db_session.execute(
            text("""
                SELECT * FROM analytics.fn_dividend_calendar(
                    :limit, :offset, :event_type, :status, :ticker
                )
            """),
            {
                "limit": limit,
                "offset": offset,
                "event_type": event_type_param,
                "status": status_param,
                "ticker": ticker_param,
            },
        )
        items: List[DividendCalendarDetailItem] = []
        for r in res.mappings().all():
            items.append(
                DividendCalendarDetailItem(
                    id_provento=r["id_provento"],
                    ticker=r["ticker"],
                    tipo=r["tipo"],
                    data_com=r["data_com"].isoformat() if r["data_com"] else None,
                    data_ex=r["data_ex"].isoformat() if r["data_ex"] else None,
                    data_pagamento=r["data_pagamento"].isoformat() if r["data_pagamento"] else None,
                    status=r["status"],
                    valor_bruto=round(float(r["valor_bruto"]), 4),
                    aliquota_ir_pct=round(float(r["aliquota_ir"]), 2),
                    valor_liquido=round(float(r["valor_liquido"]), 4),
                    moeda=r["moeda"],
                    cotacao_atual=round(float(r["cotacao"]), 2) if r["cotacao"] is not None else None,
                    yield_evento_pct=round(float(r["yield_evento_pct"]), 2) if r["cotacao"] is not None else None,
                )
            )
        return items, total
