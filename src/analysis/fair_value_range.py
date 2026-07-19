from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from src.analysis.agreement_engine import AgreementLevel, AgreementResult, OutlierStatus
from src.analysis.momentum_reference import RsiCrossDirection, RsiMomentumReference
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.config.fair_value_range import FairValueRangeConfiguration


class FairValueRangeStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    ERROR = "ERROR"


class MarketPosition(str, Enum):
    DEEPLY_UNDERVALUED = "DEEPLY_UNDERVALUED"
    UNDERVALUED = "UNDERVALUED"
    NEAR_FAIR_VALUE = "NEAR_FAIR_VALUE"
    ABOVE_FAIR_VALUE = "ABOVE_FAIR_VALUE"
    SIGNIFICANTLY_OVERVALUED = "SIGNIFICANTLY_OVERVALUED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class IncludedRangeModel:
    model_type: ValuationModelType
    value_type: ValuationValueType
    selected_value: float
    confidence: ValuationConfidenceLevel
    weight: float


@dataclass(frozen=True)
class FairValueRangeResult:
    symbol: str
    status: FairValueRangeStatus
    conservative_value: float | None
    base_value: float | None
    optimistic_intrinsic_value: float | None
    intrinsic_floor: float | None
    intrinsic_ceiling: float | None
    intrinsic_range_width: float | None
    intrinsic_range_width_pct: float | None
    market_expectation_value: float | None
    market_expectation_confidence: ValuationConfidenceLevel | None
    market_expectation_outlier_status: OutlierStatus | None
    current_price: float | None
    current_vs_conservative_pct: float | None
    current_vs_base_pct: float | None
    current_vs_optimistic_pct: float | None
    market_position: MarketPosition
    agreement_level: AgreementLevel | None
    core_model_count: int
    supporting_reference_count: int
    excluded_models: tuple[ValuationModelType, ...]
    included_models: tuple[IncludedRangeModel, ...]
    momentum_reference_price: float | None
    momentum_reference_date: object | None
    momentum_cross_direction: RsiCrossDirection | None
    momentum_current_rsi: float | None
    current_vs_momentum_reference: float | None
    current_vs_momentum_reference_pct: float | None
    methodology: str
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    calculation_steps: tuple[str, ...]
    generated_at: datetime


def calculate_fair_value_range(
    collection: ValuationSnapshotCollection | None,
    agreement: AgreementResult | None,
    current_price: float | None,
    configuration: FairValueRangeConfiguration,
    momentum_reference: RsiMomentumReference | None = None,
    generated_at: datetime | None = None,
) -> FairValueRangeResult:
    generated = datetime.now(timezone.utc) if generated_at is None else generated_at
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    symbol = getattr(collection, "symbol", "UNKNOWN")
    if collection is None or not configuration.enabled:
        return _empty(symbol, current_price, generated, "Fair value range is unavailable.")
    outlier_status = _outlier_statuses(agreement)
    core, references, market, excluded = _partition(collection, configuration, outlier_status)
    status = (
        FairValueRangeStatus.COMPLETE
        if len(core) >= configuration.minimum_intrinsic_models
        else FairValueRangeStatus.PARTIAL
        if core
        else FairValueRangeStatus.INSUFFICIENT
    )
    warnings = []
    if len(core) < configuration.minimum_intrinsic_models:
        warnings.append("Fewer than the configured minimum intrinsic models are usable.")
    support_values = core + references if configuration.include_reference_values else core
    conservative = min((item.selected_value for item in support_values), default=None)
    base = _weighted_median(core)
    optimistic = max((item.selected_value for item in core), default=None)
    floor = conservative
    ceiling = optimistic
    width = None if floor is None or ceiling is None else ceiling - floor
    width_pct = _percent(width, base)
    market_value = market[0].selected_value if market and configuration.show_market_expectation_separately else None
    market_confidence = market[0].confidence if market and configuration.show_market_expectation_separately else None
    market_outlier_status = (
        outlier_status.get(market[0].model_type)
        if market and configuration.show_market_expectation_separately
        else None
    )
    momentum_price = (
        momentum_reference.reference_price
        if momentum_reference is not None and configuration.show_momentum_reference_separately
        else None
    )
    momentum_date = (
        momentum_reference.reference_date
        if momentum_reference is not None and configuration.show_momentum_reference_separately
        else None
    )
    momentum_direction = (
        momentum_reference.cross_direction
        if momentum_reference is not None and configuration.show_momentum_reference_separately
        else None
    )
    momentum_current_rsi = (
        momentum_reference.current_rsi
        if momentum_reference is not None and configuration.show_momentum_reference_separately
        else None
    )
    current_vs_base = _difference_pct(current_price, base)
    result = FairValueRangeResult(
        symbol=symbol,
        status=status,
        conservative_value=conservative,
        base_value=base,
        optimistic_intrinsic_value=optimistic,
        intrinsic_floor=floor,
        intrinsic_ceiling=ceiling,
        intrinsic_range_width=width,
        intrinsic_range_width_pct=width_pct,
        market_expectation_value=market_value,
        market_expectation_confidence=market_confidence,
        market_expectation_outlier_status=market_outlier_status,
        current_price=current_price,
        current_vs_conservative_pct=_difference_pct(current_price, conservative),
        current_vs_base_pct=current_vs_base,
        current_vs_optimistic_pct=_difference_pct(current_price, optimistic),
        market_position=_market_position(current_vs_base, configuration),
        agreement_level=None if agreement is None else agreement.overall_agreement,
        core_model_count=len(core),
        supporting_reference_count=len(references),
        excluded_models=tuple(excluded),
        included_models=tuple(support_values),
        momentum_reference_price=momentum_price,
        momentum_reference_date=momentum_date,
        momentum_cross_direction=momentum_direction,
        momentum_current_rsi=momentum_current_rsi,
        current_vs_momentum_reference=_difference(current_price, momentum_price),
        current_vs_momentum_reference_pct=_difference_pct(current_price, momentum_price),
        methodology="Confidence-weighted median base with lower support and upper intrinsic support",
        rationale=(),
        warnings=tuple(warnings),
        calculation_steps=("Filter snapshots", "Apply agreement outliers", "Weighted median", "Market position"),
        generated_at=generated,
    )
    return _with_rationale(result, market, agreement, momentum_reference)


