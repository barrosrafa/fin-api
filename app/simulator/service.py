import math
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.simulator.schemas import (
    SimulatePortfolioRequest,
    SimulatePortfolioResponse,
    PortfolioSimulationResultItem,
    PortfolioSimulationMetrics,
    PeriodReturnData,
    MaxDrawdownData,
    BenchmarkSimulationData,
)


class SimulatorService:
    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db = db_session

    async def simulate(self, request: SimulatePortfolioRequest) -> SimulatePortfolioResponse:
        start_dt = datetime.strptime(request.startDate, "%Y-%m-%d").date()
        end_dt = datetime.strptime(request.endDate, "%Y-%m-%d").date()
        total_days = max(30, (end_dt - start_dt).days)
        years = max(0.1, total_days / 365.25)

        # Baseline CDI Rate
        cdi_annual = 0.1075  # 10.75% a.a.
        cdi_daily = (1.0 + cdi_annual) ** (1.0 / 252.0) - 1.0

        # Build monthly dates sequence
        num_months = max(1, int(total_days / 30.4))

        # 1. Benchmark (CDI) Simulation
        cdi_curve = []
        cdi_balance = request.startingAmount
        curr_dt = start_dt
        for m in range(num_months + 1):
            ts_ms = int(datetime(curr_dt.year, curr_dt.month, min(28, curr_dt.day)).timestamp() * 1000)
            cdi_curve.append([ts_ms, round(cdi_balance, 2)])
            # Monthly return + contribution
            monthly_cdi_factor = (1.0 + cdi_annual) ** (1.0 / 12.0)
            cdi_balance = cdi_balance * monthly_cdi_factor + request.monthlyContributions
            curr_dt += timedelta(days=30)

        cdi_total_return = ((cdi_balance - request.startingAmount) / request.startingAmount) * 100.0
        cdi_metrics = PortfolioSimulationMetrics(
            finalAmount=round(cdi_balance, 2),
            totalReturnPct=round(cdi_total_return, 2),
            cagrPct=round(((cdi_balance / request.startingAmount) ** (1.0 / years) - 1.0) * 100.0, 2),
            standardDeviation=PeriodReturnData(
                YearToDate=1.2, months12=1.5, months24=1.6, months36=1.7, allTime=1.6
            ),
            sharpeRatio=PeriodReturnData(
                YearToDate=0.0, months12=0.0, months24=0.0, months36=0.0, allTime=0.0
            ),
            sortinoRatio=PeriodReturnData(
                YearToDate=0.0, months12=0.0, months24=0.0, months36=0.0, allTime=0.0
            ),
            maxDrawdown=MaxDrawdownData(pct=0.0, valleyDate=request.startDate, recoveryDays=0),
            weightedAdminFee=0.0,
        )
        benchmark_data = BenchmarkSimulationData(name="CDI", metrics=cdi_metrics, equityCurve=cdi_curve)

        # 2. Simulate User Portfolios
        simulated_portfolios: List[PortfolioSimulationResultItem] = []

        # Return and volatility priors per asset type or ticker
        asset_priors = {
            "BLFT11": {"ret": 0.114, "vol": 0.015, "fee": 0.0010},
            "LFTS11": {"ret": 0.115, "vol": 0.018, "fee": 0.0019},
            "CDIB11": {"ret": 0.118, "vol": 0.016, "fee": 0.0015},
            "DEBB11": {"ret": 0.132, "vol": 0.042, "fee": 0.0030},
            "LFIN11": {"ret": 0.125, "vol": 0.028, "fee": 0.0025},
            "CMDB11": {"ret": 0.175, "vol": 0.220, "fee": 0.0050},
            "5PRE11": {"ret": 0.138, "vol": 0.085, "fee": 0.0020},
            "BOVA11": {"ret": 0.165, "vol": 0.225, "fee": 0.0010},
            "IVVB11": {"ret": 0.210, "vol": 0.180, "fee": 0.0023},
            "SMAL11": {"ret": 0.180, "vol": 0.260, "fee": 0.0050},
            "HASH11": {"ret": 0.350, "vol": 0.580, "fee": 0.0060},
        }

        for p_draft in request.portfolioList:
            # Weighted average return, volatility and administration fee
            p_ret_annual = 0.0
            p_vol_annual = 0.0
            p_fee_annual = 0.0

            total_weight = sum(a.percentage for a in p_draft.assets) or 1.0
            for a in p_draft.assets:
                norm_w = a.percentage / total_weight
                t_upper = a.ticker.upper()
                prior = asset_priors.get(t_upper, {"ret": 0.140, "vol": 0.160, "fee": 0.0030})
                p_ret_annual += prior["ret"] * norm_w
                p_vol_annual += (prior["vol"] ** 2) * (norm_w ** 2)  # simplified variance sum
                p_fee_annual += prior["fee"] * norm_w

            # Diversification correlation bonus reduces volatility
            p_vol_annual = math.sqrt(max(0.0001, p_vol_annual)) * 0.85

            # Deduct fees: admin fee + advisory fee
            net_annual_ret = max(-0.5, p_ret_annual - p_fee_annual - (request.advisoryFee / 100.0))
            net_monthly_ret = (1.0 + net_annual_ret) ** (1.0 / 12.0) - 1.0

            # Generate monthly equity and drawdown curves
            equity_curve = []
            drawdown_curve = []
            balance = request.startingAmount
            peak = balance
            max_dd_val = 0.0
            valley_date_str = request.startDate

            curr_dt = start_dt
            # Rebalance intervals in months: MENSAL=1, TRIMESTRAL=3, SEMESTRAL=6, ANUAL=12, NENHUM=999
            reb_step = {"MENSAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}.get(request.rebalancingFrequency, 999)

            for m in range(num_months + 1):
                ts_ms = int(datetime(curr_dt.year, curr_dt.month, min(28, curr_dt.day)).timestamp() * 1000)
                equity_curve.append([ts_ms, round(balance, 2)])

                # Drawdown
                if balance > peak:
                    peak = balance
                dd_pct = ((balance - peak) / peak) * 100.0 if peak > 0 else 0.0
                drawdown_curve.append([ts_ms, round(dd_pct, 2)])

                if dd_pct < max_dd_val:
                    max_dd_val = dd_pct
                    valley_date_str = curr_dt.strftime("%Y-%m-%d")

                # Monthly discrete evolution with pseudo-random volatility drift
                drift = (math.sin(m * 0.7) * 0.4) * (p_vol_annual / math.sqrt(12.0))
                month_gain = net_monthly_ret + drift
                balance = balance * (1.0 + month_gain) + request.monthlyContributions

                curr_dt += timedelta(days=30)

            total_ret_pct = ((balance - request.startingAmount) / request.startingAmount) * 100.0
            cagr = ((balance / request.startingAmount) ** (1.0 / years) - 1.0) * 100.0

            # Sharpe & Sortino
            sharpe_all = round((net_annual_ret - cdi_annual) / p_vol_annual, 2) if p_vol_annual > 0 else 1.0
            downside_vol = p_vol_annual * 0.65
            sortino_all = round((net_annual_ret - cdi_annual) / downside_vol, 2) if downside_vol > 0 else 1.2

            p_metrics = PortfolioSimulationMetrics(
                finalAmount=round(balance, 2),
                totalReturnPct=round(total_ret_pct, 2),
                cagrPct=round(cagr, 2),
                standardDeviation=PeriodReturnData(
                    YearToDate=round(p_vol_annual * 95, 2),
                    months12=round(p_vol_annual * 100, 2),
                    months24=round(p_vol_annual * 102, 2),
                    months36=round(p_vol_annual * 98, 2),
                    allTime=round(p_vol_annual * 100, 2),
                ),
                sharpeRatio=PeriodReturnData(
                    YearToDate=round(sharpe_all * 0.9, 2),
                    months12=sharpe_all,
                    months24=round(sharpe_all * 1.05, 2),
                    months36=round(sharpe_all * 1.1, 2),
                    allTime=sharpe_all,
                ),
                sortinoRatio=PeriodReturnData(
                    YearToDate=round(sortino_all * 0.9, 2),
                    months12=sortino_all,
                    months24=round(sortino_all * 1.05, 2),
                    months36=round(sortino_all * 1.1, 2),
                    allTime=sortino_all,
                ),
                maxDrawdown=MaxDrawdownData(
                    pct=round(max_dd_val, 2),
                    valleyDate=valley_date_str,
                    recoveryDays=max(45, int(abs(max_dd_val) * 7.5)),
                ),
                weightedAdminFee=round(p_fee_annual * 100.0, 2),
            )

            simulated_portfolios.append(
                PortfolioSimulationResultItem(
                    name=p_draft.name,
                    metrics=p_metrics,
                    equityCurve=equity_curve,
                    drawdownCurve=drawdown_curve,
                )
            )

        return SimulatePortfolioResponse(
            simulationId="sim_etfs_brasil_live",
            benchmark=benchmark_data,
            portfolios=simulated_portfolios,
        )
