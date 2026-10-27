import json
from typing import List, Optional, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.portfolio.schemas import (
    WalletCreate,
    WalletResponse,
    TransactionCreate,
    TransactionType,
    PositionResponse,
    PortfolioSummaryResponse,
)
from app.core.exceptions import ResourceNotFoundException, FinApiException
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
    ) -> float:
        if new_qty <= 0:
            return current_avg_price
        total_shares = current_qty + new_qty
        if total_shares <= 0:
            return 0.0
        total_spent = (current_qty * current_avg_price) + (new_qty * new_price)
        return round(total_spent / total_shares, 4)

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
                (SELECT id_usuario FROM core.usuario WHERE id_externo = :user_id OR email = :user_id LIMIT 1),
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
            WHERE u.id_externo = :user_id OR u.email = :user_id
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
              AND (u.id_externo = :user_id OR u.email = :user_id)
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

        total_cost = 0.0
        total_equity = 0.0
        positions = []
        allocation: Dict[str, float] = {}

        for r in rows:
            ticker = r["ticker"]
            qty = float(r["quantidade"])
            avg_price = float(r["preco_medio"])
            cost = qty * avg_price
            total_cost += cost

            current_price = avg_price
            if self.redis is not None:
                cached = await self.redis.get(f"quote:{ticker}")
                if cached:
                    try:
                        q_data = json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
                        current_price = float(q_data.get("price", avg_price))
                    except Exception:
                        pass

            equity = qty * current_price
            total_equity += equity
            pl = equity - cost
            pl_pct = (pl / cost * 100.0) if cost > 0 else 0.0

            asset_type = str(r["tipo_ativo"])
            allocation[asset_type] = allocation.get(asset_type, 0.0) + equity

            positions.append(
                PositionResponse(
                    ticker=ticker,
                    tipo_ativo=asset_type,
                    quantidade=qty,
                    preco_medio=avg_price,
                    preco_atual=current_price,
                    valor_total_custo=round(cost, 2),
                    valor_total_atual=round(equity, 2),
                    lucro_prejuizo=round(pl, 2),
                    lucro_prejuizo_pct=round(pl_pct, 2),
                )
            )

        if total_equity > 0:
            for p in positions:
                p.peso_pct = round(p.valor_total_atual / total_equity * 100.0, 2)
            for k in allocation:
                allocation[k] = round(allocation[k] / total_equity * 100.0, 2)

        profit_loss = total_equity - total_cost
        profit_loss_pct = (profit_loss / total_cost * 100.0) if total_cost > 0 else 0.0

        return PortfolioSummaryResponse(
            wallet_id=str(wallet_id),
            total_cost=round(total_cost, 2),
            total_equity=round(total_equity, 2),
            profit_loss=round(profit_loss, 2),
            profit_loss_pct=round(profit_loss_pct, 2),
            positions=positions,
            allocation_by_type=allocation,
        )
