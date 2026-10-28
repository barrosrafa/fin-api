from typing import List, Optional
from pydantic import BaseModel, Field


class FIIPropertyItem(BaseModel):
    id: str
    name: str
    type: str  # LOGISTICA, LAJES_CORP, SHOPPING, etc.
    address: str
    city: str
    state: str
    abl_m2: float
    occupancy_pct: float
    siila_standard: str  # AAA, AA, A, B, C
    fund_share_pct: float = 100.0


class FIIBrickScoreAxis(BaseModel):
    name: str
    score: float
    weight: float
    status: str
    comment: str


class FIITenantConcentration(BaseModel):
    tenant_name: str
    sector: str
    revenue_pct: float
    contract_type: str  # TIPICO, ATIPICO


class FIICRIHolding(BaseModel):
    code: str
    debtor: str
    indexer: str  # IPCA + X%, CDI + X%
    coupon_pct: float
    ltv_pct: float
    guarantees: str
    rating: Optional[str] = "AA"


class FIIDetailResponse(BaseModel):
    ticker: str
    name: str
    segment: str
    current_price: float
    pvp: float
    dividend_yield_12m: float
    net_worth: float
    physical_vacancy_pct: float
    financial_vacancy_pct: float
    wault_years: float = 4.2
    properties: List[FIIPropertyItem] = Field(default_factory=list)
    brick_score: List[FIIBrickScoreAxis] = Field(default_factory=list)
    top_tenants: List[FIITenantConcentration] = Field(default_factory=list)
    cri_portfolio: List[FIICRIHolding] = Field(default_factory=list)
    quarterly_dre: Optional[dict] = None


class FIIRankingItem(BaseModel):
    rank: int
    ticker: str
    name: str
    segment: str
    price: float
    dy_12m: float
    pvp: float
    net_worth: float
    physical_vacancy_pct: float
    financial_vacancy_pct: float
    liquidity_daily: float


class FIIVacancyPoint(BaseModel):
    data_referencia: str
    vacancia_fisica_pct: float
    vacancia_financeira_pct: float
    abl_propria_m2: Optional[float] = None
    area_ocupada_m2: Optional[float] = None


class FIIVacancyHistoryResponse(BaseModel):
    ticker: str
    history: List[FIIVacancyPoint] = Field(default_factory=list)

