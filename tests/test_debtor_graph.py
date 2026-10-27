import pytest
from app.portfolio.debtor_graph import DebtorGraphService, PortfolioPosition, EdgeInfo, UserOverride


def test_calculate_debtor_exposure_aggregated():
    # User holdings
    positions = [
        PortfolioPosition(ticker="KNIP11", asset_class="FII", weight_pct=22.0),
        PortfolioPosition(ticker="FUNDO_Y", asset_class="FUND_CVM_175", weight_pct=9.0),
        PortfolioPosition(ticker="CRI_Z", asset_class="DIRECT_CRI", weight_pct=3.0),
        PortfolioPosition(ticker="PETR4", asset_class="EQUITY", weight_pct=66.0),
    ]

    # Look-through edges
    edges = {
        "KNIP11": [
            EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=18.5, coverage_category="RESOLVED"),
            EdgeInfo(target_entity_name="MRV", weight_pct=9.25, coverage_category="RESOLVED"),
            EdgeInfo(target_entity_name=None, weight_pct=5.0, coverage_category="TEMPORARY_PENDING_CURATION"),
            EdgeInfo(target_entity_name=None, weight_pct=2.0, coverage_category="STRUCTURE_OPAQUE"),
        ],
        "FUNDO_Y": [
            EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=10.0, coverage_category="RESOLVED"),
        ],
        "CRI_Z": [
            EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=100.0, coverage_category="RESOLVED"),
        ],
    }

    service = DebtorGraphService(edges_lookup=edges)
    result = service.calculate_debtor_exposure(positions)

    # JHSF exposure:
    # From KNIP11: 22.0% * 18.5% = 4.07%
    # From FUNDO_Y: 9.0% * 10.0% = 0.90%
    # From CRI_Z: 3.0% * 100.0% = 3.00%
    # Total JHSF: 7.97%
    jhsf = next(d for d in result.debtors if d.entity_name == "Grupo JHSF")
    assert jhsf.total_exposure_pct == pytest.approx(7.97, 0.01)
    assert len(jhsf.contributing_assets) == 3

    # Check MRV exposure: 22.0% * 9.25% = 2.035%
    mrv = next(d for d in result.debtors if d.entity_name == "MRV")
    assert mrv.total_exposure_pct == pytest.approx(2.035, 0.01)

    # Level 0 equity PETR4:
    petr4 = next(d for d in result.debtors if d.entity_name == "PETR4")
    assert petr4.total_exposure_pct == 66.0
    assert petr4.is_level_0 is True

    # Check triple coverage (overall portfolio)
    # Total resolved: 66.0 (PETR4) + 4.07 + 2.035 + 0.90 + 3.0 = 76.005%
    # Pending: 22.0% * 5.0% = 1.10%
    # Opaque: 22.0% * 2.0% = 0.44%
    assert result.coverage.pct_resolved > 75.0
    assert result.coverage.pct_temporary_pending == pytest.approx(1.10, 0.01)
    assert result.coverage.pct_structure_opaque == pytest.approx(0.44, 0.01)


def test_user_override_excludes_edge():
    positions = [
        PortfolioPosition(ticker="KNIP11", asset_class="FII", weight_pct=20.0),
    ]
    edges = {
        "KNIP11": [
            EdgeInfo(target_entity_name="Grupo JHSF", weight_pct=10.0, coverage_category="RESOLVED"),
        ]
    }
    overrides = [
        UserOverride(source_asset_id="KNIP11", target_entity_name="Grupo JHSF", override_type="EXCLUDE_EDGE")
    ]

    service = DebtorGraphService(edges_lookup=edges)
    result = service.calculate_debtor_exposure(positions, overrides=overrides)

    jhsf_list = [d for d in result.debtors if d.entity_name == "Grupo JHSF"]
    assert len(jhsf_list) == 0


def test_bitemporal_as_of_querying():
    from datetime import datetime, timezone
    positions = [
        PortfolioPosition(ticker="KNIP11", asset_class="FII", weight_pct=20.0),
    ]
    # Edge v1 valid in Aug/2026, known on Sept 15, retified on Oct 20
    edge_v1 = EdgeInfo(
        target_entity_name="Grupo JHSF",
        weight_pct=18.0,
        coverage_category="RESOLVED",
        valid_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        valid_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        transaction_end=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )
    # Edge v2 retified on Oct 20
    edge_v2 = EdgeInfo(
        target_entity_name="Grupo JHSF",
        weight_pct=22.0,
        coverage_category="RESOLVED",
        valid_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        valid_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_start=datetime(2026, 10, 20, tzinfo=timezone.utc),
        transaction_end=datetime(9999, 12, 31, tzinfo=timezone.utc),
    )

    edges = {"KNIP11": [edge_v1, edge_v2]}
    service = DebtorGraphService(edges_lookup=edges)

    # Query as of Oct 01 (should see v1 with 18.0% -> exposure = 20% * 18% = 3.6%)
    res_oct_01 = service.calculate_debtor_exposure(
        positions,
        as_of_valid_time=datetime(2026, 8, 15, tzinfo=timezone.utc),
        as_of_transaction_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    jhsf_v1 = next(d for d in res_oct_01.debtors if d.entity_name == "Grupo JHSF")
    assert jhsf_v1.total_exposure_pct == pytest.approx(3.6, 0.01)

    # Query as of Oct 25 (should see v2 with 22.0% -> exposure = 20% * 22% = 4.4%)
    res_oct_25 = service.calculate_debtor_exposure(
        positions,
        as_of_valid_time=datetime(2026, 8, 15, tzinfo=timezone.utc),
        as_of_transaction_time=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )
    jhsf_v2 = next(d for d in res_oct_25.debtors if d.entity_name == "Grupo JHSF")
    assert jhsf_v2.total_exposure_pct == pytest.approx(4.4, 0.01)


def test_expanded_level_0_classes():
    positions = [
        PortfolioPosition(ticker="TESOURO_IPCA", asset_class="FIXED_INCOME", weight_pct=30.0),
        PortfolioPosition(ticker="BOVA11", asset_class="ETF", weight_pct=20.0),
        PortfolioPosition(ticker="CAIXA", asset_class="CASH", weight_pct=10.0),
    ]
    service = DebtorGraphService()
    result = service.calculate_debtor_exposure(positions)
    # All three should be resolved as level-0 without falling into pending curation
    assert result.coverage.pct_resolved == 60.0
    assert result.coverage.pct_temporary_pending == 0.0
    assert len(result.debtors) == 3
