import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.simulator.schemas import SimulatePortfolioRequest, SimulatePortfolioResponse, PortfolioDraft, PortfolioAssetAllocation
from app.simulator.service import SimulatorService

router = APIRouter(tags=["Simulator"])


def get_simulator_service(db: AsyncSession = Depends(get_async_session)) -> SimulatorService:
    return SimulatorService(db_session=db)


@router.post("/simulate-portfolio", response_model=SimulatePortfolioResponse)
async def simulate_portfolio_post(
    request: SimulatePortfolioRequest,
    service: SimulatorService = Depends(get_simulator_service),
):
    """
    Simulates discrete portfolio evolution with rebalancing, contributions,
    annual Sharpe, Sortino, max drawdown, and equity curves.
    """
    return await service.simulate(request)


@router.get("/simulate-portfolio", response_model=SimulatePortfolioResponse)
async def simulate_portfolio_get(
    startDate: str = Query("2024-01-02"),
    endDate: str = Query("2026-10-26"),
    startingAmount: float = Query(50000.0),
    monthlyContributions: float = Query(0.0),
    rebalancingFrequency: str = Query("TRIMESTRAL"),
    advisoryFee: float = Query(0.0),
    portfolioList: str = Query("[]"),  # JSON string of drafts
    service: SimulatorService = Depends(get_simulator_service),
):
    """
    GET endpoint matching Next.js query parameter serialization format.
    """
    try:
        parsed_list = json.loads(portfolioList)
        portfolios = []
        for p in parsed_list:
            assets = [
                PortfolioAssetAllocation(
                    ticker=a.get("ticker", ""),
                    assetsType=a.get("assetsType", "etfs"),
                    percentage=float(a.get("percentage", 0.0)),
                )
                for a in p.get("assets", [])
            ]
            portfolios.append(PortfolioDraft(name=p.get("name", "Portfólio"), assets=assets))
    except Exception:
        portfolios = []

    if not portfolios:
        # Default portfolio if empty or invalid
        portfolios = [
            PortfolioDraft(
                name="Conservador",
                assets=[
                    PortfolioAssetAllocation(ticker="BLFT11", percentage=0.5),
                    PortfolioAssetAllocation(ticker="DEBB11", percentage=0.5),
                ],
            )
        ]

    req = SimulatePortfolioRequest(
        startDate=startDate,
        endDate=endDate,
        startingAmount=startingAmount,
        monthlyContributions=monthlyContributions,
        rebalancingFrequency=rebalancingFrequency,
        advisoryFee=advisoryFee,
        portfolioList=portfolios,
    )
    return await service.simulate(req)
