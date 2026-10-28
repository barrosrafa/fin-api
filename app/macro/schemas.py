from typing import List, Optional
from pydantic import BaseModel, Field


class GovernmentAccountsItem(BaseModel):
    data_referencia: str
    receita_total_bruta: Optional[float] = None
    transferencias_estados_mun: Optional[float] = None
    receita_liquida: float
    despesa_previdencia: Optional[float] = None
    despesa_pessoal: Optional[float] = None
    despesa_total: float
    resultado_primario: float
    resultado_nominal: Optional[float] = None
    divida_bruta_pib_pct: Optional[float] = None
    divida_liquida_pib_pct: Optional[float] = None


class GovernmentAccountsResponse(BaseModel):
    total_records: int
    items: List[GovernmentAccountsItem] = Field(default_factory=list)


class CreditSystemItem(BaseModel):
    data_referencia: str
    poupanca_captacao_liquida: Optional[float] = None
    poupanca_saldo_total: Optional[float] = None
    inadimplencia_pf_pct: Optional[float] = None
    inadimplencia_pj_pct: Optional[float] = None
    inadimplencia_total_pct: Optional[float] = None
    estoque_credito_pj: Optional[float] = None
    estoque_credito_pf: Optional[float] = None
    concessao_imobiliario_pf: Optional[float] = None
    tcr_efetiva_indice: Optional[float] = None


class CreditSystemResponse(BaseModel):
    total_records: int
    items: List[CreditSystemItem] = Field(default_factory=list)
