from enum import Enum
from typing import Optional, List, Dict
from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator
from decimal import Decimal
from typing import Literal


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
    id: str
    nome: str
    descricao: Optional[str] = None
    padrao: bool = False
    criado_em: Optional[datetime] = None


class TransactionCreate(BaseModel):
    ticker: str
    tipo: TransactionType
    quantidade: Decimal = Field(..., gt=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    preco_unitario: Decimal = Field(..., ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    taxas: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    data_operacao: date
    corretora: Optional[str] = None
    notas: Optional[str] = None

    @model_validator(mode="after")
    def positive_trade_price(self):
        if self.tipo in (TransactionType.COMPRA, TransactionType.VENDA) and self.preco_unitario <= 0:
            raise ValueError("Trade price must be positive")
        return self



class PositionResponse(BaseModel):
    ticker: str
    tipo_ativo: str
    quantidade: Decimal
    preco_medio: Decimal
    preco_atual: Optional[Decimal] = None
    price_status: Literal["missing", "stale", "valid"] = "missing"
    price_as_of: Optional[datetime] = None
    price_source: Optional[str] = None
    valor_total_custo: Decimal
    valor_total_atual: Optional[Decimal] = None
    lucro_prejuizo: Optional[Decimal] = None
    lucro_prejuizo_pct: Optional[Decimal] = None
    peso_pct: Optional[Decimal] = None


class PortfolioSummaryResponse(BaseModel):
    wallet_id: str
    total_cost: Decimal
    total_equity: Optional[Decimal] = None
    profit_loss: Optional[Decimal] = None
    profit_loss_pct: Optional[Decimal] = None
    covered_equity: Decimal = Decimal(0)
    price_coverage_pct: Decimal = Decimal(0)
    priced_positions: int = 0
    total_positions: int = 0
    positions: List[PositionResponse] = Field(default_factory=list)
    allocation_by_type: Dict[str, Decimal] = Field(default_factory=dict)
