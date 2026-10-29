from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class PortfolioAssetAllocation(BaseModel):
    ticker: str
    assetsType: Optional[str] = "etfs"
    percentage: float  # 0.0 to 1.0


class PortfolioDraft(BaseModel):
    name: str  # Ex: "Conservador", "Moderado", "Arrojado"
    assets: List[PortfolioAssetAllocation]


class SimulatePortfolioRequest(BaseModel):
    startDate: str = "2024-01-02"
    endDate: str = "2026-10-26"
    startingAmount: float = 50000.0
    monthlyContributions: float = 0.0
    rebalancingFrequency: str = "TRIMESTRAL"  # NENHUM, MENSAL, TRIMESTRAL, SEMESTRAL, ANUAL
    advisoryFee: float = 0.0
    portfolioList: List[PortfolioDraft] = Field(default_factory=list)


class PeriodReturnData(BaseModel):
    YearToDate: Optional[float] = None
    months12: Optional[float] = None
    months24: Optional[float] = None
    months36: Optional[float] = None
    allTime: float = 0.0


class MaxDrawdownData(BaseModel):
    pct: float
    valleyDate: Optional[str] = None
    recoveryDays: int = 0


class PortfolioSimulationMetrics(BaseModel):
    finalAmount: float
    totalReturnPct: float
    cagrPct: float
    standardDeviation: PeriodReturnData
    sharpeRatio: PeriodReturnData
    sortinoRatio: PeriodReturnData
    maxDrawdown: MaxDrawdownData
    weightedAdminFee: float


class PortfolioSimulationResultItem(BaseModel):
    name: str
    metrics: PortfolioSimulationMetrics
    equityCurve: List[List[float]] = Field(default_factory=list)  # [[timestamp_ms, value], ...]
    drawdownCurve: List[List[float]] = Field(default_factory=list)  # [[timestamp_ms, pct], ...]


class BenchmarkSimulationData(BaseModel):
    name: str = "CDI"
    metrics: PortfolioSimulationMetrics
    equityCurve: List[List[float]] = Field(default_factory=list)


class SimulatePortfolioResponse(BaseModel):
    assumptions: List[str] = Field(default_factory=list)
    simulationId: Optional[str] = None
    benchmark: BenchmarkSimulationData
    portfolios: List[PortfolioSimulationResultItem] = Field(default_factory=list)
