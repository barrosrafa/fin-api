from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.fiis.schemas import (
    FIIDetailResponse,
    FIIPropertyItem,
    FIIBrickScoreAxis,
    FIITenantConcentration,
    FIICRIHolding,
    FIIRankingItem,
    FIIVacancyPoint,
    FIIVacancyHistoryResponse,
)


class FIIService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_fii_detail(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> FIIDetailResponse:
        t = ticker.upper()
        name = "CSHG Logística FII" if t == "HGLG11" else f"Fundo Imobiliário {t}"
        segment = "Logística Industrial"
        current_price = 162.50
        pvp = 0.98
        dividend_yield_12m = 8.75
        net_worth = 5_420_000_000.0
        physical_vacancy_pct = 2.4
        financial_vacancy_pct = 1.8
        id_ativo = None

        properties: List[FIIPropertyItem] = []
        brick_score: List[FIIBrickScoreAxis] = []

        if db_session is not None:
            # 1. Fetch Asset, Emissor & Details
            stmt = text(
                """
                SELECT 
                    a.id_ativo,
                    COALESCE(ec.nome_empresarial, a.ticker) as nome,
                    COALESCE(ec.subsetor, ec.setor, 'Imobiliário') as segmento,
                    COALESCE(cd.preco_fechamento, 160.0) as preco,
                    COALESCE(df.pvp, 0.98) as pvp,
                    COALESCE(df.dividend_yield, 8.5) as dy,
                    COALESCE(df.patrimonio_liquido, 5000000000.0) as pl
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
                LEFT JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
                LEFT JOIN LATERAL (
                    SELECT preco_fechamento 
                    FROM market.cotacao_diaria 
                    WHERE id_ativo = a.id_ativo 
                    ORDER BY data_pregao DESC LIMIT 1
                ) cd ON TRUE
                WHERE a.ticker = :ticker
                LIMIT 1;
                """
            )
            res = await db_session.execute(stmt, {"ticker": t})
            row = res.mappings().first()
            if row:
                id_ativo = row["id_ativo"]
                name = row["nome"]
                segment = row["segmento"]
                current_price = float(row["preco"])
                pvp = float(row["pvp"])
                dividend_yield_12m = float(row["dy"])
                net_worth = float(row["pl"])
                physical_vacancy_pct = 2.4
                financial_vacancy_pct = 1.8

            # 2. Fetch Real Properties from asset_details.fii_imovel
            prop_stmt = text(
                """
                SELECT 
                    fi.id_imovel,
                    fi.nome,
                    fi.tipo_imovel,
                    fi.endereco,
                    fi.cidade,
                    fi.uf,
                    fi.abl_total_m2,
                    fi.classe_siila,
                    COALESCE(fip.participacao_pct, 100.0) as part_pct,
                    COALESCE(100.0 - fip.vacancia_fisica_pct, 98.0) as occupancy_pct
                FROM asset_details.fii_imovel fi
                LEFT JOIN asset_details.fii_imovel_participacao fip ON fip.id_imovel = fi.id_imovel
                ORDER BY fi.abl_total_m2 DESC
                LIMIT 10;
                """
            )
            p_res = await db_session.execute(prop_stmt)
            for pr in p_res.mappings().all():
                properties.append(
                    FIIPropertyItem(
                        id=f"prop-{pr['id_imovel']}",
                        name=pr["nome"],
                        type=pr["tipo_imovel"] or "LOGISTICA",
                        address=pr["endereco"] or "",
                        city=pr["cidade"] or "São Paulo",
                        state=pr["uf"] or "SP",
                        abl_m2=float(pr["abl_total_m2"]),
                        occupancy_pct=float(pr["occupancy_pct"]),
                        siila_standard=pr["classe_siila"] or "AAA",
                        fund_share_pct=float(pr["part_pct"]),
                    )
                )

            # 3. Fetch Brick Score from analytics.score_eixo
            score_stmt = text(
                """
                SELECT eixo, pontuacao, peso, detalhes
                FROM analytics.score_eixo
                ORDER BY peso DESC;
                """
            )
            s_res = await db_session.execute(score_stmt)
            for sc in s_res.mappings().all():
                det = sc["detalhes"] or {}
                brick_score.append(
                    FIIBrickScoreAxis(
                        name=det.get("nome", sc["eixo"].capitalize()),
                        score=float(sc["pontuacao"]),
                        weight=float(sc["peso"]),
                        status=det.get("status", "BOM"),
                        comment=det.get("comment", ""),
                    )
                )

        # Fallback for properties if empty
        if not properties:
            properties = [
                FIIPropertyItem(
                    id="prop-1",
                    name="Hedge Logístico Itupeva",
                    type="LOGISTICA",
                    address="Rod. dos Bandeirantes, km 72",
                    city="Itupeva",
                    state="SP",
                    abl_m2=124500.0,
                    occupancy_pct=98.2,
                    siila_standard="AAA",
                    fund_share_pct=100.0,
                ),
                FIIPropertyItem(
                    id="prop-2",
                    name="Parque Logístico Betim",
                    type="LOGISTICA",
                    address="Via Expressa de Contagem",
                    city="Betim",
                    state="MG",
                    abl_m2=88400.0,
                    occupancy_pct=96.5,
                    siila_standard="AAA",
                    fund_share_pct=100.0,
                ),
            ]

        # Fallback for brick score if empty
        if not brick_score:
            brick_score = [
                FIIBrickScoreAxis(name="Qualidade Imobiliária", score=95.0, weight=0.25, status="EXCELENTE", comment="85% galpões padrão AAA."),
                FIIBrickScoreAxis(name="Financeiro & Alavancagem", score=90.0, weight=0.20, status="EXCELENTE", comment="Alavancagem mínima (< 5% do PL)."),
                FIIBrickScoreAxis(name="Inquilinos & Contratos", score=88.0, weight=0.20, status="BOM", comment="Contratos atípicos de longo prazo."),
                FIIBrickScoreAxis(name="Gestão & Governança", score=94.0, weight=0.15, status="EXCELENTE", comment="Histórico exemplar de gestão."),
                FIIBrickScoreAxis(name="Preço & Desconto (P/VP)", score=82.0, weight=0.10, status="BOM", comment="Negociando próximo ao VP."),
                FIIBrickScoreAxis(name="Risco de Liquidez", score=98.0, weight=0.10, status="EXCELENTE", comment="Mais de R$ 8M/dia negociados."),
            ]

        top_tenants = [
            FIITenantConcentration(tenant_name="Mercado Livre", sector="E-commerce", revenue_pct=24.5, contract_type="ATIPICO"),
            FIITenantConcentration(tenant_name="Volkswagen do Brasil", sector="Automotivo", revenue_pct=18.2, contract_type="TIPICO"),
            FIITenantConcentration(tenant_name="Ambev S.A.", sector="Bebidas", revenue_pct=14.8, contract_type="ATIPICO"),
            FIITenantConcentration(tenant_name="DHL Logística", sector="Logística Global", revenue_pct=12.1, contract_type="TIPICO"),
        ]

        cri_portfolio = [
            FIICRIHolding(code="CRI HGLG 24", debtor="Log Commercial Properties", indexer="IPCA + 7.45%", coupon_pct=7.45, ltv_pct=52.0, guarantees="Alienação fiduciária de galpão", rating="AAA"),
            FIICRIHolding(code="CRI HGLG 25", debtor="Goodman Brasil", indexer="CDI + 1.85%", coupon_pct=1.85, ltv_pct=48.5, guarantees="Cessão fiduciária de recebíveis de locação", rating="AA+"),
        ]

        return FIIDetailResponse(
            ticker=t,
            name=name,
            segment=segment,
            current_price=round(current_price, 2),
            pvp=round(pvp, 2),
            dividend_yield_12m=round(dividend_yield_12m, 2),
            net_worth=net_worth,
            physical_vacancy_pct=round(physical_vacancy_pct, 2),
            financial_vacancy_pct=round(financial_vacancy_pct, 2),
            wault_years=4.8,
            properties=properties,
            brick_score=brick_score,
            top_tenants=top_tenants,
            cri_portfolio=cri_portfolio,
            quarterly_dre={
                "receitas_locacao": 84500000.0,
                "rendimentos_financeiros": 6200000.0,
                "despesas_taxa_administracao": -4200000.0,
                "despesas_imoveis_vacancia": -1800000.0,
                "resultado_liquido_distribuivel": 84700000.0,
                "rendimento_distribuido_por_cota": 1.10,
            },
        )

    async def get_fiis_ranking(
        self,
        sort_by: str = "dy",
        limit: int = 50,
        db_session: Optional[AsyncSession] = None,
    ) -> List[FIIRankingItem]:
        order_col = {
            "dy": "COALESCE(df.dividend_yield, 0.0) DESC",
            "pvp": "COALESCE(df.pvp, 1.0) ASC",
            "vacancia": "COALESCE(fhv.vacancia_fisica_pct, 0.0) ASC",
            "liquidez": "COALESCE(cd.volume_total, a.volume_medio, 0.0) DESC",
        }.get(sort_by.lower(), "COALESCE(df.dividend_yield, 0.0) DESC")

        if db_session is None:
            return [
                FIIRankingItem(rank=1, ticker="HGLG11", name="CSHG Logística", segment="Logística", price=162.50, dy_12m=8.95, pvp=0.98, net_worth=5400000000.0, physical_vacancy_pct=5.5, financial_vacancy_pct=4.1, liquidity_daily=8500000.0),
                FIIRankingItem(rank=2, ticker="KNIP11", name="Kinea Rendimentos", segment="Papel / CRI", price=92.10, dy_12m=11.20, pvp=0.96, net_worth=7800000000.0, physical_vacancy_pct=0.0, financial_vacancy_pct=0.0, liquidity_daily=12000000.0),
                FIIRankingItem(rank=3, ticker="MXRF11", name="Maxi Renda", segment="Híbrido", price=10.15, dy_12m=12.40, pvp=1.02, net_worth=3200000000.0, physical_vacancy_pct=0.0, financial_vacancy_pct=0.0, liquidity_daily=15400000.0),
            ]

        stmt = text(
            f"""
            SELECT 
                a.ticker,
                COALESCE(ec.nome_empresarial, a.ticker) as nome,
                COALESCE(ec.subsetor, 'Imobiliário') as segment,
                COALESCE(cd.preco_fechamento, 100.0) as preco,
                COALESCE(df.dividend_yield, 0.0) as dy,
                COALESCE(df.pvp, 1.0) as pvp,
                COALESCE(df.patrimonio_liquido, 1000000000.0) as pl,
                COALESCE(fhv.vacancia_fisica_pct, 0.0) as vf,
                COALESCE(fhv.vacancia_financeira_pct, 0.0) as vfin,
                COALESCE(cd.volume_total, a.volume_medio, 100000.0) as liquidez
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
            LEFT JOIN LATERAL (
                SELECT vacancia_fisica_pct, vacancia_financeira_pct 
                FROM asset_details.fii_historico_vacancia 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_referencia DESC LIMIT 1
            ) fhv ON TRUE
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, volume_total 
                FROM market.cotacao_diaria 
                WHERE id_ativo = a.id_ativo 
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            WHERE a.tipo_ativo::text = 'FII'
            ORDER BY {order_col}
            LIMIT :limit;
            """
        )
        res = await db_session.execute(stmt, {"limit": limit})
        rows = res.mappings().all()

        items = []
        for idx, r in enumerate(rows, start=1):
            items.append(
                FIIRankingItem(
                    rank=idx,
                    ticker=r["ticker"],
                    name=r["nome"],
                    segment=r["segment"],
                    price=float(r["preco"]),
                    dy_12m=float(r["dy"]),
                    pvp=float(r["pvp"]),
                    net_worth=float(r["pl"]),
                    physical_vacancy_pct=float(r["vf"]),
                    financial_vacancy_pct=float(r["vfin"]),
                    liquidity_daily=float(r["liquidez"]),
                )
            )

        if not items:
            return await self.get_fiis_ranking(sort_by=sort_by, limit=limit, db_session=None)
        return items

    async def get_fii_vacancy_history(
        self,
        ticker: str,
        db_session: Optional[AsyncSession] = None,
    ) -> FIIVacancyHistoryResponse:
        t = ticker.upper()
        if db_session is None:
            pts = [
                FIIVacancyPoint(data_referencia="2025-06-30", vacancia_fisica_pct=6.4, vacancia_financeira_pct=4.9, abl_propria_m2=885000.0, area_ocupada_m2=828360.0),
                FIIVacancyPoint(data_referencia="2025-09-30", vacancia_fisica_pct=5.9, vacancia_financeira_pct=4.5, abl_propria_m2=885000.0, area_ocupada_m2=832785.0),
                FIIVacancyPoint(data_referencia="2025-12-31", vacancia_fisica_pct=5.5, vacancia_financeira_pct=4.1, abl_propria_m2=885000.0, area_ocupada_m2=836325.0),
                FIIVacancyPoint(data_referencia="2026-03-31", vacancia_fisica_pct=5.2, vacancia_financeira_pct=3.8, abl_propria_m2=885000.0, area_ocupada_m2=838980.0),
                FIIVacancyPoint(data_referencia="2026-06-30", vacancia_fisica_pct=4.9, vacancia_financeira_pct=3.5, abl_propria_m2=885000.0, area_ocupada_m2=841635.0),
                FIIVacancyPoint(data_referencia="2026-09-30", vacancia_fisica_pct=4.7, vacancia_financeira_pct=3.2, abl_propria_m2=885000.0, area_ocupada_m2=843405.0),
            ]
            return FIIVacancyHistoryResponse(ticker=t, history=pts)

        stmt = text(
            """
            SELECT 
                fhv.data_referencia::text,
                fhv.vacancia_fisica_pct,
                fhv.vacancia_financeira_pct,
                fhv.abl_propria_m2,
                fhv.area_ocupada_m2
            FROM asset_details.fii_historico_vacancia fhv
            JOIN core.ativo a ON a.id_ativo = fhv.id_ativo
            WHERE a.ticker = :ticker
            ORDER BY fhv.data_referencia ASC;
            """
        )
        res = await db_session.execute(stmt, {"ticker": t})
        rows = res.mappings().all()

        if not rows:
            return await self.get_fii_vacancy_history(ticker=t, db_session=None)

        pts = [
            FIIVacancyPoint(
                data_referencia=r["data_referencia"],
                vacancia_fisica_pct=float(r["vacancia_fisica_pct"]),
                vacancia_financeira_pct=float(r["vacancia_financeira_pct"]),
                abl_propria_m2=float(r["abl_propria_m2"]) if r["abl_propria_m2"] is not None else None,
                area_ocupada_m2=float(r["area_ocupada_m2"]) if r["area_ocupada_m2"] is not None else None,
            )
            for r in rows
        ]
        return FIIVacancyHistoryResponse(ticker=t, history=pts)

