from datetime import datetime, timezone
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class CanonicalQuote(BaseModel):
    ticker: str
    price: float
    change_pct: float
    volume: float = 0.0
    p_l: Optional[float] = None
    dy_pct: Optional[float] = None
    p_vp: Optional[float] = None
    source: str
    as_of: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalFundamentals(BaseModel):
    ticker: str
    p_l: Optional[float] = None
    p_vp: Optional[float] = None
    dy_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    roic_pct: Optional[float] = None
    margem_liquida_pct: Optional[float] = None
    divida_liquida_ebitda: Optional[float] = None
    ev_ebitda: Optional[float] = None
    lucro_por_acao: Optional[float] = None
    valor_patrimonial_por_acao: Optional[float] = None
    source: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DataNormalizer:
    @staticmethod
    def clean_number(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().replace("R$", "").replace("%", "").strip()
        if not text or text in ("-", "--", "N/A", "null"):
            return None

        # Remove thousand separator dots and convert decimal commas to dots
        # e.g., "1.500.000,00" -> "1500000.00"
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")

        try:
            return float(text)
        except ValueError:
            return None

    @classmethod
    def normalize_quote(cls, raw: Dict[str, Any], source: str) -> CanonicalQuote:
        ticker = str(raw.get("ticker", "")).strip().upper()
        price = cls.clean_number(raw.get("price") or raw.get("cotacao") or raw.get("valor")) or 0.0
        change = cls.clean_number(raw.get("change_pct") or raw.get("variacao") or raw.get("oscilacao")) or 0.0
        volume = cls.clean_number(raw.get("volume") or raw.get("volume_financeiro") or raw.get("vol")) or 0.0
        p_l = cls.clean_number(raw.get("p_l") or raw.get("pl") or raw.get("pe_ratio"))
        dy = cls.clean_number(raw.get("dy") or raw.get("dy_pct") or raw.get("dividend_yield"))
        p_vp = cls.clean_number(raw.get("p_vp") or raw.get("pvp"))

        return CanonicalQuote(
            ticker=ticker,
            price=price,
            change_pct=change,
            volume=volume,
            p_l=p_l,
            dy_pct=dy,
            p_vp=p_vp,
            source=source,
            as_of=raw.get("as_of"),
        )

    @classmethod
    def normalize_fundamentals(cls, raw: Dict[str, Any], source: str) -> CanonicalFundamentals:
        ticker = str(raw.get("ticker", "")).strip().upper()
        return CanonicalFundamentals(
            ticker=ticker,
            p_l=cls.clean_number(raw.get("p_l") or raw.get("pl")),
            p_vp=cls.clean_number(raw.get("p_vp") or raw.get("pvp")),
            dy_pct=cls.clean_number(raw.get("dy") or raw.get("dividend_yield")),
            roe_pct=cls.clean_number(raw.get("roe")),
            roic_pct=cls.clean_number(raw.get("roic")),
            margem_liquida_pct=cls.clean_number(raw.get("margem_liquida")),
            divida_liquida_ebitda=cls.clean_number(raw.get("divida_liquida_ebitda") or raw.get("div_liq_ebitda")),
            ev_ebitda=cls.clean_number(raw.get("ev_ebitda")),
            lucro_por_acao=cls.clean_number(raw.get("lpa")),
            valor_patrimonial_por_acao=cls.clean_number(raw.get("vpa")),
            source=source,
        )
