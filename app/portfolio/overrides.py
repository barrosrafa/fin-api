from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.comparator.arbitration import ArbitrationEngine, SourceObservation
from app.intelligence.falsifiable_phrase import (
    DecomposedAsset,
    FalsifiablePhraseEngine,
    LookThroughDetail,
    PhraseContext,
    RatingEvent,
)
from app.portfolio.debtor_graph import DebtorGraphService, EdgeInfo, PortfolioPosition, UserOverride

router = APIRouter(prefix="/api/v1", tags=["portfolio-graph"])

# In-memory storage for demonstration / mocked integration tests
_USER_OVERRIDES_STORE: Dict[str, List[UserOverride]] = {}
_DISCREPANCIES_STORE: List[Dict[str, Any]] = []


class UserOverrideCreate(BaseModel):
    source_asset_id: str
    target_entity_name: str
    override_type: str = Field(..., description="EXCLUDE_EDGE, REMAP_ENTITY, OVERRIDE_WEIGHT")
    override_weight_pct: Optional[float] = None
    remapped_entity_name: Optional[str] = None
    reason: Optional[str] = None


class DiscrepancyReportCreate(BaseModel):
    source_asset_id: str
    target_entity_id: Optional[str] = None
    reported_issue: str


# Sample seed edges for KNIP11 and KNCR11
DEFAULT_EDGES = {
    "KNIP11": [
        EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=18.5, coverage_category="RESOLVED"),
        EdgeInfo(target_entity_name="MRV", weight_pct=9.25, coverage_category="RESOLVED"),
        EdgeInfo(target_entity_name=None, weight_pct=4.0, coverage_category="TEMPORARY_PENDING_CURATION"),
        EdgeInfo(target_entity_name=None, weight_pct=2.5, coverage_category="STRUCTURE_OPAQUE"),
    ],
    "KNCR11": [
        EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=12.0, coverage_category="RESOLVED"),
    ],
}


@router.post("/portfolio/{user_id}/overrides")
def add_user_override(user_id: str, payload: UserOverrideCreate):
    override = UserOverride(
        source_asset_id=payload.source_asset_id,
        target_entity_name=payload.target_entity_name,
        override_type=payload.override_type,
        override_weight_pct=payload.override_weight_pct,
        remapped_entity_name=payload.remapped_entity_name,
    )
    _USER_OVERRIDES_STORE.setdefault(user_id, []).append(override)
    return {"status": "success", "override": payload.model_dump()}


@router.post("/portfolio/{user_id}/discrepancies")
def report_discrepancy(user_id: str, payload: DiscrepancyReportCreate):
    entry = {"user_id": user_id, **payload.model_dump()}
    _DISCREPANCIES_STORE.append(entry)
    return {"status": "reported", "discrepancy": entry}


@router.get("/portfolio/{user_id}/debtor-concentration")
def get_debtor_concentration(user_id: str):
    overrides = _USER_OVERRIDES_STORE.get(user_id, [])
    # Default portfolio for demonstration
    positions = [
        PortfolioPosition(ticker="KNIP11", asset_class="FII", weight_pct=22.0),
        PortfolioPosition(ticker="KNCR11", asset_class="FII", weight_pct=9.0),
        PortfolioPosition(ticker="PETR4", asset_class="EQUITY", weight_pct=69.0),
    ]

    service = DebtorGraphService(edges_lookup=DEFAULT_EDGES)
    result = service.calculate_debtor_exposure(positions, overrides=overrides)
    return result


@router.get("/portfolio/{user_id}/falsifiable-phrase")
def get_falsifiable_phrase(user_id: str):
    engine = FalsifiablePhraseEngine()
    ctx = PhraseContext(
        macro_class="crédito imobiliário de papel",
        total_pct=34.0,
        decomposed_assets=[
            DecomposedAsset(name="KNIP11", pct=22.0),
            DecomposedAsset(name="KNCR11", pct=9.0),
            DecomposedAsset(name="CRI JHSF 129S", pct=3.0),
        ],
        rating_event=RatingEvent(
            asset_name="CRI JHSF 129S",
            old_rating="AA",
            new_rating="A",
            event_date="12/09",
            source="Brick360",
            source_time="14:32",
        ),
        look_through_detail=LookThroughDetail(
            fii_name="KNIP11",
            pl_pct=18.5,
            sources="Clube FII / SiiLA",
        ),
        canonical_debtor="Grupo JHSF",
        user_threshold_pct=25.0,
    )
    result = engine.generate_phrase(user_id=user_id, portfolio_hash="hash-demo-1", context=ctx)
    return result


@router.get("/reconciliation/{ticker}")
def get_reconciliation_details(ticker: str):
    engine = ArbitrationEngine()
    # Mock multi-source observations for ticker
    observations = [
        SourceObservation(
            source_id="STATUS_INVEST",
            value=8.20,
            freshness_score=95.0,
            has_public_methodology=True,
            historical_stability_score=90.0,
        ),
        SourceObservation(
            source_id="FUNDS_EXPLORER",
            value=7.90,
            freshness_score=85.0,
            has_public_methodology=True,
            historical_stability_score=80.0,
        ),
    ]
    arbitrated = engine.arbitrate(ticker=ticker, metric_name="DY_12M", observations=observations)
    return {
        "ticker": ticker,
        "arbitrated": arbitrated,
        "divergence": {
            "has_divergence": True,
            "delta_pct": 3.8,
            "taxonomy": "DIVIDEND_WINDOW_MISMATCH",
            "taxonomy_display": "Janela de Dividendos Divergente (12M LTM vs Último Pagamento Anualizado)",
            "sources": [
                {"source": "STATUS_INVEST", "value": 8.20, "methodology": "12 meses corridos (LTM)"},
                {"source": "FUNDS_EXPLORER", "value": 7.90, "methodology": "Último provento anualizado"},
            ],
        },
    }
