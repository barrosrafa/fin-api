from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class StockChecklistItem(BaseModel):
    id: str
    title: str
    pillar: str
    passed: bool
    metric_value: str
    target_value: str
    explanation: str


class StockRevenueSegment(BaseModel):
    segment_name: str
    revenue_amount: float
    percentage: float


class StockConsensusEstimates(BaseModel):
    target_price_min: float
    target_price_avg: float
    target_price_max: float
    recommendation: str  # COMPRA_FORTE, COMPRA, NEUTRO, VENDA
    analysts_count: int
    forecast_2026: Dict[str, float]
    forecast_2027: Dict[str, float]


class DREItemResponse(BaseModel):
    year: str
    netRevenue: float
    cogs: float
    grossProfit: float
    operatingExpenses: float
    ebitda: float
    ebit: float
    financialResult: float
    taxes: float
    netIncome: float
    netMarginPct: float


class DividendItemResponse(BaseModel):
    id: str
    assetTicker: str
    type: str
    referenceMonth: str
    dateCom: str
    paymentDate: str
    valuePerShare: float
    yieldOnCostPct: float


class TechnicalIndicatorsResponse(BaseModel):
    ticker: str
    timeframe: str
    rsi14: float
    macd: str
    stochastic: float
    bollingerWidth: float
    pivotPoint: float
    support1: float
    support2: float
    resistance1: float
    resistance2: float
    summarySignal: str
    buySignalsCount: int
    neutralSignalsCount: int
    sellSignalsCount: int


class AIVerdictResponse(BaseModel):
    ticker: str
    sentiment: str
    confidenceScore: float
    executiveSummary: str
    swot: Dict[str, List[str]]
    anomaliesDetected: List[str] = Field(default_factory=list)
    lastAnalyzedDoc: str
    timestamp: str


class StockValuationResponse(BaseModel):
    ticker: str
    name: str
    current_price: float
    lpa: float
    vpa: float
    dpa_medio: float
    graham_fair_value: float
    graham_upside_pct: float
    bazin_ceiling_price: float
    bazin_upside_pct: float
    gordon_fair_value: Optional[float] = None
    dcf_intrinsic_value: float
    dcf_upside_pct: float
    margin_of_safety_pct: float
    checklist: List[StockChecklistItem] = Field(default_factory=list)
    dre_history: List[DREItemResponse] = Field(default_factory=list)
    dividends: List[DividendItemResponse] = Field(default_factory=list)
    technical: Optional[TechnicalIndicatorsResponse] = None
    ai_verdict: Optional[AIVerdictResponse] = None
    revenue_by_segment: List[StockRevenueSegment] = Field(default_factory=list)
    revenue_by_geography: List[StockRevenueSegment] = Field(default_factory=list)
    consensus: Optional[StockConsensusEstimates] = None


class StockDetailsResponse(BaseModel):
    ticker: str
    name: str
    tipo: Optional[str] = None
    classe_acao: Optional[str] = None
    sector: Optional[str] = None
    subsector: Optional[str] = None
    segmento: Optional[str] = None
    current_price: float
    data_cotacao: Optional[str] = None
    min_52_semanas: Optional[float] = None
    max_52_semanas: Optional[float] = None
    volume_medio_2m: Optional[float] = None
    valor_mercado: Optional[float] = None
    valor_firma: Optional[float] = None
    numero_acoes: Optional[int] = None
    is_financial_institution: bool = False


class StockMultiplesResponse(BaseModel):
    ticker: str
    pl: Optional[float] = None
    pvp: Optional[float] = None
    pebit: Optional[float] = None
    psr: Optional[float] = None
    p_ativos: Optional[float] = None
    p_cap_giro: Optional[float] = None
    p_ativo_circ_liq: Optional[float] = None
    dividend_yield: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ev_ebit: Optional[float] = None
    margem_bruta: Optional[float] = None
    margem_ebit: Optional[float] = None
    margem_liquida: Optional[float] = None
    roic: Optional[float] = None
    roe: Optional[float] = None
    liquidez_corrente: Optional[float] = None
    div_bruta_patrimonio: Optional[float] = None
    giro_ativos: Optional[float] = None
    lpa: Optional[float] = None
    vpa: Optional[float] = None


