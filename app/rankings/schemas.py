from typing import List, Optional
from pydantic import BaseModel, Field


class RankingAssetItem(BaseModel):
    pos: int
    ticker: str
    nome: str
    patrimonio_liquido_mm: float
    retorno_30d: float
    retorno_ano: float
    retorno_12m: float
    retorno_24m: Optional[float] = None
    sharpe_12m: Optional[float] = None
    taxa_adm_total: float = 0.30
    categoria: str = "Ações"
    cotistas: int = 0
    negociacao_diaria_mm: float = 0.0


class RankingsResponse(BaseModel):
    tipo_ativo: str
    ordem: str
    categoria: str
    total_assets: int
    items: List[RankingAssetItem] = Field(default_factory=list)
