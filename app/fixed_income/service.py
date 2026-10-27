from app.fixed_income.schemas import FixedIncomeResponse, TreasuryBondItem, YieldCurvePoint


class FixedIncomeService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_treasury_and_curves(self) -> FixedIncomeResponse:
        bonds = [
            TreasuryBondItem(name="Tesouro Selic 2029", type="SELIC", maturity_date="2029-03-01", annual_rate_pct=11.25, unit_price=15240.50, min_investment_value=152.40),
            TreasuryBondItem(name="Tesouro Prefixado 2027", type="PREFIXADO", maturity_date="2027-01-01", annual_rate_pct=12.15, unit_price=820.40, min_investment_value=32.81),
            TreasuryBondItem(name="Tesouro Prefixado 2031", type="PREFIXADO", maturity_date="2031-01-01", annual_rate_pct=12.60, unit_price=530.15, min_investment_value=31.80),
            TreasuryBondItem(name="Tesouro IPCA+ 2029", type="IPCA", maturity_date="2029-05-15", annual_rate_pct=6.45, unit_price=3420.80, min_investment_value=34.20),
            TreasuryBondItem(name="Tesouro IPCA+ 2035", type="IPCA", maturity_date="2035-05-15", annual_rate_pct=6.55, unit_price=2210.30, min_investment_value=44.20),
            TreasuryBondItem(name="Tesouro IPCA+ 2045", type="IPCA", maturity_date="2045-05-15", annual_rate_pct=6.62, unit_price=1310.50, min_investment_value=39.31),
        ]

        curves = [
            YieldCurvePoint(term_years=0.5, zero_rate_pct=11.25, inflation_implied_pct=4.10),
            YieldCurvePoint(term_years=1.0, zero_rate_pct=11.80, inflation_implied_pct=4.35),
            YieldCurvePoint(term_years=2.0, zero_rate_pct=12.15, inflation_implied_pct=4.60),
            YieldCurvePoint(term_years=3.0, zero_rate_pct=12.35, inflation_implied_pct=4.75),
            YieldCurvePoint(term_years=5.0, zero_rate_pct=12.55, inflation_implied_pct=4.95),
            YieldCurvePoint(term_years=10.0, zero_rate_pct=12.75, inflation_implied_pct=5.10),
        ]

        return FixedIncomeResponse(bonds=bonds, ettj_curves=curves)
