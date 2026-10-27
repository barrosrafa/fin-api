import pytest
from app.comparator.arbitration import ArbitrationEngine, SourceObservation, ArbitratedMetricResult


def test_arbitration_consensus_interval_and_anchor():
    engine = ArbitrationEngine()

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
        SourceObservation(
            source_id="INVESTIDOR10",
            value=8.50,
            freshness_score=80.0,
            has_public_methodology=False,
            historical_stability_score=75.0,
        ),
    ]

    result = engine.arbitrate(ticker="KNIP11", metric_name="DY_12M", observations=observations)

    assert isinstance(result, ArbitratedMetricResult)
    assert result.ticker == "KNIP11"
    assert result.metric_name == "DY_12M"
    assert result.consensus_min == 7.90
    assert result.consensus_max == 8.50
    assert result.consensus_iqr == pytest.approx(0.60, 0.01)

    # Anchor should be STATUS_INVEST due to highest composite score
    assert result.anchor_source == "STATUS_INVEST"
    assert result.anchor_value == 8.20
    assert result.confidence_score > 85.0
