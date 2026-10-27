from app.funds.schemas import FundRiskMatrixResponse, QuantRiskWindow, FundHoldingCDA


class FundService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_fund_risk_matrix(self, fund_id: str) -> FundRiskMatrixResponse:
        windows = [
            QuantRiskWindow(timeframe="1M", accumulated_return_pct=1.45, volatility_pct=11.2, sharpe=1.24, sortino=1.65, treynor=0.14, jensen_alpha=0.22, beta=0.88, tracking_error=2.4, information_ratio=0.72, max_drawdown_pct=-1.2, recovery_days=8, positive_months_pct=100.0),
            QuantRiskWindow(timeframe="3M", accumulated_return_pct=4.80, volatility_pct=12.4, sharpe=1.35, sortino=1.82, treynor=0.16, jensen_alpha=0.38, beta=0.91, tracking_error=2.8, information_ratio=0.81, max_drawdown_pct=-2.4, recovery_days=14, positive_months_pct=100.0),
            QuantRiskWindow(timeframe="6M", accumulated_return_pct=9.60, volatility_pct=13.1, sharpe=1.42, sortino=1.95, treynor=0.18, jensen_alpha=0.55, beta=0.94, tracking_error=3.1, information_ratio=0.88, max_drawdown_pct=-3.8, recovery_days=22, positive_months_pct=83.3),
            QuantRiskWindow(timeframe="12M", accumulated_return_pct=18.40, volatility_pct=14.0, sharpe=1.58, sortino=2.10, treynor=0.21, jensen_alpha=0.95, beta=0.96, tracking_error=3.5, information_ratio=0.94, max_drawdown_pct=-5.4, recovery_days=34, positive_months_pct=83.3),
            QuantRiskWindow(timeframe="24M", accumulated_return_pct=34.20, volatility_pct=14.5, sharpe=1.62, sortino=2.18, treynor=0.22, jensen_alpha=1.10, beta=0.97, tracking_error=3.6, information_ratio=0.98, max_drawdown_pct=-7.1, recovery_days=45, positive_months_pct=79.2),
            QuantRiskWindow(timeframe="36M", accumulated_return_pct=52.80, volatility_pct=15.1, sharpe=1.70, sortino=2.30, treynor=0.24, jensen_alpha=1.28, beta=0.98, tracking_error=3.8, information_ratio=1.05, max_drawdown_pct=-8.9, recovery_days=58, positive_months_pct=77.8),
            QuantRiskWindow(timeframe="YTD", accumulated_return_pct=12.10, volatility_pct=13.6, sharpe=1.48, sortino=2.02, treynor=0.19, jensen_alpha=0.68, beta=0.95, tracking_error=3.3, information_ratio=0.89, max_drawdown_pct=-4.1, recovery_days=19, positive_months_pct=87.5),
        ]

        cda = [
            FundHoldingCDA(asset_name="NTN-B 2035 (Tesouro IPCA+)", asset_type="TITULO_PUBLICO", identifier="BRSTNCNTB350", weight_pct=32.5, financial_value=650_000_000.0),
            FundHoldingCDA(asset_name="LFT 2029 (Tesouro Selic)", asset_type="TITULO_PUBLICO", identifier="BRSTNCLFT290", weight_pct=24.0, financial_value=480_000_000.0),
            FundHoldingCDA(asset_name="Debênture Vale S.A. 2031", asset_type="DEBENTURE", identifier="VALE31", weight_pct=12.5, financial_value=250_000_000.0),
            FundHoldingCDA(asset_name="Itaú Unibanco PN", asset_type="ACAO", identifier="ITUB4", weight_pct=10.0, financial_value=200_000_000.0),
            FundHoldingCDA(asset_name="Petrobras PN", asset_type="ACAO", identifier="PETR4", weight_pct=8.5, financial_value=170_000_000.0),
            FundHoldingCDA(asset_name="Operações Compromissadas / Caixa", asset_type="CAIXA", identifier="CAIXA_BR", weight_pct=12.5, financial_value=250_000_000.0),
        ]

        return FundRiskMatrixResponse(
            fund_id=fund_id,
            name=f"Fundo Multimercado Macro Estratégia {fund_id}",
            cnpj="32.845.192/0001-44",
            category_cvm175="Multimercado Livre - Classe Investimento Geral",
            benchmark="CDI",
            net_worth=2_000_000_000.0,
            matrix=windows,
            cda_holdings=cda,
        )
