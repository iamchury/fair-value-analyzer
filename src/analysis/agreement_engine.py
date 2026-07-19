from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from statistics import mean, median

from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.config.agreement_engine import AgreementEngineConfiguration


class AgreementLevel(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT = "INSUFFICIENT"


class ModelRelationship(str, Enum):
    STRONG_AGREEMENT = "STRONG_AGREEMENT"
    MODERATE_AGREEMENT = "MODERATE_AGREEMENT"
    WEAK_AGREEMENT = "WEAK_AGREEMENT"
    DIVERGENT = "DIVERGENT"
    UNAVAILABLE = "UNAVAILABLE"


class OutlierStatus(str, Enum):
    NOT_OUTLIER = "NOT_OUTLIER"
    POSSIBLE_OUTLIER = "POSSIBLE_OUTLIER"
    OUTLIER = "OUTLIER"
    NOT_EVALUATED = "NOT_EVALUATED"


class ClusterType(str, Enum):
    INTRINSIC_CLUSTER = "INTRINSIC_CLUSTER"
    SUPPORTING_REFERENCE = "SUPPORTING_REFERENCE"
    MARKET_EXPECTATION = "MARKET_EXPECTATION"
    UNCLASSIFIED = "UNCLASSIFIED"


class AgreementResultStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    ERROR = "ERROR"


class MarketExpectationDirection(str, Enum):
    ABOVE_INTRINSIC = "ABOVE_INTRINSIC"
    BELOW_INTRINSIC = "BELOW_INTRINSIC"
    NEAR_INTRINSIC = "NEAR_INTRINSIC"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ClusterMemberValue:
    model_type: ValuationModelType
    value_type: ValuationValueType
    cluster_type: ClusterType
    selected_value: float


@dataclass(frozen=True)
class PairwiseComparison:
    model_a: ValuationModelType
    model_b: ValuationModelType
    value_a: float | None
    value_b: float | None
    absolute_difference: float | None
    percentage_difference: float | None
    relationship: ModelRelationship


@dataclass(frozen=True)
class IntrinsicCluster:
    cluster_type: ClusterType
    member_model_types: tuple[ValuationModelType, ...]
    member_values: tuple[ClusterMemberValue, ...]
    minimum_value: float | None
    maximum_value: float | None
    mean_value: float | None
    median_value: float | None
    spread_percentage: float | None
    pairwise_comparisons: tuple[PairwiseComparison, ...]
    agreement_level: AgreementLevel
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ModelOutlier:
    model_type: ValuationModelType
    value: float | None
    comparison_median: float | None
    difference_percentage: float | None
    status: OutlierStatus


@dataclass(frozen=True)
class MarketExpectationAnalysis:
    model_type: ValuationModelType
    selected_value: float | None
    intrinsic_median: float | None
    absolute_difference: float | None
    percentage_difference: float | None
    direction: MarketExpectationDirection
    outlier_status: OutlierStatus
    confidence: ValuationConfidenceLevel
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AgreementResult:
    status: AgreementResultStatus
    core_intrinsic_agreement: AgreementLevel
    extended_intrinsic_agreement: AgreementLevel
    overall_agreement: AgreementLevel
    intrinsic_cluster: IntrinsicCluster
    pairwise_comparisons: tuple[PairwiseComparison, ...]
    model_outliers: tuple[ModelOutlier, ...]
    market_expectation_analyses: tuple[MarketExpectationAnalysis, ...]
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    generated_at: datetime


def analyze_agreement(
    collection: ValuationSnapshotCollection,
    configuration: AgreementEngineConfiguration,
    generated_at: datetime | None = None,
) -> AgreementResult:
    generated = datetime.now(timezone.utc) if generated_at is None else generated_at
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    if not configuration.enabled:
        empty = _cluster((), configuration, AgreementLevel.INSUFFICIENT)
        return AgreementResult(
            status=AgreementResultStatus.INSUFFICIENT,
            core_intrinsic_agreement=AgreementLevel.INSUFFICIENT,
            extended_intrinsic_agreement=AgreementLevel.INSUFFICIENT,
            overall_agreement=AgreementLevel.INSUFFICIENT,
            intrinsic_cluster=empty,
            pairwise_comparisons=(),
            model_outliers=(),
            market_expectation_analyses=(),
            rationale=("Agreement engine is disabled.",),
            warnings=("Agreement engine is disabled.",),
            generated_at=generated,
        )

    usable = tuple(snapshot for snapshot in collection.snapshots if _is_usable(snapshot))
    core = tuple(
        snapshot
        for snapshot in usable
        if snapshot.value_type == ValuationValueType.INTRINSIC_VALUE
    )
    references = tuple(
        snapshot
        for snapshot in usable
        if snapshot.value_type == ValuationValueType.REFERENCE_VALUE
    )
    market = tuple(
        snapshot
        for snapshot in usable
        if snapshot.value_type == ValuationValueType.MARKET_EXPECTATION
    )
    extended = core + references if configuration.include_reference_in_intrinsic_cluster else core
    core_agreement = _aggregate_agreement(core, configuration)
    extended_agreement = _aggregate_agreement(extended, configuration)
    overall = core_agreement
    status = (
        AgreementResultStatus.COMPLETE
        if len(core) >= configuration.minimum_primary_models
        else AgreementResultStatus.INSUFFICIENT
    )
    warnings = _warnings(collection, usable, core, references, market, configuration)
    intrinsic_cluster = _cluster(extended, configuration, extended_agreement)
    pairwise = intrinsic_cluster.pairwise_comparisons
    core_median = _median_value(core)
    cluster_median = intrinsic_cluster.median_value or core_median
    outliers = _outliers(usable, core_median, cluster_median, configuration)
    market_analyses = _market_analyses(market, cluster_median, outliers, configuration)
    return AgreementResult(
        status=status,
        core_intrinsic_agreement=core_agreement,
        extended_intrinsic_agreement=extended_agreement,
        overall_agreement=overall,
        intrinsic_cluster=intrinsic_cluster,
        pairwise_comparisons=pairwise,
        model_outliers=outliers,
        market_expectation_analyses=market_analyses,
        rationale=_rationale(
            core,
            references,
            market_analyses,
            outliers,
            cluster_median,
            _currency(usable),
        ),
        warnings=warnings,
        generated_at=generated,
    )


def symmetric_percentage_difference(a: object, b: object) -> float | None:
    if not _is_positive_number(a) or not _is_positive_number(b):
        return None
    return abs(float(a) - float(b)) / ((float(a) + float(b)) / 2) * 100


def classify_pairwise_relationship(
    percentage_difference: float | None,
    configuration: AgreementEngineConfiguration,
) -> ModelRelationship:
    if percentage_difference is None:
        return ModelRelationship.UNAVAILABLE
    if percentage_difference <= configuration.strong_threshold_pct:
        return ModelRelationship.STRONG_AGREEMENT
    if percentage_difference <= configuration.moderate_threshold_pct:
        return ModelRelationship.MODERATE_AGREEMENT
    if percentage_difference <= configuration.weak_threshold_pct:
        return ModelRelationship.WEAK_AGREEMENT
    return ModelRelationship.DIVERGENT


def _is_usable(snapshot: ValuationSnapshot) -> bool:
    return (
        snapshot.status
        in (ValuationSnapshotStatus.COMPLETE, ValuationSnapshotStatus.PARTIAL)
        and _is_positive_number(snapshot.selected_fair_value)
    )


def _cluster(
    snapshots: tuple[ValuationSnapshot, ...],
    configuration: AgreementEngineConfiguration,
    agreement: AgreementLevel,
) -> IntrinsicCluster:
    values = tuple(float(snapshot.selected_fair_value) for snapshot in snapshots)
    if not values:
        return IntrinsicCluster(
            ClusterType.INTRINSIC_CLUSTER,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            (),
            AgreementLevel.INSUFFICIENT,
            ("No usable intrinsic valuation snapshots are available.",),
        )
    minimum = min(values)
    maximum = max(values)
    mean_value = mean(values)
    members = tuple(
        ClusterMemberValue(
            snapshot.model_type,
            snapshot.value_type,
            _cluster_type(snapshot),
            float(snapshot.selected_fair_value),
        )
        for snapshot in snapshots
    )
    pairwise = _pairwise_comparisons(snapshots, configuration)
    return IntrinsicCluster(
        ClusterType.INTRINSIC_CLUSTER,
        tuple(snapshot.model_type for snapshot in snapshots),
        members,
        minimum,
        maximum,
        mean_value,
        median(values),
        (maximum - minimum) / mean_value * 100 if mean_value > 0 else None,
        pairwise,
        agreement,
        (),
    )


def _pairwise_comparisons(
    snapshots: tuple[ValuationSnapshot, ...],
    configuration: AgreementEngineConfiguration,
) -> tuple[PairwiseComparison, ...]:
    comparisons: list[PairwiseComparison] = []
    for index, left in enumerate(snapshots):
        for right in snapshots[index + 1 :]:
            pct = symmetric_percentage_difference(
                left.selected_fair_value,
                right.selected_fair_value,
            )
            absolute = (
                None
                if pct is None
                else abs(float(left.selected_fair_value) - float(right.selected_fair_value))
            )
            comparisons.append(
                PairwiseComparison(
                    left.model_type,
                    right.model_type,
                    left.selected_fair_value,
                    right.selected_fair_value,
                    absolute,
                    pct,
                    classify_pairwise_relationship(pct, configuration),
                )
            )
    return tuple(comparisons)


def _aggregate_agreement(
    snapshots: tuple[ValuationSnapshot, ...],
    configuration: AgreementEngineConfiguration,
) -> AgreementLevel:
    if len(snapshots) < configuration.minimum_primary_models:
        return AgreementLevel.INSUFFICIENT
    diffs = tuple(
        difference
        for difference in (
            symmetric_percentage_difference(left.selected_fair_value, right.selected_fair_value)
            for index, left in enumerate(snapshots)
            for right in snapshots[index + 1 :]
        )
        if difference is not None
    )
    if not diffs:
        return AgreementLevel.INSUFFICIENT
    max_diff = max(diffs)
    median_diff = median(diffs)
    strong_count = sum(
        1 for difference in diffs if difference <= configuration.strong_threshold_pct
    )
    if all(diff <= configuration.strong_threshold_pct for diff in diffs) or (
        max_diff <= configuration.moderate_threshold_pct
        and strong_count >= len(diffs) / 2
    ):
        return AgreementLevel.STRONG
    if max_diff <= configuration.moderate_threshold_pct or (
        max_diff <= configuration.weak_threshold_pct
        and median_diff <= configuration.moderate_threshold_pct
    ):
        return AgreementLevel.MODERATE
    if max_diff <= configuration.weak_threshold_pct:
        return AgreementLevel.WEAK
    return AgreementLevel.CONFLICTED


def _outliers(
    snapshots: tuple[ValuationSnapshot, ...],
    core_median: float | None,
    cluster_median: float | None,
    configuration: AgreementEngineConfiguration,
) -> tuple[ModelOutlier, ...]:
    outliers: list[ModelOutlier] = []
    for snapshot in snapshots:
        comparison_median = (
            cluster_median
            if snapshot.value_type == ValuationValueType.MARKET_EXPECTATION
            else core_median
        )
        difference = _one_sided_difference(snapshot.selected_fair_value, comparison_median)
        outliers.append(
            ModelOutlier(
                snapshot.model_type,
                snapshot.selected_fair_value,
                comparison_median,
                difference,
                _classify_outlier(difference, configuration),
            )
        )
    return tuple(outliers)


def _market_analyses(
    snapshots: tuple[ValuationSnapshot, ...],
    cluster_median: float | None,
    outliers: tuple[ModelOutlier, ...],
    configuration: AgreementEngineConfiguration,
) -> tuple[MarketExpectationAnalysis, ...]:
    analyses: list[MarketExpectationAnalysis] = []
    outlier_by_model = {outlier.model_type: outlier for outlier in outliers}
    for snapshot in snapshots:
        percentage = _one_sided_difference(snapshot.selected_fair_value, cluster_median)
        absolute = (
            None
            if snapshot.selected_fair_value is None or cluster_median is None
            else float(snapshot.selected_fair_value) - cluster_median
        )
        analyses.append(
            MarketExpectationAnalysis(
                snapshot.model_type,
                snapshot.selected_fair_value,
                cluster_median,
                absolute,
                percentage,
                _market_direction(snapshot.selected_fair_value, cluster_median, percentage, configuration),
                outlier_by_model.get(
                    snapshot.model_type,
                    ModelOutlier(snapshot.model_type, None, None, None, OutlierStatus.NOT_EVALUATED),
                ).status,
                snapshot.confidence,
                tuple(snapshot.warnings),
            )
        )
    return tuple(analyses)


def _warnings(
    collection: ValuationSnapshotCollection,
    usable: tuple[ValuationSnapshot, ...],
    core: tuple[ValuationSnapshot, ...],
    references: tuple[ValuationSnapshot, ...],
    market: tuple[ValuationSnapshot, ...],
    configuration: AgreementEngineConfiguration,
) -> tuple[str, ...]:
    warnings = []
    if len(core) < configuration.minimum_primary_models:
        warnings.append("Fewer than the configured minimum primary intrinsic models are usable.")
    if len(usable) < len(collection.snapshots):
        warnings.append("Some snapshots were excluded because their selected values were unusable.")
    if references and not core:
        warnings.append("Reference values are present, but no intrinsic model median is available.")
    if market and not (core or references):
        warnings.append("Market expectation values are present without an intrinsic comparison cluster.")
    return tuple(warnings)


def _rationale(
    core: tuple[ValuationSnapshot, ...],
    references: tuple[ValuationSnapshot, ...],
    market_analyses: tuple[MarketExpectationAnalysis, ...],
    outliers: tuple[ModelOutlier, ...],
    cluster_median: float | None,
    currency: str | None,
) -> tuple[str, ...]:
    if cluster_median is None:
        return ("Agreement analysis has insufficient intrinsic values.",)
    lines: list[str] = []
    currency_suffix = f" {currency}" if currency else ""
    if len(core) >= 2:
        names = " and ".join(_display_model(snapshot.model_type) for snapshot in core[:2])
        lines.append(f"{names} strongly agree near {cluster_median:.2f}{currency_suffix}.")
    outlier_by_model = {outlier.model_type: outlier for outlier in outliers}
    for snapshot in references:
        outlier = outlier_by_model.get(snapshot.model_type)
        if outlier and outlier.difference_percentage is not None:
            direction = "below" if snapshot.selected_fair_value < cluster_median else "above"
            lines.append(
                f"{_display_model(snapshot.model_type)} is approximately "
                f"{outlier.difference_percentage:.2f}% {direction} the intrinsic median "
                "and remains within the supporting valuation cluster."
            )
    for analysis in market_analyses:
        if analysis.percentage_difference is None:
            continue
        direction = "above" if analysis.direction == MarketExpectationDirection.ABOVE_INTRINSIC else "below"
        status = "market-expectation outlier" if analysis.outlier_status == OutlierStatus.OUTLIER else "market expectation"
        lines.append(
            f"{_display_model(analysis.model_type)} is approximately "
            f"{analysis.percentage_difference:.2f}% {direction} the intrinsic median "
            f"and is classified as a {status}."
        )
        if analysis.confidence != ValuationConfidenceLevel.UNKNOWN:
            reason = ""
            if any("dispersion is extreme" in warning.lower() for warning in analysis.warnings):
                reason = " because target dispersion is extreme"
            lines.append(
                f"The analyst model has {analysis.confidence.value} confidence{reason}."
            )
    return tuple(lines) or ("Agreement analysis completed.",)


def _cluster_type(snapshot: ValuationSnapshot) -> ClusterType:
    if snapshot.value_type == ValuationValueType.INTRINSIC_VALUE:
        return ClusterType.INTRINSIC_CLUSTER
    if snapshot.value_type == ValuationValueType.REFERENCE_VALUE:
        return ClusterType.SUPPORTING_REFERENCE
    if snapshot.value_type == ValuationValueType.MARKET_EXPECTATION:
        return ClusterType.MARKET_EXPECTATION
    return ClusterType.UNCLASSIFIED


def _median_value(snapshots: tuple[ValuationSnapshot, ...]) -> float | None:
    values = [float(snapshot.selected_fair_value) for snapshot in snapshots if _is_usable(snapshot)]
    return median(values) if values else None


def _one_sided_difference(value: object, comparison_median: float | None) -> float | None:
    if not _is_positive_number(value) or not _is_positive_number(comparison_median):
        return None
    return abs(float(value) - float(comparison_median)) / float(comparison_median) * 100


def _classify_outlier(
    difference_percentage: float | None,
    configuration: AgreementEngineConfiguration,
) -> OutlierStatus:
    if difference_percentage is None:
        return OutlierStatus.NOT_EVALUATED
    if difference_percentage < configuration.outlier_threshold_pct:
        return OutlierStatus.NOT_OUTLIER
    if difference_percentage < configuration.extreme_outlier_threshold_pct:
        return OutlierStatus.POSSIBLE_OUTLIER
    return OutlierStatus.OUTLIER


def _market_direction(
    value: float | None,
    cluster_median: float | None,
    difference_percentage: float | None,
    configuration: AgreementEngineConfiguration,
) -> MarketExpectationDirection:
    if not _is_positive_number(value) or not _is_positive_number(cluster_median):
        return MarketExpectationDirection.UNKNOWN
    if difference_percentage is not None and difference_percentage <= configuration.moderate_threshold_pct:
        return MarketExpectationDirection.NEAR_INTRINSIC
    return (
        MarketExpectationDirection.ABOVE_INTRINSIC
        if float(value) > float(cluster_median)
        else MarketExpectationDirection.BELOW_INTRINSIC
    )


def _is_positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and value > 0
    )


def _display_model(model_type: ValuationModelType) -> str:
    return {
        ValuationModelType.AUTOMATIC_PER: "Automatic PER",
        ValuationModelType.RESEARCH_PER: "Research PER",
        ValuationModelType.DCF_REFERENCE: "DCF Reference",
        ValuationModelType.ANALYST_CONSENSUS: "Analyst Consensus",
    }.get(model_type, model_type.value.replace("_", " ").title())


def _currency(snapshots: tuple[ValuationSnapshot, ...]) -> str | None:
    for snapshot in snapshots:
        if snapshot.currency:
            return snapshot.currency
    return None
