from typing import List, Optional
from pydantic import BaseModel, Field


class TreasuryBondItem(BaseModel):
    name: str
    type: str  # SELIC, PREFIXADO, IPCA
    maturity_date: str
    annual_rate_pct: float
    unit_price: float
    min_investment_value: float


class YieldCurvePoint(BaseModel):
    term_years: float
    zero_rate_pct: float
    inflation_implied_pct: Optional[float] = None


class FixedIncomeResponse(BaseModel):
    bonds: List[TreasuryBondItem] = Field(default_factory=list)
    ettj_curves: List[YieldCurvePoint] = Field(default_factory=list)
