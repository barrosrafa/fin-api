from typing import List, Optional
from pydantic import BaseModel, Field


class DividendSimulationRequest(BaseModel):
    ticker: Optional[str] = None
    initial_capital: float = Field(..., ge=0, description="Capital inicial R$")
    monthly_contribution: float = Field(..., ge=0, description="Aporte regular mensal R$")
    time_horizon_months: int = Field(..., ge=1, le=600, description="Prazo em meses (ex: 120)")
    initial_stock_price: float = Field(..., gt=0, description="Preço atual da cota/ação R$")
    monthly_dividend_per_unit: float = Field(..., ge=0, description="Dividendo médio mensal R$/cota")
    annual_inflation_rate: float = Field(default=0.045, ge=0, le=0.5, description="Inflação anual esperada (ex: 0.045 = 4.5%)")
    annual_dividend_growth_rate: float = Field(default=0.05, ge=0, le=0.5, description="Crescimento anual do provento (DGR)")
    tax_rate: float = Field(default=0.0, ge=0, le=0.5, description="Alíquota de imposto (0.0 p/ BR, 0.30 p/ US)")
    reinvest_dividends: bool = Field(default=True, description="Reinvestir proventos mensalmente")


class MonthlyMilestone(BaseModel):
    mes: int
    cotas: float
    patrimonio: float
    aporte_realizado: float
    provento_recebido: float
    total_investido_bolso: float
    yield_on_cost_pct: float


class MagicNumberInfo(BaseModel):
    atingido: bool
    mes: Optional[int] = None
    cotas_necessarias: Optional[float] = None


class DividendSimulationResponse(BaseModel):
    patrimonio_final: float
    total_aportado_bolso: float
    total_proventos_gerados: float
    cotas_finais: float
    renda_mensal_final: float
    magic_number: MagicNumberInfo
    evolucao: List[MonthlyMilestone]


class MonthlyHeatmapItem(BaseModel):
    month: int
    record_date_probability_pct: float
    payment_probability_pct: float
    average_payout_per_unit: float
    last_payment_year: Optional[int] = None


class DividendMapEntry(BaseModel):
    ticker: str
    asset_name: str
    asset_type: str
    monthly_heatmap: List[MonthlyHeatmapItem]


class DividendMapResponse(BaseModel):
    total: int
    items: List[DividendMapEntry]


class DividendCalendarDetailItem(BaseModel):
    id_provento: int
    ticker: str
    tipo: str
    data_com: Optional[str] = None
    data_pagamento: Optional[str] = None
    valor_bruto: float
    aliquota_ir_pct: float
    valor_liquido: float
    moeda: str = "BRL"
    cotacao_atual: float
    yield_evento_pct: float
