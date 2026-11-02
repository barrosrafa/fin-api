"""Confirmed trading events, with documentary evidence and effective dates.

Registry status is also honored for every instrument. No inactivity is inferred
from low liquidity or a missing quote. These overrides correct known stale registry
records until official discovery reconciles them.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel


class TradingStatus(BaseModel):
    status: str = "unknown"
    ended_on: str | None = None
    successor: str | None = None
    source_url: str | None = None


AXIA_NOTICE = (
    "https://www.b3.com.br/data/files/CB/71/43/E8/FC56E91064BF82E9AC094EA8/"
    "OC%20035-2026-VNC%20TRATAMENTO%20DAS%20CARTEIRAS%20DE%20INDICES%20DA%20B3_PT.pdf"
)
CONFIRMED_EVENTS = {
    ticker: TradingStatus(status="inactive", ended_on="2026-06-08", successor="AXIA3", source_url=AXIA_NOTICE)
    for ticker in ("AXIA5", "AXIA6")
}


def trading_status(ticker: str, registry_status: str | None = None, today: date | None = None) -> TradingStatus:
    today = today or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    event = CONFIRMED_EVENTS.get(ticker.upper())
    if event and today >= date.fromisoformat(event.ended_on):
        return event.model_copy()
    registry_key = registry_status.upper() if isinstance(registry_status, str) else None
    status = {"ACTIVE": "active", "INACTIVE": "inactive", "MATURED": "inactive"}.get(registry_key, "unknown")
    return TradingStatus(status=status)
