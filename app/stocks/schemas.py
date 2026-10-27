from typing import List, Optional, Dict
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
    revenue_by_segment: List[StockRevenueSegment] = Field(default_factory=list)
    revenue_by_geography: List[StockRevenueSegment] = Field(default_factory=list)
    consensus: Optional[StockConsensusEstimates] = None
