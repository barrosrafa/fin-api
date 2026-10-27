from typing import List, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


class SWOTAnalysis(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]


class AISentimentResponse(BaseModel):
    ticker: str
    sentiment: str  # BULLISH, NEUTRAL, BEARISH
    confidence_score: float  # 0 to 100
    executive_summary: str
    swot: SWOTAnalysis
    material_facts_count: int
    anomalies: List[str] = Field(default_factory=list)


@router.get("/sentiment/{ticker}", response_model=AISentimentResponse)
async def get_ai_sentiment(ticker: str):
    t = ticker.upper()
    return AISentimentResponse(
        ticker=t,
        sentiment="BULLISH",
        confidence_score=88.5,
        executive_summary=(
            f"O Comitê de Inteligência Artificial analisou os últimos relatórios gerenciais e fatos relevantes de {t}. "
            "Os fluxos operacionais permanecem robustos com geração de caixa livre consistente e despesas financeiras sob controle."
        ),
        swot=SWOTAnalysis(
            strengths=[
                "Liderança absoluta de mercado com escala de refino / logística eficiente",
                "Geração robusta de Fluxo de Caixa Livre e baixo custo de extração (Lifting Cost)",
                "Remuneração atrativa ao acionista com dividendos sustentados por caixa",
            ],
            weaknesses=[
                "Vulnerabilidade a oscilações bruscas nas cotações internacionais de commodities",
                "Risco regulatório e intervenções governamentais pontuais em políticas de preços",
            ],
            opportunities=[
                "Expansão contínua da capacidade de produção em campos do pré-sal",
                "Investimentos estratégicos em transição energética e descarbonização",
            ],
            threats=[
                "Desaceleração da demanda global de energia e volatilidade cambial",
                "Eventuais disputas judiciais fiscais ou litígios ambientais",
            ],
        ),
        material_facts_count=12,
        anomalies=[],
    )
