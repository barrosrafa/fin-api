from typing import List, Optional
from pydantic import BaseModel, Field
from app.market.lifecycle import TradingStatus


class FIIPropertyItem(BaseModel):
    id: str
    name: str
    type: Optional[str] = None  # LOGISTICA, LAJES_CORP, SHOPPING, etc.
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    abl_m2: Optional[float] = None
    occupancy_pct: Optional[float] = None
    siila_standard: Optional[str] = None  # AAA, AA, A, B, C
    fund_share_pct: Optional[float] = None


class FIIBrickScoreAxis(BaseModel):
    name: str
    score: Optional[float] = None
    weight: Optional[float] = None
    status: str
    comment: str


class FIITenantConcentration(BaseModel):
    tenant_name: str
    sector: str
    revenue_pct: Optional[float] = None
    contract_type: str  # TIPICO, ATIPICO


class FIICRIHolding(BaseModel):
    code: str
    debtor: str
    indexer: str  # IPCA + X%, CDI + X%
    coupon_pct: Optional[float] = None
    ltv_pct: Optional[float] = None
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
    pvp: Optional[float] = None
    vp_per_share: Optional[float] = None
    dividend_yield_12m: Optional[float] = None
    last_dividend: Optional[float] = None
    expense_pct: Optional[float] = None
    cash_pct: Optional[float] = None
    default_pct: Optional[float] = None
    physical_vacancy_pct: Optional[float] = None
    financial_vacancy_pct: Optional[float] = None
    shares_count: Optional[int] = None
    shareholders_count: Optional[int] = None
    market_cap: Optional[float] = None
    daily_trades: Optional[int] = None
    daily_volume: Optional[float] = None
    net_worth: Optional[float] = None
    change_1d: Optional[float] = None
    change_12m: Optional[float] = None
    min_52w: Optional[float] = None
    max_52w: Optional[float] = None
    cagr_dividends_3y: Optional[float] = None
    cagr_share_value_3y: Optional[float] = None
    quote_datetime: Optional[str] = None


class FIIDividendItem(BaseModel):
    id: str
    type: str
    reference_month: Optional[str] = None
    date_approval: Optional[str] = None
    date_com: str
    date_ex: Optional[str] = None
    date_payment: str
    value_per_share: Optional[float] = None
    yield_pct: Optional[float] = None
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
    total_assets: Optional[float] = None
    liquid_assets: dict
    investments: dict
    receivables: dict
    total_liabilities: dict
    net_worth: Optional[float] = None
class FIILucratividadeData(BaseModel):
    rental_income: Optional[float] = None
    property_sale_income: Optional[float] = None
    securities_income: Optional[float] = None
    financial_income: Optional[float] = None
    operating_expenses: Optional[float] = None
    admin_fee_expense: Optional[float] = None
    other_expenses: Optional[float] = None
    net_profit: Optional[float] = None
    distributed_per_share: Optional[float] = None
class FIIDetailResponse(BaseModel):
    fundamentals_source: Optional[str] = None
    fundamentals_date: Optional[str] = None
    source: Optional[str] = None
    quote_date: Optional[str] = None
    trading: TradingStatus = Field(default_factory=TradingStatus)
    fundamentals_note: str = "P/VP usa informe CVM oficial, quando há referência não ambígua até a sessão da cotação. DY 12M indisponível sem cobertura completa verificável."
    ticker: str
    name: str
    segment: str
    current_price: Optional[float] = None
    pvp: Optional[float] = None
    dividend_yield_12m: Optional[float] = None
    net_worth: Optional[float] = None
    physical_vacancy_pct: Optional[float] = None
    financial_vacancy_pct: Optional[float] = None
    wault_years: Optional[float] = None
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
    rank: Optional[int] = None
    ticker: str
    name: str
    segment: str
    price: Optional[float] = None
    dy_12m: Optional[float] = None
    pvp: Optional[float] = None
    net_worth: Optional[float] = None
    physical_vacancy_pct: Optional[float] = None
    financial_vacancy_pct: Optional[float] = None
    liquidity_daily: Optional[float] = None
    source: Optional[str] = None
    quote_date: Optional[str] = None
    trading: TradingStatus = Field(default_factory=TradingStatus)
class FIIVacancyPoint(BaseModel):
    data_referencia: str
    vacancia_fisica_pct: Optional[float] = None
    vacancia_financeira_pct: Optional[float] = None
    abl_propria_m2: Optional[float] = None
    area_ocupada_m2: Optional[float] = None


class FIIVacancyHistoryResponse(BaseModel):
    ticker: str
    history: List[FIIVacancyPoint] = Field(default_factory=list)

