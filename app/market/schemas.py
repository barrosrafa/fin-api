from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class TickerQuote(BaseModel):
    ticker: str
    price: float
    change_pct: float
    volume: float = 0.0
    p_l: Optional[float] = None
    dy_pct: Optional[float] = None
    p_vp: Optional[float] = None
    source: Optional[str] = "fin-cache"


class QuoteResponse(BaseModel):
    ticker: str
    status: Literal["fresh", "stale", "syncing"]
    quote: Optional[TickerQuote] = None
    sync_id: Optional[str] = None
    message: Optional[str] = None
    check_url: Optional[str] = None


class SyncStatusResponse(BaseModel):
    ticker: str
    status: Literal["idle", "in_progress", "completed", "failed"]
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class IndicatorsResponse(BaseModel):
    ticker: str
    p_l: Optional[float] = None
    p_vp: Optional[float] = None
    dy_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    roic_pct: Optional[float] = None
    margem_liquida_pct: Optional[float] = None
    divida_liquida_ebitda: Optional[float] = None
    ev_ebitda: Optional[float] = None


class ScreenerFilter(BaseModel):
    asset_class: str = "stock"
    min_dy: Optional[float] = None
    max_p_l: Optional[float] = None
    min_roe: Optional[float] = None
    limit: int = 50
    offset: int = 0


class ScreenerItem(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: float
    dy_pct: Optional[float] = None
    p_l: Optional[float] = None
    roe_pct: Optional[float] = None


# Endpoints for Frontend Terminal
class BenchmarkItem(BaseModel):
    name: str
    ticker: str
    value: float
    change: float
    sparkline: List[float] = Field(default_factory=list)


class AssetSummaryResponse(BaseModel):
    ticker: str
    name: str
    type: str  # ACAO, FII, ETF
    sector: str
    subsector: Optional[str] = None
    currentPrice: float
    change24h: float
    change12m: Optional[float] = None
    dividendYield: float
    marketCap: Optional[float] = None
    pvp: Optional[float] = None
    pl: Optional[float] = None
    sparkline: List[float] = Field(default_factory=list)
    badge: Optional[str] = None


class DividendCalendarItem(BaseModel):
    id: str
    assetTicker: str
    type: str  # DIVIDENDO, JCP, RENDIMENTO
    referenceMonth: str
    dateCom: str
    paymentDate: str
    valuePerShare: float
    yieldOnCostPct: float


class IbovPEPoint(BaseModel):
    data_referencia: str
    fechamento_indice: float
    pl_ponderado: float
    pl_mediano: float
    media_historica_5y: float
    banda_superior_1dp: float
    banda_inferior_1dp: float
    banda_superior_2dp: float
    banda_inferior_2dp: float


class IbovPEResponse(BaseModel):
    total_records: int
    items: List[IbovPEPoint] = Field(default_factory=list)


class InvestorFlowItem(BaseModel):
    data_pregao: str
    categoria_investidor: str
    compras_reais: float
    vendas_reais: float
    saldo_liquido: float
    saldo_acumulado_mes: Optional[float] = None
    saldo_acumulado_ano: Optional[float] = None
    participacao_pct: Optional[float] = None


class InvestorFlowResponse(BaseModel):
    total_records: int
    items: List[InvestorFlowItem] = Field(default_factory=list)


class EarningsCalendarItem(BaseModel):
    ticker: str
    nome_empresarial: str
    periodo_referencia: str
    tipo_documento: str
    data_prevista: str
    horario_previsto: Optional[str] = "APOS_FECHAMENTO"
    status: str = "CONFIRMADO"
    link_webcast: Optional[str] = None


class EarningsCalendarResponse(BaseModel):
    total: int
    items: List[EarningsCalendarItem] = Field(default_factory=list)

