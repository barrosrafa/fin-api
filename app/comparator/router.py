from typing import List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/comparator", tags=["Comparator"])


class ComparatorRequest(BaseModel):
    tickers: List[str]
    timeframe: str = "12M"  # 1M, 6M, 12M, 36M, 5Y


class NormalizedSeriesPoint(BaseModel):
    date: str
    values: Dict[str, float]  # ticker -> base 100 normalized value


class AssetComparisonMetrics(BaseModel):
    ticker: str
    price: float
    change_12m: float
    dy_pct: float
    pvp: float
    pl: float
    volatility_pct: float
    sharpe: float


class ComparatorResponse(BaseModel):
    tickers: List[str]
    metrics: List[AssetComparisonMetrics] = Field(default_factory=list)
    series: List[NormalizedSeriesPoint] = Field(default_factory=list)


@router.post("/compare", response_model=ComparatorResponse)
async def compare_assets(request: ComparatorRequest):
    tickers = [t.upper() for t in request.tickers]
    metrics = []
    for t in tickers:
        metrics.append(
            AssetComparisonMetrics(
                ticker=t,
                price=38.45 if t == "PETR4" else 62.10 if t == "VALE3" else 162.50,
                change_12m=24.3 if t == "PETR4" else -8.4 if t == "VALE3" else 12.8,
                dy_pct=14.8 if t == "PETR4" else 9.2 if t == "VALE3" else 8.75,
                pvp=1.15 if t == "PETR4" else 1.38 if t == "VALE3" else 0.98,
                pl=4.8 if t == "PETR4" else 5.9 if t == "VALE3" else 11.2,
                volatility_pct=26.4 if t == "PETR4" else 28.5 if t == "VALE3" else 12.1,
                sharpe=1.24 if t == "PETR4" else 0.45 if t == "VALE3" else 1.58,
            )
        )

    # Base 100 performance series
    dates = ["2025-10-01", "2026-01-01", "2026-04-01", "2026-07-01", "2026-10-26"]
    series = []
    base_values = {
        "PETR4": [100.0, 108.5, 114.2, 119.8, 124.3],
        "VALE3": [100.0, 96.2, 92.4, 94.0, 91.6],
        "HGLG11": [100.0, 102.5, 106.1, 109.4, 112.8],
    }
    for idx, d in enumerate(dates):
        pt_vals = {}
        for t in tickers:
            pt_vals[t] = base_values.get(t, [100.0 + idx * 2.5] * 5)[idx]
        series.append(NormalizedSeriesPoint(date=d, values=pt_vals))

    return ComparatorResponse(tickers=tickers, metrics=metrics, series=series)
