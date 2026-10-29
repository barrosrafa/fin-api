from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.brokers.schemas import BrokerResponse, BrokerItem, BrokerCosts, BrokerRatings


class BrokerService:
    async def get_brokers(self, db_session: AsyncSession) -> BrokerResponse:
        stmt = text(
            """
            SELECT id_instituicao, nome_instituicao, cnpj,
                   COALESCE(taxa_corretagem_acoes, 0.0) as taxa_acoes,
                   COALESCE(taxa_corretagem_fiis, 0.0) as taxa_fiis,
                   COALESCE(taxa_corretagem_opcoes, 0.0) as taxa_opcoes,
                   COALESCE(custodia_mensal, 0.0) as custodia,
                   COALESCE(spread_cambial_ptax_pct, 0.0) as spread_fx,
                   COALESCE(plataformas_suportadas, ARRAY['Home Broker']::TEXT[]) as plataformas,
                   COALESCE(is_internacional, FALSE) as is_intl,
                   COALESCE(nota_geral, 4.5) as nota,
                   COALESCE(total_avaliacoes, 100) as reviews
            FROM core.instituicao_financeira
            WHERE tipo = 'CORRETORA'
            ORDER BY nota_geral DESC NULLS LAST;
            """
        )
        res = await db_session.execute(stmt)
        rows = res.mappings().all()

        items = [
            BrokerItem(
                id=r["id_instituicao"],
                nome=r["nome_instituicao"],
                cnpj=r["cnpj"],
                is_internacional=bool(r["is_intl"]),
                costs=BrokerCosts(
                    taxa_acoes=float(r["taxa_acoes"]),
                    taxa_fiis=float(r["taxa_fiis"]),
                    taxa_opcoes=float(r["taxa_opcoes"]),
                    custodia_mensal=float(r["custodia"]),
                    spread_cambial_ptax_pct=float(r["spread_fx"]),
                ),
                ratings=BrokerRatings(
                    nota_geral=float(r["nota"]),
                    total_avaliacoes=int(r["reviews"]),
                ),
                plataformas_suportadas=r["plataformas"] or ["Home Broker"],
            )
            for r in rows
        ]
        return BrokerResponse(total=len(items), items=items)
