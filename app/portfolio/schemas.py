from enum import Enum
from typing import Optional, List, Dict
from datetime import date, datetime
from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    COMPRA = "COMPRA"
    VENDA = "VENDA"
    DIVIDENDO = "DIVIDENDO"
    JCP = "JCP"
    RENDIMENTO = "RENDIMENTO"
    BONIFICACAO = "BONIFICACAO"
    SUBSCRICAO = "SUBSCRICAO"


class WalletCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    descricao: Optional[str] = None
    padrao: bool = False


class WalletResponse(BaseModel):
    id: int
    nome: str
    descricao: Optional[str] = None
    padrao: bool = False
    criado_em: Optional[datetime] = None


class TransactionCreate(BaseModel):
    ticker: str
    tipo: TransactionType
    quantidade: float = Field(..., gt=0)
    preco_unitario: float = Field(..., ge=0)
    taxas: float = 0.0
    data_operacao: date
    corretora: Optional[str] = None
    notas: Optional[str] = None


class PositionResponse(BaseModel):
    ticker: str
    tipo_ativo: str
    quantidade: float
    preco_medio: float
    preco_atual: float
    valor_total_custo: float
    valor_total_atual: float
    lucro_prejuizo: float
    lucro_prejuizo_pct: float
    peso_pct: float = 0.0


class PortfolioSummaryResponse(BaseModel):
    wallet_id: int
    total_cost: float
    total_equity: float
    profit_loss: float
    profit_loss_pct: float
    positions: List[PositionResponse] = []
    allocation_by_type: Dict[str, float] = {}
