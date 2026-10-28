from typing import List, Optional
from pydantic import BaseModel, Field


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
    max_drawdown_pct: float
    valley_date: Optional[str] = None
    recovery_days: Optional[int] = None
    drawdown_curve: List[List[float]] = Field(default_factory=list)


class ETFDetailResponse(BaseModel):
    ticker: str
    name: str
    benchmark_index: str
    provider: str
    current_price: float
    nav_per_share: Optional[float] = None
    nav_spread_pct: Optional[float] = None  # (price - nav) / nav * 100
    ter_pct: float  # Total Expense Ratio (primary + secondary)
    primary_fee_pct: float
    secondary_fee_pct: float
    policy: str  # ACUMULATIVO, DISTRIBUTIVO
    shares_lending_pct: float  # % loaned out
    max_lending_limit_pct: float = 30.0
    underlying_holdings: List[ETFUnderlyingAsset] = Field(default_factory=list)
    flow_history_30d: List[ETFFlowPoint] = Field(default_factory=list)
    drawdown: Optional[ETFDrawdownResponse] = None
