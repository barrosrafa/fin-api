from typing import List, Optional
from pydantic import BaseModel, Field


class OptionContract(BaseModel):
    symbol: str
    type: str  # CALL, PUT
    style: str  # AMERICANA, EUROPEIA
    strike: float
    expiration_date: str
    moneyness: str  # ITM, ATM, OTM
    last_price: float
    implied_volatility_pct: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    open_interest: int
    volume_24h: float


class StockBorrowingBTC(BaseModel):
    ticker: str
    borrower_rate_avg: float
    borrower_rate_min: float
    borrower_rate_max: float
    lender_rate_avg: float
    active_contracts: int
    shares_borrowed_qty: int
    financial_volume: float
    free_float_borrowed_pct: float


class BuybackProgram(BaseModel):
    program_id: str
    approval_date: str
    expiration_date: str
    shares_authorized: int
    shares_acquired: int
    shares_in_treasury: int
    execution_pct: float


class DerivativesResponse(BaseModel):
    underlying: str
    spot_price: float
    calls: List[OptionContract] = Field(default_factory=list)
    puts: List[OptionContract] = Field(default_factory=list)
    btc_borrowing: StockBorrowingBTC
    buybacks: List[BuybackProgram] = Field(default_factory=list)
