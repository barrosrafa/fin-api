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
