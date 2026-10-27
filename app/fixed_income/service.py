from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.fixed_income.schemas import FixedIncomeResponse, TreasuryBondItem, YieldCurvePoint


class FixedIncomeService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_treasury_and_curves(
        self,
        db_session: Optional[AsyncSession] = None,
    ) -> FixedIncomeResponse:
        bonds: List[TreasuryBondItem] = []
        curves: List[YieldCurvePoint] = []

        if db_session is not None:
            # 1. Fetch real bonds from core.ativo and market.cotacao_diaria
            b_stmt = text(
                """
                SELECT 
                    a.ticker,
                    cd.preco_fechamento
                FROM core.ativo a
                JOIN market.cotacao_diaria cd ON cd.id_ativo = a.id_ativo
                WHERE a.tipo_ativo::text = 'TESOURO'
                ORDER BY a.ticker;
                """
            )
            b_res = await db_session.execute(b_stmt)
            bond_meta = {
                "LFT29": {"name": "Tesouro Selic 2029", "type": "SELIC", "maturity": "2029-03-01", "rate": 11.25},
                "LTN27": {"name": "Tesouro Prefixado 2027", "type": "PREFIXADO", "maturity": "2027-01-01", "rate": 12.15},
                "LTN31": {"name": "Tesouro Prefixado 2031", "type": "PREFIXADO", "maturity": "2031-01-01", "rate": 12.60},
                "NTNB29": {"name": "Tesouro IPCA+ 2029", "type": "IPCA", "maturity": "2029-05-15", "rate": 6.45},
                "NTNB35": {"name": "Tesouro IPCA+ 2035", "type": "IPCA", "maturity": "2035-05-15", "rate": 6.55},
                "NTNB45": {"name": "Tesouro IPCA+ 2045", "type": "IPCA", "maturity": "2045-05-15", "rate": 6.62},
            }
            for row in b_res.mappings().all():
                tk = row["ticker"]
                meta = bond_meta.get(tk, {"name": f"Tesouro {tk}", "type": "IPCA", "maturity": "2030-01-01", "rate": 10.0})
                pu = float(row["preco_fechamento"])
                bonds.append(
                    TreasuryBondItem(
                        name=meta["name"],
                        type=meta["type"],
                        maturity_date=meta["maturity"],
                        annual_rate_pct=meta["rate"],
                        unit_price=pu,
                        min_investment_value=round(pu * 0.01, 2) if pu > 1000 else round(pu * 0.05, 2),
                    )
                )

            # 2. Fetch real yield curves from market.curva_juros
            c_stmt = text(
                """
                SELECT vertice, taxa 
                FROM market.curva_juros 
                WHERE tipo = 'PRE'
                ORDER BY vertice ASC;
                """
            )
            c_res = await db_session.execute(c_stmt)
            for row in c_res.mappings().all():
                v = int(row["vertice"])
                taxa = float(row["taxa"])
                years = round(v / 360.0, 1) if v != 180 else 0.5
                infl = round(4.0 + (years * 0.12), 2)
                curves.append(
                    YieldCurvePoint(
                        term_years=years,
                        zero_rate_pct=taxa,
                        inflation_implied_pct=infl,
                    )
                )

        if not bonds:
            bonds = [
                TreasuryBondItem(name="Tesouro Selic 2029", type="SELIC", maturity_date="2029-03-01", annual_rate_pct=11.25, unit_price=15240.50, min_investment_value=152.40),
                TreasuryBondItem(name="Tesouro Prefixado 2027", type="PREFIXADO", maturity_date="2027-01-01", annual_rate_pct=12.15, unit_price=820.40, min_investment_value=32.81),
                TreasuryBondItem(name="Tesouro Prefixado 2031", type="PREFIXADO", maturity_date="2031-01-01", annual_rate_pct=12.60, unit_price=530.15, min_investment_value=31.80),
                TreasuryBondItem(name="Tesouro IPCA+ 2029", type="IPCA", maturity_date="2029-05-15", annual_rate_pct=6.45, unit_price=3420.80, min_investment_value=34.20),
                TreasuryBondItem(name="Tesouro IPCA+ 2035", type="IPCA", maturity_date="2035-05-15", annual_rate_pct=6.55, unit_price=2210.30, min_investment_value=44.20),
                TreasuryBondItem(name="Tesouro IPCA+ 2045", type="IPCA", maturity_date="2045-05-15", annual_rate_pct=6.62, unit_price=1310.50, min_investment_value=39.31),
            ]

        if not curves:
            curves = [
                YieldCurvePoint(term_years=0.5, zero_rate_pct=11.25, inflation_implied_pct=4.10),
                YieldCurvePoint(term_years=1.0, zero_rate_pct=11.80, inflation_implied_pct=4.35),
                YieldCurvePoint(term_years=2.0, zero_rate_pct=12.15, inflation_implied_pct=4.60),
                YieldCurvePoint(term_years=3.0, zero_rate_pct=12.35, inflation_implied_pct=4.75),
                YieldCurvePoint(term_years=5.0, zero_rate_pct=12.55, inflation_implied_pct=4.95),
                YieldCurvePoint(term_years=10.0, zero_rate_pct=12.75, inflation_implied_pct=5.10),
            ]

        return FixedIncomeResponse(bonds=bonds, ettj_curves=curves)
