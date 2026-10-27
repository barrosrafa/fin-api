from app.etfs.schemas import ETFDetailResponse, ETFUnderlyingAsset, ETFFlowPoint


class ETFService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_etf_detail(self, ticker: str) -> ETFDetailResponse:
        t = ticker.upper()
        current_price = 128.40 if t == "BOVA11" else 285.50
        nav_per_share = 128.25 if t == "BOVA11" else 285.10
        spread_pct = round(((current_price - nav_per_share) / nav_per_share) * 100, 3)

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
            benchmark_index="IBOVESPA" if t == "BOVA11" else "S&P 500 BRL",
            provider="BlackRock Brasil",
            current_price=current_price,
            nav_per_share=nav_per_share,
            nav_spread_pct=spread_pct,
            ter_pct=0.30 if t == "BOVA11" else 0.24,
            primary_fee_pct=0.30 if t == "BOVA11" else 0.21,
            secondary_fee_pct=0.00 if t == "BOVA11" else 0.03,
            policy="ACUMULATIVO",
            shares_lending_pct=14.5,
            max_lending_limit_pct=30.0,
            underlying_holdings=holdings,
            flow_history_30d=flows,
        )