class StockFinancialsResponse(BaseModel):
    ticker: str
    is_financial_institution: bool = False
    data_balanco: Optional[str] = None
    ativo_total: Optional[float] = None
    disponibilidades: Optional[float] = None
    ativo_circulante: Optional[float] = None
    divida_bruta: Optional[float] = None
    divida_liquida: Optional[float] = None
    patrimonio_liquido: Optional[float] = None
    receita_liquida_12m: Optional[float] = None
    receita_liquida_3m: Optional[float] = None
    ebit_12m: Optional[float] = None
    ebit_3m: Optional[float] = None
    lucro_liquido_12m: Optional[float] = None
    lucro_liquido_3m: Optional[float] = None
    # Banking / Financial Institutions specific
    carteira_credito: Optional[float] = None
    depositos: Optional[float] = None
    resultado_intermediacao_12m: Optional[float] = None
    resultado_intermediacao_3m: Optional[float] = None
    receita_servicos_12m: Optional[float] = None
    receita_servicos_3m: Optional[float] = None


class StockCompleteDetailsResponse(BaseModel):
    details: StockDetailsResponse
    multiples: StockMultiplesResponse
    financials: StockFinancialsResponse


class FinancialStatementRow(BaseModel):
    account_name: str
    account_code: str
    is_total: bool = False
    indentation_level: int = 0
    values_by_year: Dict[str, Optional[float]] = Field(default_factory=dict)


class FinancialMatrixResponse(BaseModel):
    ticker: str
    company_name: str
    period_type: str  # ANUAL ou TRIMESTRAL
    years: List[str] = Field(default_factory=list)
    dre: List[FinancialStatementRow] = Field(default_factory=list)
    balance_sheet: List[FinancialStatementRow] = Field(default_factory=list)
    cash_flow: List[FinancialStatementRow] = Field(default_factory=list)
    margins_and_returns: List[FinancialStatementRow] = Field(default_factory=list)


class ConsistencyScreenerItem(BaseModel):
    ticker: str
    company_name: str
    sector: str
    segment: str
    consecutive_profitable_years: int
    cagr_lucro_5y: Optional[float] = None
    current_pe: Optional[float] = None
    current_pb: Optional[float] = None
    current_dy: float
    current_roe: float


class StockRankingItem(BaseModel):
    rank: int
    ticker: str
    name: str
    sector: str
    price: float
    dy: float
    pl: Optional[float] = None
    pvp: Optional[float] = None
    roe: Optional[float] = None
    roic: Optional[float] = None
    margem_liquida: Optional[float] = None
    ev_ebitda: Optional[float] = None
    liquidez: float


class DividendMatrixRow(BaseModel):
    year: int
    months: List[Optional[float]] = Field(default_factory=list)  # 12 meses (Jan a Dez)
    annual_total: float
    yield_on_cost_pct: float = 0.0


class DividendMatrixResponse(BaseModel):
    ticker: str
    years: List[int] = Field(default_factory=list)
    matrix: List[DividendMatrixRow] = Field(default_factory=list)


class USEquityItem(BaseModel):
    ticker: str
    name: str
    price_usd: float
    price_brl: float
    ptax_rate: float
    pe_ratio: Optional[float] = None
    dividend_yield_pct: float
    market_cap_usd: Optional[float] = None
    sector: str = "Technology"


class REITItem(BaseModel):
    ticker: str
    name: str
    subtipo_reit: str
    price_usd: float
    price_brl: float
    ptax_rate: float
    ffo_per_share: float
    affo_per_share: float
    p_ffo: float
    p_affo: float
    ffo_payout_pct: float
    occupancy_rate_pct: float
    gross_dy_pct: float
    net_dy_brl_pct: float  # With 30% IRS Withholding tax
    properties_count: int



