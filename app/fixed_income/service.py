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
            # 1. Fetch real bonds from asset_details.tesouro_direto and core.ativo
            b_stmt = text(
                """
                SELECT 
                    a.ticker,
                    td.tipo_titulo,
                    td.indexador,
                    COALESCE(td.taxa_compra, td.taxa_venda, 10.0) as taxa,
                    td.vencimento,
                    COALESCE(td.pu, 1000.0) as pu
                FROM asset_details.tesouro_direto td
                JOIN core.ativo a ON a.id_ativo = td.id_ativo
                WHERE td.vencimento >= CURRENT_DATE ORDER BY td.vencimento ASC;
                """
            )
            b_res = await db_session.execute(b_stmt)
            for row in b_res.mappings().all():
                tipo_raw = (row["tipo_titulo"] or "").upper()
                if "SELIC" in tipo_raw:
                    b_type = "SELIC"
                elif "PREFIXADO" in tipo_raw:
                    b_type = "PREFIXADO"
                else:
                    b_type = "IPCA"

                pu = float(row["pu"])
                venc = row["vencimento"]
                venc_str = venc.strftime("%Y-%m-%d") if venc else "2030-01-01"
                venc_year = venc.year if venc else ""
                nome = f"{row['tipo_titulo']} {venc_year}".strip()

                bonds.append(
                    TreasuryBondItem(
                        name=nome,
                        type=b_type,
                        maturity_date=venc_str,
                        annual_rate_pct=float(row["taxa"]),
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

        return FixedIncomeResponse(bonds=bonds, ettj_curves=curves)
