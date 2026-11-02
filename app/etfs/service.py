from datetime import datetime
from typing import Optional
from fastapi import HTTPException
from app.market.quality import verified_market_text as text
from app.market.lifecycle import trading_status
from sqlalchemy.ext.asyncio import AsyncSession
from app.etfs.schemas import (
    ETFDetailResponse,
    ETFUnderlyingAsset,
    ETFDrawdownResponse,
)


class ETFService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_etf_drawdown(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> ETFDrawdownResponse:
        t = ticker.upper()
        if db_session is None:
            raise HTTPException(status_code=503, detail="ETF quote history unavailable")

        stmt = text("""
            SELECT cd.data_pregao, cd.preco_fechamento
            FROM market.cotacao_diaria cd
            JOIN core.ativo a ON a.id_ativo = cd.id_ativo
            WHERE a.ticker = :ticker
            ORDER BY cd.data_pregao ASC;
        """)
        res = await db_session.execute(stmt, {"ticker": t})
        rows = res.mappings().all()

        if not rows:
            return ETFDrawdownResponse(
                ticker=t,
                max_drawdown_pct=None,
                valley_date=None,
                recovery_days=None,
                drawdown_curve=[],
            )

        peak = 0.0
        max_dd = 0.0
        valley_date = None
        valley_idx = -1
        curve = []

        for idx, r in enumerate(rows):
            p = float(r["preco_fechamento"])
            if p > peak:
                peak = p
            dd = ((p - peak) / peak) * 100.0 if peak > 0 else 0.0
            dt = r["data_pregao"]
            ts = int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)
            curve.append([ts, round(dd, 2)])
            if dd < max_dd:
                max_dd = dd
                valley_date = str(dt)
                valley_idx = idx

        recovery_days = None
        if valley_idx >= 0:
            valley_peak = 0.0
            for i in range(valley_idx + 1):
                valley_peak = max(valley_peak, float(rows[i]["preco_fechamento"]))
            for j in range(valley_idx + 1, len(rows)):
                if float(rows[j]["preco_fechamento"]) >= valley_peak:
                    dt_valley = rows[valley_idx]["data_pregao"]
                    dt_rec = rows[j]["data_pregao"]
                    recovery_days = (dt_rec - dt_valley).days
                    break

        return ETFDrawdownResponse(
            ticker=t,
            max_drawdown_pct=round(max_dd, 2),
            valley_date=valley_date,
            recovery_days=recovery_days,
            drawdown_curve=curve,
        )

    async def get_etf_detail(self, ticker: str, db_session: Optional[AsyncSession] = None) -> ETFDetailResponse:
        if db_session is None:
            raise HTTPException(status_code=503, detail="ETF data unavailable")
        t = ticker.upper()
        result = await db_session.execute(text("""
            SELECT a.id_ativo, a.canonical_instrument_id,
                   COALESCE(ec.nome_empresarial, a.ticker) AS nome,
                   ci.status AS registry_status,
                   ed.indice_referencia, ed.gestor, ed.taxa_administracao_total,
                   ed.taxa_administracao_primaria, ed.taxa_administracao_secundaria,
                   ed.politica_dividendos, ed.limite_aluguel_pl_pct, ed.patrimonio, ed.cotas,
                   cd.preco_fechamento, cd.data_pregao::text AS quote_date
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor=a.id_emissor
            LEFT JOIN canonical.instrument ci ON ci.instrument_id=a.canonical_instrument_id
            LEFT JOIN asset_details.etf_detalhe ed ON ed.id_ativo=a.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, data_pregao FROM market.cotacao_diaria
                WHERE id_ativo=a.id_ativo ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            WHERE a.ticker=:ticker AND a.tipo_ativo::text='ETF' LIMIT 1
        """), {"ticker": t})
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"ETF ticker '{t}' not found")
        price = float(row["preco_fechamento"]) if row.get("preco_fechamento") is not None else None
        shares = row.get("cotas")
        nav = float(row["patrimonio"]) / float(shares) if row.get("patrimonio") is not None and shares is not None and float(shares) > 0 else None
        spread = (price / nav - 1) * 100 if price is not None and nav is not None and nav > 0 else None
        holding_result = await db_session.execute(text("""
            SELECT codigo_ativo, descricao_ativo, setor_economico, peso_percentual
            FROM market.etf_composicao_carteira
            WHERE id_ativo_fundo=:asset AND data_referencia=(
                SELECT MAX(data_referencia) FROM market.etf_composicao_carteira WHERE id_ativo_fundo=:asset
            ) ORDER BY peso_percentual DESC
        """), {"asset": row["id_ativo"]})
        holdings = [ETFUnderlyingAsset(
            ticker=h["codigo_ativo"], name=h["descricao_ativo"] or h["codigo_ativo"],
            weight_pct=float(h["peso_percentual"]), sector=h["setor_economico"] or "Diversificado",
        ) for h in holding_result.mappings().all()]
        drawdown = await self.get_etf_drawdown(t, db_session)
        return ETFDetailResponse(
            ticker=t, name=row["nome"], benchmark_index=row.get("indice_referencia"),
            provider=row.get("gestor"), current_price=price, source="B3 / COTAHIST" if price is not None else None,
            quote_date=row.get("quote_date"), trading=trading_status(t, row.get("registry_status")),
            nav_per_share=nav, nav_spread_pct=spread,
            ter_pct=float(row["taxa_administracao_total"]) if row.get("taxa_administracao_total") is not None else None,
            primary_fee_pct=float(row["taxa_administracao_primaria"]) if row.get("taxa_administracao_primaria") is not None else None,
            secondary_fee_pct=float(row["taxa_administracao_secundaria"]) if row.get("taxa_administracao_secundaria") is not None else None,
            policy=row.get("politica_dividendos"), shares_lending_pct=None,
            max_lending_limit_pct=float(row["limite_aluguel_pl_pct"]) if row.get("limite_aluguel_pl_pct") is not None else None,
            underlying_holdings=holdings, flow_history_30d=[], drawdown=drawdown,
        )
