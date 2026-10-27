from typing import Optional
from app.fiis.schemas import (
    FIIDetailResponse,
    FIIPropertyItem,
    FIIBrickScoreAxis,
    FIITenantConcentration,
    FIICRIHolding,
)


class FIIService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_fii_detail(self, ticker: str) -> FIIDetailResponse:
        t = ticker.upper()
        # Canonical baseline with deep physical / financial metrics
        properties = [
            FIIPropertyItem(
                id="prop-1",
                name="Centro Logístico Imigrantes",
                type="LOGISTICA",
                address="Rod. dos Imigrantes, km 28",
                city="São Bernardo do Campo",
                state="SP",
                abl_m2=84500.0,
                occupancy_pct=98.5,
                siila_standard="AAA",
                fund_share_pct=100.0,
            ),
            FIIPropertyItem(
                id="prop-2",
                name="Parque Logístico Betim",
                type="LOGISTICA",
                address="Via Expressa, 4500",
                city="Betim",
                state="MG",
                abl_m2=62000.0,
                occupancy_pct=100.0,
                siila_standard="AA",
                fund_share_pct=100.0,
            ),
            FIIPropertyItem(
                id="prop-3",
                name="Edifício Platinum Tower",
                type="LAJES_CORP",
                address="Av. Brigadeiro Faria Lima, 3400",
                city="São Paulo",
                state="SP",
                abl_m2=22400.0,
                occupancy_pct=94.2,
                siila_standard="AAA",
                fund_share_pct=60.0,
            ),
        ]

        brick_score = [
            FIIBrickScoreAxis(name="Imobiliário & SiiLA", score=92.0, weight=0.25, status="EXCELENTE", comment="Ativos Triple A com excelente absorção regional."),
            FIIBrickScoreAxis(name="Alavancagem & Dívida", score=88.0, weight=0.20, status="BOM", comment="Passivos de securitização com LTV inferior a 25% do PL."),
            FIIBrickScoreAxis(name="Inquilinos & Crédito", score=95.0, weight=0.20, status="EXCELENTE", comment="Top locatários multinacionais com baixa inadimplência."),
            FIIBrickScoreAxis(name="Gestão & Governança", score=85.0, weight=0.15, status="BOM", comment="Taxas dentro da mediana CVM com bom alinhamento."),
            FIIBrickScoreAxis(name="Preço & Valuation", score=78.0, weight=0.10, status="REGULAR", comment="P/VP negociando próximo da paridade patrimonial."),
            FIIBrickScoreAxis(name="Risco de Papel/CRIs", score=90.0, weight=0.10, status="EXCELENTE", comment="Garantias fiduciárias e sobrecolateral sólidas."),
        ]

        tenants = [
            FIITenantConcentration(tenant_name="Mercado Livre", sector="E-Commerce / Logística", revenue_pct=24.5, contract_type="ATIPICO"),
            FIITenantConcentration(tenant_name="DHL Supply Chain", sector="Operador Logístico", revenue_pct=18.2, contract_type="TIPICO"),
            FIITenantConcentration(tenant_name="Ambev S.A.", sector="Bebidas / Consumo", revenue_pct=15.0, contract_type="ATIPICO"),
            FIITenantConcentration(tenant_name="Magazine Luiza", sector="Varejo", revenue_pct=11.4, contract_type="TIPICO"),
        ]

        cris = [
            FIICRIHolding(code="CRI-HGLG-01", debtor="Log Commercial Properties", indexer="IPCA + 7.85%", coupon_pct=7.85, ltv_pct=52.0, guarantees="Alienação Fiduciária de Terrenos e Galpões", rating="AAA"),
            FIICRIHolding(code="CRI-HGLG-02", debtor="Bresco Logística", indexer="CDI + 2.10%", coupon_pct=2.10, ltv_pct=48.5, guarantees="Cessão Fiduciária de Recebíveis de Aluguel", rating="AA+"),
        ]

        return FIIDetailResponse(
            ticker=t,
            name=f"Fundo de Investimento Imobiliário {t}",
            segment="Galpões Logísticos e Industriais",
            current_price=162.50,
            pvp=0.98,
            dividend_yield_12m=8.75,
            net_worth=5_420_000_000.0,
            physical_vacancy_pct=2.8,
            financial_vacancy_pct=1.9,
            wault_years=4.6,
            properties=properties,
            brick_score=brick_score,
            top_tenants=tenants,
            cri_portfolio=cris,
            quarterly_dre={
                "receita_locacao": 89_400_000.0,
                "receita_rendimentos": 12_800_000.0,
                "despesas_operacionais": -4_500_000.0,
                "taxa_administracao": -3_200_000.0,
                "resultado_distribuivel": 94_500_000.0,
                "rendimento_por_cota": 1.10,
            },
        )
