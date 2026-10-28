from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SuitabilityOption(BaseModel):
    id_opcao: int
    ordem: int
    texto: str
    pontos: int


class SuitabilityQuestion(BaseModel):
    id_pergunta: int
    ordem: int
    titulo: str
    descricao: Optional[str] = None
    eixo: str
    opcoes: List[SuitabilityOption]


class SuitabilityAnswerItem(BaseModel):
    id_pergunta: int
    id_opcao_selecionada: int


class SuitabilityEvaluateRequest(BaseModel):
    respostas: List[SuitabilityAnswerItem]


class AssetAllocationTarget(BaseModel):
    renda_fixa: float
    fiis: float
    acoes: float
    internacional: float
    cripto: Optional[float] = 0.0


class SuitabilityEvaluateResponse(BaseModel):
    score_total: int
    codigo_categoria: str
    nome_categoria: str
    descricao: str
    alocacao_alvo: AssetAllocationTarget
    recomendacoes_principais: List[str]
