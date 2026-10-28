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


class FIICadastralData(BaseModel):
    legal_name: Optional[str] = None
    cnpj: Optional[str] = None
    trading_code: str
    administrator_name: Optional[str] = None
    administrator_cnpj: Optional[str] = None
    administrator_address: Optional[str] = None
    administrator_phone: Optional[str] = None
    administrator_site: Optional[str] = None
    manager_name: Optional[str] = None
    mandate: Optional[str] = None
    target_audience: Optional[str] = None
    duration_term: Optional[str] = None
    management_type: Optional[str] = None
    admin_fee_desc: Optional[str] = None
    shares_count: Optional[int] = None
    shareholders_count: Optional[int] = None


class FIIIndicatorsData(BaseModel):
    pvp: float
    vp_per_share: float
    dividend_yield_12m: float
    last_dividend: float
    expense_pct: float
    cash_pct: float
    default_pct: float
    physical_vacancy_pct: float
    financial_vacancy_pct: float
    shares_count: int
    shareholders_count: int
    market_cap: float
    daily_trades: int
    daily_volume: float
    net_worth: float
    change_1d: float
    change_12m: float
    min_52w: float
    max_52w: float
    cagr_dividends_3y: float
    cagr_share_value_3y: float
    quote_datetime: Optional[str] = None


class FIIDividendItem(BaseModel):
    id: str
    type: str
    reference_month: Optional[str] = None
    date_approval: Optional[str] = None
    date_com: str
    date_ex: Optional[str] = None
    date_payment: str
    value_per_share: float
    yield_pct: float
    status: str


class FIIDisclosureItem(BaseModel):
    document_id: str
    document_type: str
    title: str
    document_date: str
    published_at: Optional[str] = None
    source_url: Optional[str] = None
    external_id: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_sentiment: Optional[str] = None


class FIIBalanceSheetData(BaseModel):
    data_referencia: str
    total_assets: float
    liquid_assets: dict
    investments: dict
    receivables: dict
    total_liabilities: dict
    net_worth: float


class FIILucratividadeData(BaseModel):
    rental_income: float
    property_sale_income: float
    securities_income: float
    financial_income: float
    operating_expenses: float
    admin_fee_expense: float
    other_expenses: float
    net_profit: float
    distributed_per_share: float


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
    cadastral: Optional[FIICadastralData] = None
    indicators: Optional[FIIIndicatorsData] = None
    dividends: List[FIIDividendItem] = Field(default_factory=list)
    disclosures: List[FIIDisclosureItem] = Field(default_factory=list)
    balance_sheet: Optional[FIIBalanceSheetData] = None
    lucratividade: Optional[FIILucratividadeData] = None


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

