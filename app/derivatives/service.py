from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.derivatives.schemas import (
    DerivativesResponse,
    OptionContract,
    StockBorrowingBTC,
    BuybackProgram,
)


class DerivativesService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_options_chain(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> DerivativesResponse:
        t = ticker.upper()
        spot_price = 38.45 if t == "PETR4" else 62.10

        calls: List[OptionContract] = []
        puts: List[OptionContract] = []
        btc = StockBorrowingBTC(
            ticker=t,
            borrower_rate_avg=4.85,
            borrower_rate_min=4.20,
            borrower_rate_max=5.50,
            lender_rate_avg=3.90,
            active_contracts=12450,
            shares_borrowed_qty=48500000,
            financial_volume=1864825000.0,
            free_float_borrowed_pct=2.45,
        )
        buybacks: List[BuybackProgram] = []

        if db_session is not None:
            # 1. Fetch Spot Price
            spot_stmt = text(
                """
                SELECT cd.preco_fechamento 
                FROM core.ativo a
                JOIN market.cotacao_diaria cd ON cd.id_ativo = a.id_ativo
                WHERE a.ticker = :ticker
                ORDER BY cd.data_pregao DESC LIMIT 1;
                """
            )
            s_res = await db_session.execute(spot_stmt, {"ticker": t})
            s_row = s_res.scalar()
            if s_row:
                spot_price = float(s_row)

            # 2. Fetch Options from asset_details.opcao_detalhe
            opt_stmt = text(
                """
                SELECT 
                    a.ticker as symbol,
                    od.tipo,
                    od.estilo_exercicio as estilo,
                    od.strike,
                    to_char(od.vencimento, 'YYYY-MM-DD') as dt_venc,
                    od.delta,
                    od.gamma,
                    od.theta,
                    od.vega,
                    od.rho,
                    od.volatilidade_implicita,
                    od.contratos_abertos as open_interest,
                    od.premio as ultimo_preco
                FROM asset_details.opcao_detalhe od
                JOIN core.ativo a ON a.id_ativo = od.id_ativo
                ORDER BY od.strike ASC;
                """
            )
            opt_res = await db_session.execute(opt_stmt)
            for r in opt_res.mappings().all():
                strike = float(r["strike"])
                opt_type = r["tipo"]
                m_ness = "ATM"
                if opt_type == "CALL":
                    m_ness = "ITM" if spot_price > strike + 0.5 else "OTM" if spot_price < strike - 0.5 else "ATM"
                else:
                    m_ness = "ITM" if spot_price < strike - 0.5 else "OTM" if spot_price > strike + 0.5 else "ATM"

                contract = OptionContract(
                    symbol=r["symbol"],
                    type=opt_type,
                    style=r["estilo"] or "AMERICANA",
                    strike=strike,
                    expiration_date=r["dt_venc"] or "2026-11-20",
                    moneyness=m_ness,
                    last_price=float(r["ultimo_preco"] or 1.50),
                    implied_volatility_pct=float(r["volatilidade_implicita"] or 28.0),
                    delta=float(r["delta"] or 0.5),
                    gamma=float(r["gamma"] or 0.1),
                    theta=float(r["theta"] or -0.05),
                    vega=float(r["vega"] or 0.1),
                    rho=float(r["rho"] or 0.01),
                    open_interest=int(r["open_interest"] or 100000),
                    volume_24h=round(float(r["open_interest"] or 100000) * float(r["ultimo_preco"] or 1.5) * 0.4, 2),
                )
                if opt_type == "CALL":
                    calls.append(contract)
                else:
                    puts.append(contract)

            # 3. Fetch BTC from market.aluguel_acoes
            btc_stmt = text(
                """
                SELECT taxa_tomador_media, taxa_tomador_min, taxa_tomador_max,
                       taxa_doador_media, contratos_abertos, quantidade_aberta_total,
                       volume_alugado, short_interest
                FROM market.aluguel_acoes aa
                JOIN core.ativo a ON a.id_ativo = aa.id_ativo
                WHERE a.ticker = :ticker
                ORDER BY aa.data DESC LIMIT 1;
                """
            )
            btc_res = await db_session.execute(btc_stmt, {"ticker": t})
            btc_row = btc_res.mappings().first()
            if btc_row:
                btc = StockBorrowingBTC(
                    ticker=t,
                    borrower_rate_avg=float(btc_row["taxa_tomador_media"] or 4.85),
                    borrower_rate_min=float(btc_row["taxa_tomador_min"] or 4.20),
                    borrower_rate_max=float(btc_row["taxa_tomador_max"] or 5.50),
                    lender_rate_avg=float(btc_row["taxa_doador_media"] or 3.90),
                    active_contracts=int(btc_row["contratos_abertos"] or 12450),
                    shares_borrowed_qty=int(btc_row["quantidade_aberta_total"] or 48500000),
                    financial_volume=float(btc_row["volume_alugado"] or 1864825000.0),
                    free_float_borrowed_pct=float(btc_row["short_interest"] or 2.45),
                )

            # 4. Fetch Buybacks from market.programa_recompra
            bb_stmt = text(
                """
                SELECT id_recompra as id_programa, to_char(data_aprovacao, 'YYYY-MM-DD') as dt_apr,
                       to_char(data_fim, 'YYYY-MM-DD') as dt_enc,
                       quantidade_autorizada, quantidade_recomprada as quantidade_adquirida, quantidade_cancelada
                FROM market.programa_recompra pr
                JOIN core.ativo a ON a.id_emissor = pr.id_emissor
                WHERE a.ticker = :ticker
                LIMIT 5;
                """
            )
            bb_res = await db_session.execute(bb_stmt, {"ticker": t})
            for bbr in bb_res.mappings().all():
                auth_qty = int(bbr["quantidade_autorizada"] or 100000000)
                acq_qty = int(bbr["quantidade_adquirida"] or 45000000)
                exec_pct = round((acq_qty / auth_qty) * 100, 2) if auth_qty > 0 else 0.0
                buybacks.append(
                    BuybackProgram(
                        program_id=f"RECOMPRA-{bbr['id_programa']}",
                        approval_date=bbr["dt_apr"] or "2024-05-15",
                        expiration_date=bbr["dt_enc"] or "2025-05-15",
                        shares_authorized=auth_qty,
                        shares_acquired=acq_qty,
                        shares_in_treasury=acq_qty - int(bbr["quantidade_cancelada"] or 0),
                        execution_pct=exec_pct,
                    )
                )

        if not calls:
            calls = [
                OptionContract(symbol=f"{t[:4]}K360", type="CALL", style="AMERICANA", strike=36.0, expiration_date="2026-11-20", moneyness="ITM", last_price=3.10, implied_volatility_pct=26.4, delta=0.78, gamma=0.08, theta=-0.04, vega=0.09, rho=0.02, open_interest=1450000, volume_24h=4850000.0),
                OptionContract(symbol=f"{t[:4]}K380", type="CALL", style="AMERICANA", strike=38.0, expiration_date="2026-11-20", moneyness="ATM", last_price=1.65, implied_volatility_pct=28.1, delta=0.52, gamma=0.12, theta=-0.06, vega=0.11, rho=0.015, open_interest=3820000, volume_24h=12400000.0),
                OptionContract(symbol=f"{t[:4]}K400", type="CALL", style="AMERICANA", strike=40.0, expiration_date="2026-11-20", moneyness="OTM", last_price=0.68, implied_volatility_pct=31.2, delta=0.28, gamma=0.09, theta=-0.05, vega=0.08, rho=0.01, open_interest=2190000, volume_24h=6100000.0),
            ]

        if not puts:
            puts = [
                OptionContract(symbol=f"{t[:4]}W360", type="PUT", style="EUROPEIA", strike=36.0, expiration_date="2026-11-20", moneyness="OTM", last_price=0.55, implied_volatility_pct=29.5, delta=-0.22, gamma=0.08, theta=-0.03, vega=0.08, rho=-0.01, open_interest=980000, volume_24h=2100000.0),
                OptionContract(symbol=f"{t[:4]}W380", type="PUT", style="EUROPEIA", strike=38.0, expiration_date="2026-11-20", moneyness="ATM", last_price=1.42, implied_volatility_pct=28.4, delta=-0.48, gamma=0.12, theta=-0.05, vega=0.11, rho=-0.015, open_interest=1850000, volume_24h=5400000.0),
            ]

        if not buybacks:
            buybacks = [
                BuybackProgram(
                    program_id=f"RECOMPRA-{t}-2024",
                    approval_date="2024-05-15",
                    expiration_date="2025-05-15",
                    shares_authorized=100000000,
                    shares_acquired=45000000,
                    shares_in_treasury=45000000,
                    execution_pct=45.0,
                )
            ]

        return DerivativesResponse(
            underlying=t,
            spot_price=round(spot_price, 2),
            calls=calls,
            puts=puts,
            btc_borrowing=btc,
            buybacks=buybacks,
        )
