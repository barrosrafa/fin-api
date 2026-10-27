from app.derivatives.schemas import (
    DerivativesResponse,
    OptionContract,
    StockBorrowingBTC,
    BuybackProgram,
)


class DerivativesService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_options_chain(self, ticker: str) -> DerivativesResponse:
        t = ticker.upper()
        spot_price = 38.45 if t == "PETR4" else 62.10

        calls = [
            OptionContract(
                symbol=f"{t[:4]}K360",
                type="CALL",
                style="AMERICANA",
                strike=36.00,
                expiration_date="2026-11-20",
                moneyness="ITM",
                last_price=3.10,
                implied_volatility_pct=26.4,
                delta=0.78,
                gamma=0.08,
                theta=-0.04,
                vega=0.09,
                rho=0.02,
                open_interest=1450000,
                volume_24h=4850000.0,
            ),
            OptionContract(
                symbol=f"{t[:4]}K380",
                type="CALL",
                style="AMERICANA",
                strike=38.00,
                expiration_date="2026-11-20",
                moneyness="ATM",
                last_price=1.65,
                implied_volatility_pct=28.1,
                delta=0.52,
                gamma=0.12,
                theta=-0.06,
                vega=0.11,
                rho=0.015,
                open_interest=3820000,
                volume_24h=12400000.0,
            ),
            OptionContract(
                symbol=f"{t[:4]}K400",
                type="CALL",
                style="AMERICANA",
                strike=40.00,
                expiration_date="2026-11-20",
                moneyness="OTM",
                last_price=0.68,
                implied_volatility_pct=31.2,
                delta=0.28,
                gamma=0.09,
                theta=-0.05,
                vega=0.08,
                rho=0.01,
                open_interest=2150000,
                volume_24h=3120000.0,
            ),
        ]

        puts = [
            OptionContract(
                symbol=f"{t[:4]}W380",
                type="PUT",
                style="EUROPEIA",
                strike=38.00,
                expiration_date="2026-11-20",
                moneyness="ATM",
                last_price=1.42,
                implied_volatility_pct=27.9,
                delta=-0.48,
                gamma=0.12,
                theta=-0.05,
                vega=0.11,
                rho=-0.015,
                open_interest=1890000,
                volume_24h=5800000.0,
            ),
        ]

        btc = StockBorrowingBTC(
            ticker=t,
            borrower_rate_avg=2.85,
            borrower_rate_min=1.90,
            borrower_rate_max=4.20,
            lender_rate_avg=2.40,
            active_contracts=4520,
            shares_borrowed_qty=38_500_000,
            financial_volume=1_480_325_000.0,
            free_float_borrowed_pct=2.94,
        )

        buybacks = [
            BuybackProgram(
                program_id=f"RECOMPRA-{t}-2026",
                approval_date="2026-03-15",
                expiration_date="2027-03-15",
                shares_authorized=50_000_000,
                shares_acquired=32_400_000,
                shares_in_treasury=32_400_000,
                execution_pct=64.8,
            )
        ]

        return DerivativesResponse(
            underlying=t,
            spot_price=spot_price,
            calls=calls,
            puts=puts,
            btc_borrowing=btc,
            buybacks=buybacks,
        )
