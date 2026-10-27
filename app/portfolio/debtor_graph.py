from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PortfolioPosition:
    ticker: str
    asset_class: str # FII, FUND_CVM_175, DIRECT_CRI, EQUITY, FIXED_INCOME
    weight_pct: float # Percent of total portfolio


@dataclass
class EdgeInfo:
    target_entity_name: Optional[str]
    weight_pct: float # Percent of fund/asset PL
    coverage_category: str = "RESOLVED" # RESOLVED, TEMPORARY_PENDING_CURATION, STRUCTURE_OPAQUE


@dataclass
class UserOverride:
    source_asset_id: str
    target_entity_name: str
    override_type: str # EXCLUDE_EDGE, REMAP_ENTITY, OVERRIDE_WEIGHT
    override_weight_pct: Optional[float] = None
    remapped_entity_name: Optional[str] = None


@dataclass
class ContributingAsset:
    ticker: str
    asset_class: str
    allocation_pct: float
    effective_exposure_pct: float


@dataclass
class DebtorExposure:
    entity_name: str
    total_exposure_pct: float
    is_level_0: bool = False
    contributing_assets: List[ContributingAsset] = field(default_factory=list)


@dataclass
class CoverageSummary:
    pct_resolved: float
    pct_temporary_pending: float
    pct_structure_opaque: float


@dataclass
class PortfolioDebtorAnalysisResult:
    debtors: List[DebtorExposure]
    coverage: CoverageSummary


class DebtorGraphService:
    """Service for bitemporal look-through debtor graph traversal and concentration analysis."""

    def __init__(self, edges_lookup: Optional[Dict[str, List[EdgeInfo]]] = None):
        self.edges_lookup = edges_lookup or {}

    def calculate_debtor_exposure(
        self,
        positions: List[PortfolioPosition],
        overrides: Optional[List[UserOverride]] = None,
    ) -> PortfolioDebtorAnalysisResult:
        overrides_map: Dict[tuple, UserOverride] = {}
        if overrides:
            for o in overrides:
                overrides_map[(o.source_asset_id, o.target_entity_name)] = o

        debtor_totals: Dict[str, float] = {}
        contributions: Dict[str, List[ContributingAsset]] = {}
        is_level_0_map: Dict[str, bool] = {}

        total_resolved = 0.0
        total_pending = 0.0
        total_opaque = 0.0

        for pos in positions:
            ticker = pos.ticker
            pos_weight = pos.weight_pct

            # Level 0 assets (direct equities, sovereign bonds)
            if pos.asset_class in ("EQUITY", "DIRECT_EQUITY", "SOVEREIGN_BOND"):
                entity_name = ticker
                debtor_totals[entity_name] = debtor_totals.get(entity_name, 0.0) + pos_weight
                is_level_0_map[entity_name] = True
                contrib = ContributingAsset(
                    ticker=ticker,
                    asset_class=pos.asset_class,
                    allocation_pct=pos_weight,
                    effective_exposure_pct=pos_weight,
                )
                contributions.setdefault(entity_name, []).append(contrib)
                total_resolved += pos_weight
                continue

            edges = self.edges_lookup.get(ticker, [])
            if not edges:
                # Treated as unmapped/pending
                total_pending += pos_weight
                continue

            for edge in edges:
                override = overrides_map.get((ticker, edge.target_entity_name))
                if override and override.override_type == "EXCLUDE_EDGE":
                    continue

                target_name = edge.target_entity_name
                if override and override.override_type == "REMAP_ENTITY" and override.remapped_entity_name:
                    target_name = override.remapped_entity_name

                weight = edge.weight_pct
                if override and override.override_type == "OVERRIDE_WEIGHT" and override.override_weight_pct is not None:
                    weight = override.override_weight_pct

                effective_pct = (pos_weight * weight) / 100.0

                if edge.coverage_category == "RESOLVED" and target_name:
                    debtor_totals[target_name] = debtor_totals.get(target_name, 0.0) + effective_pct
                    is_level_0_map[target_name] = False
                    contrib = ContributingAsset(
                        ticker=ticker,
                        asset_class=pos.asset_class,
                        allocation_pct=pos_weight,
                        effective_exposure_pct=round(effective_pct, 4),
                    )
                    contributions.setdefault(target_name, []).append(contrib)
                    total_resolved += effective_pct
                elif edge.coverage_category == "STRUCTURE_OPAQUE":
                    total_opaque += effective_pct
                else:
                    total_pending += effective_pct

        debtors_list = []
        for name, total_exp in debtor_totals.items():
            debtors_list.append(
                DebtorExposure(
                    entity_name=name,
                    total_exposure_pct=round(total_exp, 4),
                    is_level_0=is_level_0_map.get(name, False),
                    contributing_assets=contributions.get(name, []),
                )
            )

        debtors_list.sort(key=lambda d: d.total_exposure_pct, reverse=True)

        return PortfolioDebtorAnalysisResult(
            debtors=debtors_list,
            coverage=CoverageSummary(
                pct_resolved=round(total_resolved, 4),
                pct_temporary_pending=round(total_pending, 4),
                pct_structure_opaque=round(total_opaque, 4),
            ),
        )
