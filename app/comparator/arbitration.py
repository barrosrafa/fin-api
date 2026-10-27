from dataclasses import dataclass
from typing import List


@dataclass
class SourceObservation:
    source_id: str
    value: float
    freshness_score: float # 0 - 100
    has_public_methodology: bool
    historical_stability_score: float # 0 - 100


@dataclass
class ArbitratedMetricResult:
    ticker: str
    metric_name: str
    consensus_min: float
    consensus_max: float
    consensus_iqr: float
    anchor_source: str
    anchor_value: float
    confidence_score: float
    methodology_version: str = "v1.0.0"


class ArbitrationEngine:
    """Deterministic arbitration engine selecting metric consensus intervals and scored anchors."""

    # Weights: w1 (Freshness) = 0.40, w2 (Methodology Doc) = 0.35, w3 (Stability) = 0.25
    W_FRESHNESS = 0.40
    W_METHODOLOGY = 0.35
    W_STABILITY = 0.25

    def arbitrate(
        self,
        ticker: str,
        metric_name: str,
        observations: List[SourceObservation],
    ) -> ArbitratedMetricResult:
        if not observations:
            raise ValueError("No observations provided for arbitration")

        values = [o.value for o in observations]
        consensus_min = min(values)
        consensus_max = max(values)
        consensus_iqr = consensus_max - consensus_min

        # Score each observation
        scored_obs = []
        for obs in observations:
            doc_score = 100.0 if obs.has_public_methodology else 0.0
            composite_score = (
                self.W_FRESHNESS * obs.freshness_score
                + self.W_METHODOLOGY * doc_score
                + self.W_STABILITY * obs.historical_stability_score
            )
            scored_obs.append((composite_score, obs))

        scored_obs.sort(key=lambda x: x[0], reverse=True)
        best_score, best_obs = scored_obs[0]

        return ArbitratedMetricResult(
            ticker=ticker,
            metric_name=metric_name,
            consensus_min=round(consensus_min, 4),
            consensus_max=round(consensus_max, 4),
            consensus_iqr=round(consensus_iqr, 4),
            anchor_source=best_obs.source_id,
            anchor_value=best_obs.value,
            confidence_score=round(best_score, 2),
        )
