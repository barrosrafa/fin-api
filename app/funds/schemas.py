from typing import List
from pydantic import BaseModel, Field


class QuantRiskWindow(BaseModel):
    timeframe: str  # 1M, 3M, 6M, 12M, 24M, 36M, 60M, YTD
    accumulated_return_pct: float
    volatility_pct: float
    sharpe: float
    sortino: float
    treynor: float
    jensen_alpha: float
    beta: float
    tracking_error: float
    information_ratio: float
    max_drawdown_pct: float
    recovery_days: int
    positive_months_pct: float


class FundHoldingCDA(BaseModel):
    asset_name: str
    asset_type: str  # ACAO, TITULO_PUBLICO, DEBENTURE, DERIVATIVO, CAIXA
    identifier: str
    weight_pct: float
    financial_value: float


class FundRiskMatrixResponse(BaseModel):
    fund_id: str
    name: str
    cnpj: str
    category_cvm175: str
    benchmark: str
    net_worth: float
    matrix: List[QuantRiskWindow] = Field(default_factory=list)
    cda_holdings: List[FundHoldingCDA] = Field(default_factory=list)
