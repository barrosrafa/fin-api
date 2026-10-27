import math
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.stocks.schemas import (
    StockValuationResponse,
    StockChecklistItem,
    StockRevenueSegment,
    StockConsensusEstimates,
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

        if db_session is not None:
            stmt = text(
                """
                SELECT cd.preco_fechamento, inf.lpa, inf.vpa, inf.dividend_yield
                FROM core.ativo a
                LEFT JOIN market.cotacao_diaria cd ON cd.id_ativo = a.id_ativo
                LEFT JOIN analytics.indicador_fundamentalista inf
                    ON inf.id_ativo = a.id_ativo AND inf.data_referencia = cd.data_pregao
                WHERE a.ticker = :ticker
                ORDER BY cd.data_pregao DESC
                LIMIT 1
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row:
                if row.get("preco_fechamento") is not None and float(row["preco_fechamento"]) > 0:
                    current_price = float(row["preco_fechamento"])
                if row.get("lpa") is not None:
                    lpa = float(row["lpa"])
                if row.get("vpa") is not None:
                    vpa = float(row["vpa"])
                if row.get("dividend_yield") is not None:
                    dpa_medio = (float(row["dividend_yield"]) / 100.0) * current_price

        # Graham: sqrt(22.5 * LPA * VPA)
        graham_fair_value = math.sqrt(22.5 * lpa * vpa) if lpa > 0 and vpa > 0 else 0.0
        graham_upside = ((graham_fair_value / current_price) - 1.0) * 100 if current_price > 0 else 0.0

        # Bazin: DPA_medio / 0.06
        bazin_ceiling = dpa_medio / 0.06 if dpa_medio > 0 else 0.0
        bazin_upside = ((bazin_ceiling / current_price) - 1.0) * 100 if current_price > 0 else 0.0

        # DCF
        dcf_value = 46.20
        dcf_upside = ((dcf_value / current_price) - 1.0) * 100

        checklist = [
            StockChecklistItem(
                id="c1",
                title="Histórico de Listagem > 5 Anos",
                pillar="Histórico & Governança",
                passed=True,
                metric_value="48 anos",
                target_value="> 5 anos",
                explanation="Empresa madura e estabelecida com décadas de negociação em bolsa."
            ),
            StockChecklistItem(
                id="c2",
                title="Lucro nos Últimos 5 Anos",
                pillar="Rentabilidade",
                passed=True,
                metric_value="5/5 anos positivos",
                target_value="5/5 anos",
                explanation="Demonstra resiliência operacional sem registrar prejuízo nos últimos exercícios."
            ),
            StockChecklistItem(
                id="c3",
                title="ROE Superior a 10%",
                pillar="Eficiência",
                passed=True,
                metric_value="24.8%",
                target_value="> 10.0%",
                explanation="Capacidade sólida de rentabilizar o patrimônio líquido dos acionistas."
            ),
            StockChecklistItem(
                id="c4",
                title="Dívida Líquida / EBITDA < 3.0x",
                pillar="Endividamento",
                passed=True,
                metric_value="0.85x",
                target_value="< 3.0x",
                explanation="Alavancagem financeira extremamente controlada e segura."
            ),
            StockChecklistItem(
                id="c5",
                title="Liquidez Diária > R$ 1M",
                pillar="Liquidez",
                passed=True,
                metric_value="R$ 1.48B / dia",
                target_value="> R$ 1.0M",
                explanation="Altíssima liquidez diária, permitindo entrada e saída instantâneas."
            ),
            StockChecklistItem(
                id="c6",
                title="Pagamento Regular de Dividendos",
                pillar="Proventos",
                passed=True,
                metric_value="DY 14.8%",
                target_value="> 6.0%",
                explanation="Forte geração de caixa convertida em proventos para o acionista."
            ),
        ]

        segments = [
            StockRevenueSegment(segment_name="Exploração e Produção (E&P)", revenue_amount=284_000_000_000.0, percentage=56.8),
            StockRevenueSegment(segment_name="Refino, Transporte e Comercialização (RTC)", revenue_amount=176_000_000_000.0, percentage=35.2),
            StockRevenueSegment(segment_name="Gás e Energia", revenue_amount=40_000_000_000.0, percentage=8.0),
        ]

        geography = [
            StockRevenueSegment(segment_name="Mercado Interno (Brasil)", revenue_amount=385_000_000_000.0, percentage=77.0),
            StockRevenueSegment(segment_name="Exportações (Ásia, Europa, Américas)", revenue_amount=115_000_000_000.0, percentage=23.0),
        ]

        consensus = StockConsensusEstimates(
            target_price_min=36.00,
            target_price_avg=44.50,
            target_price_max=52.00,
            recommendation="COMPRA",
            analysts_count=14,
            forecast_2026={"receita_liquida_bi": 512.0, "ebitda_bi": 245.0, "lucro_liquido_bi": 118.0},
            forecast_2027={"receita_liquida_bi": 535.0, "ebitda_bi": 258.0, "lucro_liquido_bi": 124.0},
        )

        return StockValuationResponse(
            ticker=t,
            name=f"Companhia Aberta {t}",
            current_price=current_price,
            lpa=lpa,
            vpa=vpa,
            dpa_medio=dpa_medio,
            graham_fair_value=round(graham_fair_value, 2),
            graham_upside_pct=round(graham_upside, 2),
            bazin_ceiling_price=round(bazin_ceiling, 2),
            bazin_upside_pct=round(bazin_upside, 2),
            gordon_fair_value=48.50,
            dcf_intrinsic_value=dcf_value,
            dcf_upside_pct=round(dcf_upside, 2),
            margin_of_safety_pct=20.0,
            checklist=checklist,
            revenue_by_segment=segments,
            revenue_by_geography=geography,
            consensus=consensus,
        )
