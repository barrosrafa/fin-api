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
