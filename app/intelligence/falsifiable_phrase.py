from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DecomposedAsset:
    name: str
    pct: float


@dataclass
class RatingEvent:
    asset_name: str
    old_rating: str
    new_rating: str
    event_date: str
    source: str
    source_time: str


@dataclass
class LookThroughDetail:
    fii_name: str
    pl_pct: float
    sources: str


@dataclass
class PhraseContext:
    macro_class: str
    total_pct: float
    decomposed_assets: List[DecomposedAsset]
    rating_event: Optional[RatingEvent] = None
    look_through_detail: Optional[LookThroughDetail] = None
    canonical_debtor: Optional[str] = None
    user_threshold_pct: Optional[float] = None


@dataclass
class InteractivePill:
    pill_id: str
    label: str
    value: Any
    pill_type: str # PERCENTAGE, SOURCE_PROVENANCE, RATING_EVENT, THRESHOLD
    modal_target: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FalsifiablePhraseResult:
    text: str
    interactive_pills: List[InteractivePill]
    inference_log: Dict[str, Any]


class FalsifiablePhraseEngine:
    """100% deterministic template engine generating falsifiable statements in < 10ms with inference logging."""

    TEMPLATE_ID = "portfolio_debtor_concentration_v1"

    def generate_phrase(
        self,
        user_id: str,
        portfolio_hash: str,
        context: PhraseContext,
    ) -> FalsifiablePhraseResult:
        # Build assets decomposition string: "soma de FII X (22.0%), fundo CVM 175 Y (9.0%) e CRI Z (3.0%)"
        assets_strs = [f"{a.name} ({a.pct:.1f}%)" for a in context.decomposed_assets]
        if len(assets_strs) > 1:
            decomposed_text = ", ".join(assets_strs[:-1]) + f" e {assets_strs[-1]}"
        elif assets_strs:
            decomposed_text = assets_strs[0]
        else:
            decomposed_text = "ativos diretos"

        text_parts = [
            f"Sua exposição a {context.macro_class} é {context.total_pct:.1f}% do patrimônio — soma de {decomposed_text}."
        ]

        pills: List[InteractivePill] = [
            InteractivePill(
                pill_id="pill_total_exp",
                label=f"{context.total_pct:.1f}%",
                value=context.total_pct,
                pill_type="PERCENTAGE",
                modal_target="MODAL_CALCULATION_TREE",
                metadata={"macro_class": context.macro_class},
            )
        ]

        if context.canonical_debtor:
            pills.append(
                InteractivePill(
                    pill_id="pill_canonical_debtor",
                    label=context.canonical_debtor,
                    value=context.canonical_debtor,
                    pill_type="ENTITY",
                    modal_target="MODAL_DEBTOR_DETAILS",
                    metadata={"debtor": context.canonical_debtor},
                )
            )

        if context.rating_event:
            re = context.rating_event
            rating_str = (
                f"O rating do {re.asset_name} caiu de {re.old_rating} para {re.new_rating} em {re.event_date} "
                f"(fonte: {re.source}, atualizado {re.source_time})."
            )
            text_parts.append(rating_str)
            pills.append(
                InteractivePill(
                    pill_id="pill_rating_source",
                    label=re.source,
                    value=re.new_rating,
                    pill_type="SOURCE_PROVENANCE",
                    modal_target="MODAL_SOURCE_PROOF",
                    metadata={"source_time": re.source_time, "asset": re.asset_name},
                )
            )

        if context.look_through_detail:
            lt = context.look_through_detail
            lt_str = f"O {lt.fii_name} tem {lt.pl_pct:.1f}% do PL no mesmo emissor (fonte: {lt.sources})."
            text_parts.append(lt_str)
            pills.append(
                InteractivePill(
                    pill_id="pill_look_through_source",
                    label=lt.sources,
                    value=lt.pl_pct,
                    pill_type="SOURCE_PROVENANCE",
                    modal_target="MODAL_SOURCE_PROOF",
                    metadata={"fii": lt.fii_name},
                )
            )

        text_parts.append("Você não tem concentração por ticker — tem concentração por devedor.")

        final_text = " ".join(text_parts)

        inference_log = {
            "user_id": user_id,
            "portfolio_version_hash": portfolio_hash,
            "template_id": self.TEMPLATE_ID,
            "subgraph_snapshot": asdict(context),
            "generated_text": final_text,
            "created_at": datetime.now().isoformat(),
        }

        return FalsifiablePhraseResult(
            text=final_text,
            interactive_pills=pills,
            inference_log=inference_log,
        )