def confidence_weight(confidence: ValuationConfidenceLevel, config: FairValueRangeConfiguration) -> float:
    if confidence == ValuationConfidenceLevel.HIGH:
        return config.high_confidence_weight
    if confidence == ValuationConfidenceLevel.MEDIUM:
        return config.medium_confidence_weight
    if confidence == ValuationConfidenceLevel.LOW:
        return config.low_confidence_weight
    return config.unknown_confidence_weight


def _partition(
    collection: ValuationSnapshotCollection,
    config: FairValueRangeConfiguration,
    outliers: dict[ValuationModelType, OutlierStatus],
) -> tuple[list[IncludedRangeModel], list[IncludedRangeModel], list[IncludedRangeModel], list[ValuationModelType]]:
    core = []
    references = []
    market = []
    excluded = []
    for snapshot in collection.snapshots:
        if not _usable(snapshot):
            excluded.append(snapshot.model_type)
            continue
        if snapshot.value_type == ValuationValueType.MARKET_EXPECTATION:
            market.append(
                IncludedRangeModel(
                    snapshot.model_type,
                    snapshot.value_type,
                    float(snapshot.selected_fair_value),
                    snapshot.confidence,
                    confidence_weight(snapshot.confidence, config),
                )
            )
            continue
        if config.exclude_outliers and outliers.get(snapshot.model_type) == OutlierStatus.OUTLIER:
            excluded.append(snapshot.model_type)
            continue
        if (
            snapshot.value_type == ValuationValueType.INTRINSIC_VALUE
            and snapshot.confidence == ValuationConfidenceLevel.LOW
            and not config.include_low_confidence_intrinsic
        ):
            excluded.append(snapshot.model_type)
            continue
        weight = confidence_weight(snapshot.confidence, config)
        item = IncludedRangeModel(
            snapshot.model_type,
            snapshot.value_type,
            float(snapshot.selected_fair_value),
            snapshot.confidence,
            weight,
        )
        if snapshot.value_type == ValuationValueType.INTRINSIC_VALUE:
            core.append(item)
        elif snapshot.value_type == ValuationValueType.REFERENCE_VALUE and config.include_reference_values:
            references.append(
                IncludedRangeModel(
                    item.model_type,
                    item.value_type,
                    item.selected_value,
                    item.confidence,
                    item.weight * config.reference_value_weight,
                )
            )
    return core, references, market, excluded


def _weighted_median(items: list[IncludedRangeModel]) -> float | None:
    if not items:
        return None
    ordered = sorted(items, key=lambda item: (item.selected_value, item.model_type.value))
    total = sum(item.weight for item in ordered)
    threshold = total / 2
    cumulative = 0.0
    for item in ordered:
        cumulative += item.weight
        if cumulative >= threshold:
            return item.selected_value
    return ordered[-1].selected_value


