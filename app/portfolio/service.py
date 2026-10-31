import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from app.calculations.money import decimal_value, money
from app.calculations.pnl import Position
from typing import List, Optional, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.portfolio.schemas import (
    WalletCreate,
    WalletResponse,
    PositionResponse,
    PortfolioSummaryResponse,
)
from app.core.exceptions import ResourceNotFoundException
from app.core.logging import logger


class PortfolioService:
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client

    @staticmethod
    def compute_new_average_price(
        current_qty: float,
        current_avg_price: float,
        new_qty: float,
        new_price: float,
    ) -> Decimal:
        qty = decimal_value(current_qty)
        avg = decimal_value(current_avg_price)
        with localcontext() as context:
            context.prec = 38
            return Position(qty, qty * avg).buy(new_qty, new_price).average_price

    async def create_wallet(
        self,
        user_id: str,
        data: WalletCreate,
        db_session: AsyncSession,
    ) -> WalletResponse:
        stmt = text(
            """
            INSERT INTO core.carteira (id_usuario, nome_carteira, data_criacao)
            VALUES (
                (SELECT id_usuario FROM core.usuario WHERE id_externo = :user_id OR email = :user_id OR id_usuario::text = :user_id LIMIT 1),
                :nome, NOW()
            )
            RETURNING id_carteira, nome_carteira, data_criacao
            """
        )
        res = await db_session.execute(
            stmt,
            {"user_id": user_id, "nome": data.nome},
        )
        row = res.mappings().first()
        await db_session.commit()
        return WalletResponse(
            id=str(row["id_carteira"]),
            nome=row["nome_carteira"],
            descricao=data.descricao,
            padrao=data.padrao,
            criado_em=row.get("data_criacao"),
        )

    async def list_wallets(
        self,
        user_id: str,
        db_session: AsyncSession,
    ) -> List[WalletResponse]:
        stmt = text(
            """
            SELECT c.id_carteira, c.nome_carteira, c.data_criacao
            FROM core.carteira c
            JOIN core.usuario u ON u.id_usuario = c.id_usuario
            WHERE u.id_externo = :user_id OR u.email = :user_id OR u.id_usuario::text = :user_id
            ORDER BY c.data_criacao DESC
            """
        )
        res = await db_session.execute(stmt, {"user_id": user_id})
        rows = res.mappings().all()
        return [
            WalletResponse(
                id=str(r["id_carteira"]),
                nome=r["nome_carteira"],
                descricao=None,
                padrao=False,
                criado_em=r.get("data_criacao"),
            )
            for r in rows
        ]

    async def get_portfolio_summary(
        self,
        wallet_id: str,
        user_id: str,
        db_session: AsyncSession,
    ) -> PortfolioSummaryResponse:
        # IDOR Guard: verify wallet belongs to current user
        check_stmt = text(
            """
            SELECT c.id_carteira
            FROM core.carteira c
            JOIN core.usuario u ON u.id_usuario = c.id_usuario
            WHERE c.id_carteira = CAST(:wallet_id AS UUID)
              AND (u.id_externo = :user_id OR u.email = :user_id OR u.id_usuario::text = :user_id)
            """
        )
        check_res = await db_session.execute(check_stmt, {"wallet_id": wallet_id, "user_id": user_id})
        if not check_res.scalar_one_or_none():
            raise ResourceNotFoundException("Wallet", str(wallet_id))

        stmt = text(
            """
            SELECT a.ticker, a.tipo_ativo, p.quantidade_total AS quantidade, p.preco_medio_ponderado AS preco_medio
            FROM core.posicao_custodia p
            JOIN core.ativo a ON a.id_ativo = p.id_ativo
            WHERE p.id_carteira = CAST(:wallet_id AS UUID) AND p.quantidade_total > 0
            """
        )
        res = await db_session.execute(stmt, {"wallet_id": wallet_id})
        rows = res.mappings().all()

        with localcontext() as context:
            context.prec = 50
            total_cost = Decimal(0)
            covered_equity = Decimal(0)
            priced_positions = 0
            positions = []
            allocation: Dict[str, Decimal] = {}

            for r in rows:
                ticker = r["ticker"]
                qty = decimal_value(r["quantidade"], positive=True)
                avg_price = decimal_value(r["preco_medio"])
                cost = qty * avg_price
                total_cost += cost
                price, as_of, source = None, None, None
                status = "missing"
                if self.redis is not None:
                    try:
                        cached = await self.redis.get(f"quote:{ticker}")
                        if cached:
                            quote = json.loads(cached, parse_float=Decimal)
                            price = decimal_value(quote.get("price"), positive=True)
                            source = quote.get("source")
                            source = source.strip() if isinstance(source, str) else None
                            fact_time = quote.get("as_of")
                            as_of = datetime.fromisoformat(fact_time.replace("Z", "+00:00")) if fact_time else None
                            age = (datetime.now(timezone.utc) - as_of).total_seconds() if as_of and as_of.tzinfo else None
                            # Price age is measured from the fact time, never from its collection time.
                            # This conservative policy is not an exchange-session calendar.
                            status = "valid" if age is not None and 0 <= age <= 300 and source else "stale"
                    except (ValueError, TypeError, AttributeError):
                        price, as_of, source, status = None, None, None, "missing"
                    except aioredis.RedisError:
                        logger.warning("Portfolio quote cache unavailable")
                equity = qty * price if price is not None and status == "valid" else None
                pl = equity - cost if equity is not None else None
                asset_type = str(r["tipo_ativo"])
                if equity is not None:
                    priced_positions += 1
                    covered_equity += equity
                    allocation[asset_type] = allocation.get(asset_type, Decimal(0)) + equity
                positions.append(PositionResponse(
                    ticker=ticker, tipo_ativo=asset_type, quantidade=qty, preco_medio=avg_price,
                    preco_atual=price, price_status=status, price_as_of=as_of, price_source=source,
                    valor_total_custo=money(cost), valor_total_atual=money(equity) if equity is not None else None,
                    lucro_prejuizo=money(pl) if pl is not None else None,
                    lucro_prejuizo_pct=money(pl / cost * 100) if pl is not None and cost > 0 else None,
                ))
            complete = priced_positions == len(positions)
            # Allocation weights are portfolio weights only when the entire portfolio is priced.
            if complete and covered_equity > 0:
                for position in positions:
                    position.peso_pct = money(position.valor_total_atual / covered_equity * 100)
                allocation = {key: money(value / covered_equity * 100) for key, value in allocation.items()}
            else:
                allocation = {}
            profit_loss = covered_equity - total_cost if complete else None
            return PortfolioSummaryResponse(
                wallet_id=str(wallet_id), total_cost=money(total_cost),
                total_equity=money(covered_equity) if complete else None,
                profit_loss=money(profit_loss) if profit_loss is not None else None,
                profit_loss_pct=money(profit_loss / total_cost * 100) if complete and total_cost > 0 else None,
                covered_equity=money(covered_equity), priced_positions=priced_positions, total_positions=len(positions),
                price_coverage_pct=money(Decimal(priced_positions) / len(positions) * 100) if positions else Decimal(100),
                positions=positions, allocation_by_type=allocation,
            )
