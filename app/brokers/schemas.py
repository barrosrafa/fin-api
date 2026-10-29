from typing import List
from pydantic import BaseModel


class BrokerCosts(BaseModel):
    taxa_acoes: float
    taxa_fiis: float
    taxa_opcoes: float
    custodia_mensal: float
    spread_cambial_ptax_pct: float


class BrokerRatings(BaseModel):
    nota_geral: float
    total_avaliacoes: int


class BrokerItem(BaseModel):
    id: int
    nome: str
    cnpj: str
    is_internacional: bool
    costs: BrokerCosts
    ratings: BrokerRatings
    plataformas_suportadas: List[str]


class BrokerResponse(BaseModel):
    total: int
    items: List[BrokerItem]
