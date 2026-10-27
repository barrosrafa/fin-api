import time
import pytest
from app.intelligence.falsifiable_phrase import FalsifiablePhraseEngine, PhraseContext, DecomposedAsset, RatingEvent, LookThroughDetail


def test_generate_falsifiable_phrase_deterministic_and_fast():
    engine = FalsifiablePhraseEngine()

    ctx = PhraseContext(
        macro_class="crédito imobiliário de papel",
        total_pct=34.0,
        decomposed_assets=[
            DecomposedAsset(name="FII X", pct=22.0),
            DecomposedAsset(name="fundo CVM 175 Y", pct=9.0),
            DecomposedAsset(name="CRI Z", pct=3.0),
        ],
        rating_event=RatingEvent(
            asset_name="CRI Z",
            old_rating="AA",
            new_rating="A",
            event_date="12/09",
            source="Brick360",
            source_time="14:32",
        ),
        look_through_detail=LookThroughDetail(
            fii_name="FII X",
            pl_pct=18.0,
            sources="Clube FII / SiiLA",
        ),
        canonical_debtor="Grupo JHSF",
        user_threshold_pct=25.0,
    )

    start_t = time.perf_counter()
    result = engine.generate_phrase(user_id="user-123", portfolio_hash="hash-abc", context=ctx)
    elapsed_ms = (time.perf_counter() - start_t) * 1000

    assert elapsed_ms < 10.0, f"Execution took {elapsed_ms}ms, expected < 10ms"

    expected_snippet = "Sua exposição a crédito imobiliário de papel é 34.0% do patrimônio — soma de FII X (22.0%), fundo CVM 175 Y (9.0%) e CRI Z (3.0%). O rating do CRI Z caiu de AA para A em 12/09 (fonte: Brick360, atualizado 14:32). O FII X tem 18.0% do PL no mesmo emissor (fonte: Clube FII / SiiLA). Você não tem concentração por ticker — tem concentração por devedor."
    assert result.text == expected_snippet
    assert result.inference_log["user_id"] == "user-123"
    assert result.inference_log["portfolio_version_hash"] == "hash-abc"
    assert len(result.interactive_pills) >= 4
