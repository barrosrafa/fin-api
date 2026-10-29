from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.macro.schemas import (
    GovernmentAccountsItem,
    GovernmentAccountsResponse,
    CreditSystemItem,
    CreditSystemResponse,
)


class MacroService:
    @staticmethod
    async def get_government_accounts(
        db: AsyncSession, limit: int = 36
    ) -> GovernmentAccountsResponse:
        stmt = text(
            """
            SELECT 
                data_referencia::text,
                receita_total_bruta,
                transferencias_estados_mun,
                receita_liquida,
                despesa_previdencia,
                despesa_pessoal,
                despesa_total,
                resultado_primario,
                resultado_nominal,
                divida_bruta_pib_pct,
                divida_liquida_pib_pct
            FROM market.contas_publicas_governo
            ORDER BY data_referencia ASC
            LIMIT :limit;
            """
        )
        res = await db.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        items = [
            GovernmentAccountsItem(
                data_referencia=r["data_referencia"],
                receita_total_bruta=float(r["receita_total_bruta"]) if r["receita_total_bruta"] is not None else None,
                transferencias_estados_mun=float(r["transferencias_estados_mun"]) if r["transferencias_estados_mun"] is not None else None,
                receita_liquida=float(r["receita_liquida"]),
                despesa_previdencia=float(r["despesa_previdencia"]) if r["despesa_previdencia"] is not None else None,
                despesa_pessoal=float(r["despesa_pessoal"]) if r["despesa_pessoal"] is not None else None,
                despesa_total=float(r["despesa_total"]),
                resultado_primario=float(r["resultado_primario"]),
                resultado_nominal=float(r["resultado_nominal"]) if r["resultado_nominal"] is not None else None,
                divida_bruta_pib_pct=float(r["divida_bruta_pib_pct"]) if r["divida_bruta_pib_pct"] is not None else None,
                divida_liquida_pib_pct=float(r["divida_liquida_pib_pct"]) if r["divida_liquida_pib_pct"] is not None else None,
            )
            for r in rows
        ]
        return GovernmentAccountsResponse(total_records=len(items), items=items)

    @staticmethod
    async def get_credit_system(
        db: AsyncSession, limit: int = 36
    ) -> CreditSystemResponse:
        stmt = text(
            """
            SELECT 
                data_referencia::text,
                poupanca_captacao_liquida,
                poupanca_saldo_total,
                inadimplencia_pf_pct,
                inadimplencia_pj_pct,
                inadimplencia_total_pct,
                estoque_credito_pj,
                estoque_credito_pf,
                concessao_imobiliario_pf,
                tcr_efetiva_indice
            FROM market.credito_sistema_financeiro
            ORDER BY data_referencia ASC
            LIMIT :limit;
            """
        )
        res = await db.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        items = [
            CreditSystemItem(
                data_referencia=r["data_referencia"],
                poupanca_captacao_liquida=float(r["poupanca_captacao_liquida"]) if r["poupanca_captacao_liquida"] is not None else None,
                poupanca_saldo_total=float(r["poupanca_saldo_total"]) if r["poupanca_saldo_total"] is not None else None,
                inadimplencia_pf_pct=float(r["inadimplencia_pf_pct"]) if r["inadimplencia_pf_pct"] is not None else None,
                inadimplencia_pj_pct=float(r["inadimplencia_pj_pct"]) if r["inadimplencia_pj_pct"] is not None else None,
                inadimplencia_total_pct=float(r["inadimplencia_total_pct"]) if r["inadimplencia_total_pct"] is not None else None,
                estoque_credito_pj=float(r["estoque_credito_pj"]) if r["estoque_credito_pj"] is not None else None,
                estoque_credito_pf=float(r["estoque_credito_pf"]) if r["estoque_credito_pf"] is not None else None,
                concessao_imobiliario_pf=float(r["concessao_imobiliario_pf"]) if r["concessao_imobiliario_pf"] is not None else None,
                tcr_efetiva_indice=float(r["tcr_efetiva_indice"]) if r["tcr_efetiva_indice"] is not None else None,
            )
            for r in rows
        ]
        return CreditSystemResponse(total_records=len(items), items=items)