def _market_position(value: float | None, config: FairValueRangeConfiguration) -> MarketPosition:
    if value is None:
        return MarketPosition.UNAVAILABLE
    value = round(value, 10)
    if value <= config.deep_undervalued_pct:
        return MarketPosition.DEEPLY_UNDERVALUED
    if value < config.undervalued_pct:
        return MarketPosition.UNDERVALUED
    if value <= config.near_fair_upper_pct:
        return MarketPosition.NEAR_FAIR_VALUE
    if value <= config.above_fair_pct:
        return MarketPosition.ABOVE_FAIR_VALUE
    return MarketPosition.SIGNIFICANTLY_OVERVALUED


def _with_rationale(
    result: FairValueRangeResult,
    market: list[IncludedRangeModel],
    agreement: AgreementResult | None,
    momentum: RsiMomentumReference | None,
) -> FairValueRangeResult:
    lines = []
    if result.base_value is not None:
        lines.append(f"Automatic PER and Research PER place the base intrinsic value near {result.base_value:.2f}.")
    if result.conservative_value is not None and result.conservative_value != result.base_value:
        lines.append(f"DCF Reference provides conservative support near {result.conservative_value:.2f}.")
    if result.current_vs_base_pct is not None:
        price_direction = "above" if result.current_vs_base_pct >= 0 else "below"
        lines.append(
            f"The current price is {abs(result.current_vs_base_pct):.2f}% {price_direction} the base value and is classified as {_market_position_text(result.market_position)}."
        )
    if market:
        outlier = _market_outlier_text(market[0].model_type, agreement)
        diff = _difference_pct(market[0].selected_value, result.base_value)
        if diff is not None:
            lines.append(
                f"Analyst Consensus is {diff:.2f}% above the base value, but remains a {market[0].confidence.value.lower()}-confidence market expectation {outlier}."
            )
    if momentum is not None and momentum.reference_price is not None:
        lines.append("The RSI 50 reference is reported separately as a momentum benchmark and does not affect intrinsic valuation.")
    return FairValueRangeResult(**{**result.__dict__, "rationale": tuple(lines)})


def _market_outlier_text(model_type: ValuationModelType, agreement: AgreementResult | None) -> str:
    if agreement is None:
        return "reference"
    for analysis in agreement.market_expectation_analyses:
        if analysis.model_type == model_type:
            return f"{analysis.outlier_status.value.lower().replace('_', '-')}"
    return "reference"


def _market_position_text(position: MarketPosition) -> str:
    return position.value.lower().replace("_", " ")


def _outlier_statuses(agreement: AgreementResult | None) -> dict[ValuationModelType, OutlierStatus]:
    if agreement is None:
        return {}
    return {outlier.model_type: outlier.status for outlier in agreement.model_outliers}


def _usable(snapshot: ValuationSnapshot) -> bool:
    return (
        snapshot.status in (ValuationSnapshotStatus.COMPLETE, ValuationSnapshotStatus.PARTIAL)
        and _positive(snapshot.selected_fair_value)
    )


def _difference_pct(left: float | None, right: float | None) -> float | None:
    if not _positive(left) or not _positive(right):
        return None
    return (float(left) - float(right)) / float(right) * 100


def _difference(left: float | None, right: float | None) -> float | None:
    if not _positive(left) or not _positive(right):
        return None
    return float(left) - float(right)


def _percent(left: float | None, right: float | None) -> float | None:
    if left is None or not _positive(right):
        return None
    return float(left) / float(right) * 100


def _positive(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value) and value > 0


def _empty(symbol: str, current_price: float | None, generated: datetime, warning: str) -> FairValueRangeResult:
    return FairValueRangeResult(
        symbol=symbol,
        status=FairValueRangeStatus.INSUFFICIENT,
        conservative_value=None,
        base_value=None,
        optimistic_intrinsic_value=None,
        intrinsic_floor=None,
        intrinsic_ceiling=None,
        intrinsic_range_width=None,
        intrinsic_range_width_pct=None,
        market_expectation_value=None,
        market_expectation_confidence=None,
        market_expectation_outlier_status=None,
        current_price=current_price,
        current_vs_conservative_pct=None,
        current_vs_base_pct=None,
        current_vs_optimistic_pct=None,
        market_position=MarketPosition.UNAVAILABLE,
        agreement_level=None,
        core_model_count=0,
        supporting_reference_count=0,
        excluded_models=(),
        included_models=(),
        momentum_reference_price=None,
        momentum_reference_date=None,
        momentum_cross_direction=None,
        momentum_current_rsi=None,
        current_vs_momentum_reference=None,
        current_vs_momentum_reference_pct=None,
        methodology="Confidence-weighted median base with lower support and upper intrinsic support",
        rationale=(),
        warnings=(warning,),
        calculation_steps=(),
        generated_at=generated,
    )
