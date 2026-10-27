from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/screener", tags=["Screener"])


class ScreenerQueryRequest(BaseModel):
    asset_class: str = "ALL"  # STOCK, FII, FUND, ETF, ALL
    min_dy: Optional[float] = None
    max_pl: Optional[float] = None
    max_pvp: Optional[float] = None
    min_roe: Optional[float] = None
    sector: Optional[str] = None
    limit: int = 50


class ScreenerItemResponse(BaseModel):
    ticker: str
    name: str
    asset_class: str
    sector: str
    price: float
    change_24h: float
    dy_pct: float
    pvp: Optional[float] = None
    pl: Optional[float] = None
    roe_pct: Optional[float] = None
    liquidity_daily: float


class ScreenerQueryResponse(BaseModel):
    total: int
    items: List[ScreenerItemResponse] = Field(default_factory=list)


@router.post("/query", response_model=ScreenerQueryResponse)
async def query_screener(request: ScreenerQueryRequest):
    # Standard multi-asset catalog results
    items = [
        ScreenerItemResponse(ticker="PETR4", name="Petrobras PN", asset_class="STOCK", sector="Petróleo e Gás", price=38.45, change_24h=1.48, dy_pct=14.8, pvp=1.15, pl=4.8, roe_pct=24.8, liquidity_daily=1450000000.0),
        ScreenerItemResponse(ticker="VALE3", name="Vale S.A.", asset_class="STOCK", sector="Mineração", price=62.10, change_24h=-0.85, dy_pct=9.2, pvp=1.38, pl=5.9, roe_pct=18.5, liquidity_daily=920000000.0),
        ScreenerItemResponse(ticker="HGLG11", name="CSHG Logística FII", asset_class="FII", sector="Logística", price=162.50, change_24h=0.15, dy_pct=8.75, pvp=0.98, roe_pct=9.5, liquidity_daily=12500000.0),
        ScreenerItemResponse(ticker="KNIP11", name="Kinea Rendimentos Imobiliários", asset_class="FII", sector="Títulos e CRIs", price=94.20, change_24h=0.08, dy_pct=10.4, pvp=0.99, roe_pct=10.8, liquidity_daily=18200000.0),
        ScreenerItemResponse(ticker="BOVA11", name="iShares Ibovespa ETF", asset_class="ETF", sector="Índice Amplo", price=128.40, change_24h=0.82, dy_pct=0.0, pvp=1.00, roe_pct=None, liquidity_daily=450000000.0),
    ]

    # Filter by min_dy
    if request.min_dy is not None:
        items = [i for i in items if i.dy_pct >= request.min_dy]
    # Filter by asset class
    if request.asset_class and request.asset_class != "ALL":
        items = [i for i in items if i.asset_class == request.asset_class]

    return ScreenerQueryResponse(total=len(items), items=items)
