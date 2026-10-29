from datetime import datetime
from typing import Optional
from sqlalchemy import text
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
            return ETFDrawdownResponse(
                ticker=t,
                max_drawdown_pct=0.0,
                valley_date=None,
                recovery_days=None,
                drawdown_curve=[],
            )

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
                max_drawdown_pct=0.0,
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

    async def get_etf_detail(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> ETFDetailResponse:
        t = ticker.upper()
        current_price = 128.40 if t == "BOVA11" else 285.50
        nav_per_share = 128.25 if t == "BOVA11" else 285.10
        provider = "BlackRock Brasil"
        benchmark_index = "IBOVESPA" if t == "BOVA11" else "S&P 500 BRL"
        name = f"iShares {t} Fundo de Índice"
        ter_pct = 0.30
        primary_fee_pct = 0.30
        secondary_fee_pct = 0.00
        policy = "ACUMULATIVO"
        max_lending_limit_pct = 30.0

        db_holdings = []
        if db_session is not None:
            stmt = text(
                """
                SELECT 
                    a.id_ativo,
                    COALESCE(ec.nome_empresarial, a.ticker) as nome,
                    COALESCE(cd.preco_fechamento, 128.0) as preco,
                    ed.indice_referencia,
                    ed.gestor,
                    ed.taxa_administracao_total,
                    ed.taxa_administracao_primaria,
                    ed.taxa_administracao_secundaria,
                    ed.politica_dividendos,
                    ed.limite_aluguel_pl_pct,
                    ed.patrimonio,
                    ed.cotas
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                LEFT JOIN asset_details.etf_detalhe ed ON ed.id_ativo = a.id_ativo
                LEFT JOIN LATERAL (
                    SELECT preco_fechamento 
                    FROM market.cotacao_diaria 
                    WHERE id_ativo = a.id_ativo 
                    ORDER BY data_pregao DESC LIMIT 1
                ) cd ON TRUE
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row:
                if row["nome"]:
                    name = row["nome"]
                current_price = float(row["preco"])
                if row["patrimonio"] and row["cotas"] and float(row["cotas"]) > 0:
                    nav_per_share = round(float(row["patrimonio"]) / float(row["cotas"]), 2)
                else:
                    nav_per_share = None

                if row["indice_referencia"]:
                    benchmark_index = row["indice_referencia"]
                if row["gestor"]:
                    provider = row["gestor"]
                if row["taxa_administracao_total"] is not None:
                    ter_pct = float(row["taxa_administracao_total"])
                if row["taxa_administracao_primaria"] is not None:
                    primary_fee_pct = float(row["taxa_administracao_primaria"])
                else:
                    primary_fee_pct = ter_pct
                if row["taxa_administracao_secundaria"] is not None:
                    secondary_fee_pct = float(row["taxa_administracao_secundaria"])
                else:
                    secondary_fee_pct = max(0.0, round(ter_pct - primary_fee_pct, 4))
                if row["politica_dividendos"]:
                    policy = row["politica_dividendos"]
                if row["limite_aluguel_pl_pct"] is not None:
                    max_lending_limit_pct = float(row["limite_aluguel_pl_pct"])

                # Query open holdings filtered strictly by latest reference date snapshot
                h_stmt = text(
                    """
                    SELECT codigo_ativo, descricao_ativo, setor_economico, peso_percentual
                    FROM market.etf_composicao_carteira
                    WHERE id_ativo_fundo = :id_ativo
                      AND data_referencia = (
                          SELECT MAX(data_referencia)
                          FROM market.etf_composicao_carteira
                          WHERE id_ativo_fundo = :id_ativo
                      )
                    ORDER BY peso_percentual DESC;
                    """
                )
                h_res = await db_session.execute(h_stmt, {"id_ativo": row["id_ativo"]})
                h_rows = h_res.mappings().all()
                if h_rows:
                    for hr in h_rows:
                        db_holdings.append(
                            ETFUnderlyingAsset(
                                ticker=hr["codigo_ativo"],
                                name=hr["descricao_ativo"] or hr["codigo_ativo"],
                                weight_pct=float(hr["peso_percentual"]),
                                sector=hr["setor_economico"] or "Diversificado",
                            )
                        )

        if nav_per_share is not None and nav_per_share > 0:
            spread_pct = round(((current_price - nav_per_share) / nav_per_share) * 100, 3)
        else:
            spread_pct = None

        if db_holdings:
            holdings = db_holdings
        elif db_session is None and t == "IVVB11":
            holdings = [
                ETFUnderlyingAsset(ticker="MSFT", name="Microsoft Corporation", weight_pct=6.8, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="AAPL", name="Apple Inc.", weight_pct=6.5, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="NVDA", name="NVIDIA Corporation", weight_pct=6.2, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="AMZN", name="Amazon.com Inc.", weight_pct=3.6, sector="Consumo Discricionário"),
                ETFUnderlyingAsset(ticker="GOOGL", name="Alphabet Inc. Class A", weight_pct=2.3, sector="Serviços de Comunicação"),
            ]
        elif db_session is None and t == "BOVA11":
            holdings = [
                ETFUnderlyingAsset(ticker="VALE3", name="Vale S.A.", weight_pct=13.2, sector="Materiais Básicos"),
                ETFUnderlyingAsset(ticker="PETR4", name="Petrobras PN", weight_pct=11.5, sector="Petróleo e Gás"),
                ETFUnderlyingAsset(ticker="ITUB4", name="Itaú Unibanco PN", weight_pct=8.4, sector="Financeiro"),
                ETFUnderlyingAsset(ticker="PETR3", name="Petrobras ON", weight_pct=6.1, sector="Petróleo e Gás"),
                ETFUnderlyingAsset(ticker="BBDC4", name="Banco Bradesco PN", weight_pct=4.5, sector="Financeiro"),
            ]
        else:
            holdings = []

        flows = []
        drawdown_data = await self.get_etf_drawdown(t, db_session)

        return ETFDetailResponse(
            ticker=t,
            name=name,
            benchmark_index=benchmark_index,
            provider=provider,
            current_price=round(current_price, 2),
            nav_per_share=round(nav_per_share, 2) if nav_per_share is not None else None,
            nav_spread_pct=round(spread_pct, 2) if spread_pct is not None else None,
            ter_pct=ter_pct,
            primary_fee_pct=primary_fee_pct,
            secondary_fee_pct=secondary_fee_pct,
            policy=policy,
            shares_lending_pct=14.5,
            max_lending_limit_pct=max_lending_limit_pct,
            underlying_holdings=holdings,
            flow_history_30d=flows,
            drawdown=drawdown_data,
        )
