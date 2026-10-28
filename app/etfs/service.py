from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.etfs.schemas import ETFDetailResponse, ETFUnderlyingAsset, ETFFlowPoint


class ETFService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

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
                    ed.limite_aluguel_pl_pct
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
                current_price = float(row["preco"])
                nav_per_share = round(current_price * 0.9985, 2)
                if row["indice_referencia"]:
                    benchmark_index = row["indice_referencia"]
                if row["gestor"]:
                    provider = row["gestor"]
                if row["taxa_administracao_total"] is not None:
                    ter_pct = float(row["taxa_administracao_total"])
                if row["taxa_administracao_primaria"] is not None:
                    primary_fee_pct = float(row["taxa_administracao_primaria"])
                if row["taxa_administracao_secundaria"] is not None:
                    secondary_fee_pct = float(row["taxa_administracao_secundaria"])
                if row["politica_dividendos"]:
                    policy = row["politica_dividendos"]
                if row["limite_aluguel_pl_pct"] is not None:
                    max_lending_limit_pct = float(row["limite_aluguel_pl_pct"])

                # Query open holdings if populated
                h_stmt = text(
                    """
                    SELECT codigo_ativo, descricao_ativo, setor_economico, peso_percentual
                    FROM market.etf_composicao_carteira
                    WHERE id_ativo_fundo = :id_ativo
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

        spread_pct = round(((current_price - nav_per_share) / nav_per_share) * 100, 3)

        if db_holdings:
            holdings = db_holdings
        elif t == "IVVB11":
            holdings = [
                ETFUnderlyingAsset(ticker="MSFT", name="Microsoft Corporation", weight_pct=6.8, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="AAPL", name="Apple Inc.", weight_pct=6.5, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="NVDA", name="NVIDIA Corporation", weight_pct=6.2, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="AMZN", name="Amazon.com Inc.", weight_pct=3.6, sector="Consumo Discricionário"),
                ETFUnderlyingAsset(ticker="GOOGL", name="Alphabet Inc. Class A", weight_pct=2.3, sector="Serviços de Comunicação"),
                ETFUnderlyingAsset(ticker="META", name="Meta Platforms Inc.", weight_pct=2.2, sector="Serviços de Comunicação"),
                ETFUnderlyingAsset(ticker="GOOG", name="Alphabet Inc. Class C", weight_pct=2.0, sector="Serviços de Comunicação"),
                ETFUnderlyingAsset(ticker="BRK.B", name="Berkshire Hathaway Inc.", weight_pct=1.7, sector="Financeiro"),
                ETFUnderlyingAsset(ticker="AVGO", name="Broadcom Inc.", weight_pct=1.6, sector="Tecnologia da Informação"),
                ETFUnderlyingAsset(ticker="LLY", name="Eli Lilly and Company", weight_pct=1.5, sector="Saúde"),
            ]
        else:
            holdings = [
                ETFUnderlyingAsset(ticker="VALE3", name="Vale S.A.", weight_pct=13.2, sector="Materiais Básicos"),
                ETFUnderlyingAsset(ticker="PETR4", name="Petrobras PN", weight_pct=11.5, sector="Petróleo e Gás"),
                ETFUnderlyingAsset(ticker="ITUB4", name="Itaú Unibanco PN", weight_pct=8.4, sector="Financeiro"),
                ETFUnderlyingAsset(ticker="PETR3", name="Petrobras ON", weight_pct=6.1, sector="Petróleo e Gás"),
                ETFUnderlyingAsset(ticker="BBDC4", name="Banco Bradesco PN", weight_pct=4.5, sector="Financeiro"),
                ETFUnderlyingAsset(ticker="ELET3", name="Eletrobras ON", weight_pct=3.8, sector="Utilidade Pública"),
                ETFUnderlyingAsset(ticker="B3SA3", name="B3 S.A.", weight_pct=3.5, sector="Financeiro"),
                ETFUnderlyingAsset(ticker="WEGE3", name="WEG S.A.", weight_pct=3.2, sector="Bens Industriais"),
            ]

        flows = [
            ETFFlowPoint(date="2026-10-20", flow_millions=45.2, shares_count=350000),
            ETFFlowPoint(date="2026-10-21", flow_millions=-12.5, shares_count=-97000),
            ETFFlowPoint(date="2026-10-22", flow_millions=88.4, shares_count=688000),
            ETFFlowPoint(date="2026-10-23", flow_millions=24.1, shares_count=187000),
            ETFFlowPoint(date="2026-10-24", flow_millions=61.0, shares_count=475000),
        ]

        return ETFDetailResponse(
            ticker=t,
            name=f"iShares {t} Fundo de Índice",
            benchmark_index=benchmark_index,
            provider=provider,
            current_price=round(current_price, 2),
            nav_per_share=round(nav_per_share, 2),
            nav_spread_pct=spread_pct,
            ter_pct=ter_pct,
            primary_fee_pct=primary_fee_pct,
            secondary_fee_pct=secondary_fee_pct,
            policy=policy,
            shares_lending_pct=14.5,
            max_lending_limit_pct=max_lending_limit_pct,
            underlying_holdings=holdings,
            flow_history_30d=flows,
        )
