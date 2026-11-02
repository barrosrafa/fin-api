from typing import List, Optional
from pydantic import BaseModel, Field
from app.market.lifecycle import TradingStatus


class ETFUnderlyingAsset(BaseModel):
    ticker: str
    name: str
    weight_pct: float
    sector: str


class ETFFlowPoint(BaseModel):
    date: str
    flow_millions: float  # + creation, - redemption
    shares_count: int


class ETFDrawdownResponse(BaseModel):
    ticker: str
    max_drawdown_pct: Optional[float] = None
    valley_date: Optional[str] = None
    recovery_days: Optional[int] = None
    drawdown_curve: List[List[float]] = Field(default_factory=list)


class ETFDetailResponse(BaseModel):
    source: Optional[str] = None
    quote_date: Optional[str] = None
    trading: TradingStatus = Field(default_factory=TradingStatus)
    ticker: str
    name: str
    benchmark_index: Optional[str] = None
    provider: Optional[str] = None
    current_price: Optional[float] = None
    nav_per_share: Optional[float] = None
    nav_spread_pct: Optional[float] = None  # (price - nav) / nav * 100
    ter_pct: Optional[float] = None
    primary_fee_pct: Optional[float] = None
    secondary_fee_pct: Optional[float] = None
    policy: Optional[str] = None
    shares_lending_pct: Optional[float] = None
    max_lending_limit_pct: Optional[float] = None
    underlying_holdings: List[ETFUnderlyingAsset] = Field(default_factory=list)
    flow_history_30d: List[ETFFlowPoint] = Field(default_factory=list)
    drawdown: Optional[ETFDrawdownResponse] = None
