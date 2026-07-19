from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any

from src.analysis.agreement_engine import AgreementLevel, AgreementResult, OutlierStatus
from src.analysis.fair_value_range import FairValueRangeResult, FairValueRangeStatus
from src.analysis.momentum_reference import MomentumReferenceStatus, RsiCrossDirection, RsiMomentumReference
from src.analysis.valuation_decision import ValuationRecommendation
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.config.recommendation_v2 import RecommendationV2Configuration


class RecommendationV2Decision(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    ACCUMULATE = "ACCUMULATE"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
    AVOID = "AVOID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RecommendationV2Status(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    ERROR = "ERROR"


class ValuationCondition(str, Enum):
    DEEPLY_UNDERVALUED = "DEEPLY_UNDERVALUED"
    UNDERVALUED = "UNDERVALUED"
    SLIGHTLY_UNDERVALUED = "SLIGHTLY_UNDERVALUED"
    NEAR_FAIR_VALUE = "NEAR_FAIR_VALUE"
    MODERATELY_OVERVALUED = "MODERATELY_OVERVALUED"
    SIGNIFICANTLY_OVERVALUED = "SIGNIFICANTLY_OVERVALUED"
    EXTREMELY_OVERVALUED = "EXTREMELY_OVERVALUED"
    UNAVAILABLE = "UNAVAILABLE"


class MomentumCondition(str, Enum):
    STRONG_POSITIVE = "STRONG_POSITIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    WEAK = "WEAK"
    STRONG_NEGATIVE = "STRONG_NEGATIVE"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class RecommendationAlignment(str, Enum):
    ALIGNED = "ALIGNED"
    V2_MORE_BULLISH = "V2_MORE_BULLISH"
    V2_MORE_BEARISH = "V2_MORE_BEARISH"
    NOT_COMPARABLE = "NOT_COMPARABLE"


@dataclass(frozen=True)
class RecommendationV2Result:
    symbol: str
    status: RecommendationV2Status
    decision: RecommendationV2Decision
    valuation_condition: ValuationCondition
    momentum_condition: MomentumCondition
    evidence_quality: EvidenceQuality
    current_price: float | None
    conservative_value: float | None
    base_value: float | None
    optimistic_intrinsic_value: float | None
    current_vs_base_pct: float | None
    core_agreement: AgreementLevel | None
    extended_agreement: AgreementLevel | None
    intrinsic_model_count: int
    reference_model_count: int
    current_rsi: float | None
    rsi_reference_price: float | None
    current_vs_rsi_reference_pct: float | None
    analyst_expectation: float | None
    analyst_outlier_status: OutlierStatus | None
    analyst_confidence: ValuationConfidenceLevel | None
    legacy_recommendation: ValuationRecommendation | None
    alignment: RecommendationAlignment
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    calculation_steps: tuple[str, ...]
    generated_at: datetime


def calculate_recommendation_v2(
    symbol: str,
    configuration: RecommendationV2Configuration,
    fair_value_range: FairValueRangeResult | None,
    agreement_result: AgreementResult | None,
    momentum_reference: RsiMomentumReference | None,
    snapshot_collection: ValuationSnapshotCollection | None,
    legacy_recommendation: Any,
    generated_at: datetime | None = None,
) -> RecommendationV2Result:
    generated = datetime.now(timezone.utc) if generated_at is None else generated_at
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    normalized_symbol = symbol.strip().upper()
    if not configuration.enabled:
        return _result(
            normalized_symbol,
            RecommendationV2Status.INSUFFICIENT,
            RecommendationV2Decision.INSUFFICIENT_DATA,
            ValuationCondition.UNAVAILABLE,
            MomentumCondition.UNAVAILABLE,
            EvidenceQuality.INSUFFICIENT,
            fair_value_range,
            agreement_result,
            momentum_reference,
            snapshot_collection,
            _legacy_decision(legacy_recommendation),
            generated,
            ("Recommendation V2 is disabled.",),
        )

    valuation = classify_valuation_condition(fair_value_range, configuration)
    momentum = classify_momentum_condition(momentum_reference, configuration)
    evidence = classify_evidence_quality(
        fair_value_range,
        agreement_result,
        snapshot_collection,
        configuration,
    )
    warnings = _warnings(fair_value_range, agreement_result, momentum_reference, evidence, configuration)
    decision = _decision(valuation, momentum, evidence, agreement_result, configuration)
    status = _status(decision, fair_value_range, evidence)
    legacy = _legacy_decision(legacy_recommendation)
    alignment = _alignment(decision, legacy)
    if alignment in (RecommendationAlignment.V2_MORE_BULLISH, RecommendationAlignment.V2_MORE_BEARISH):
        warnings += ("Legacy recommendation and Recommendation V2 diverge.",)
    return _result(
        normalized_symbol,
        status,
        decision,
        valuation,
        momentum,
        evidence,
        fair_value_range,
        agreement_result,
        momentum_reference,
        snapshot_collection,
        legacy,
        generated,
        warnings,
        alignment,
    )


def classify_valuation_condition(
    fair_value_range: FairValueRangeResult | None,
    configuration: RecommendationV2Configuration,
) -> ValuationCondition:
    value = None if fair_value_range is None else fair_value_range.current_vs_base_pct
    if not _finite(value):
        return ValuationCondition.UNAVAILABLE
    thresholds = configuration.valuation_thresholds
    value = round(float(value), 10)
    if value <= thresholds.deeply_undervalued_pct:
        return ValuationCondition.DEEPLY_UNDERVALUED
    if value <= thresholds.undervalued_pct:
        return ValuationCondition.UNDERVALUED
    if value < thresholds.slightly_undervalued_pct:
        return ValuationCondition.SLIGHTLY_UNDERVALUED
    if value <= thresholds.near_fair_upper_pct:
        return ValuationCondition.NEAR_FAIR_VALUE
    if value <= thresholds.moderately_overvalued_pct:
        return ValuationCondition.MODERATELY_OVERVALUED
    if value <= thresholds.significantly_overvalued_pct:
        return ValuationCondition.SIGNIFICANTLY_OVERVALUED
    return ValuationCondition.EXTREMELY_OVERVALUED


def classify_momentum_condition(
    momentum: RsiMomentumReference | None,
    configuration: RecommendationV2Configuration,
) -> MomentumCondition:
    if momentum is None or momentum.status not in (MomentumReferenceStatus.COMPLETE, MomentumReferenceStatus.FALLBACK):
        return MomentumCondition.UNAVAILABLE
    rsi = momentum.current_rsi
    reference_pct = momentum.price_change_since_reference_pct
    if not _finite(rsi) and not _finite(reference_pct):
        return MomentumCondition.UNAVAILABLE
    thresholds = configuration.momentum_thresholds
    if (_finite(rsi) and rsi <= thresholds.strong_negative_rsi) or (
        _finite(reference_pct) and reference_pct <= thresholds.severe_negative_reference_pct
    ):
        return MomentumCondition.STRONG_NEGATIVE
    if (
        _finite(rsi)
        and _finite(reference_pct)
        and rsi >= thresholds.strong_positive_rsi
        and reference_pct >= thresholds.positive_reference_pct
    ):
        return MomentumCondition.STRONG_POSITIVE
    if (_finite(rsi) and rsi >= thresholds.positive_rsi) or (
        _finite(reference_pct) and reference_pct > thresholds.positive_reference_pct
    ):
        return MomentumCondition.POSITIVE
    if (_finite(rsi) and rsi < thresholds.weak_rsi) or (
        _finite(reference_pct) and reference_pct < thresholds.negative_reference_pct
    ):
        return MomentumCondition.WEAK
    return MomentumCondition.NEUTRAL


def classify_evidence_quality(
    fair_value_range: FairValueRangeResult | None,
    agreement: AgreementResult | None,
    collection: ValuationSnapshotCollection | None,
    configuration: RecommendationV2Configuration,
) -> EvidenceQuality:
    intrinsic = _intrinsic_snapshots(collection)
    if (
        fair_value_range is None
        or fair_value_range.base_value is None
        or agreement is None
        or len(intrinsic) < configuration.minimum_intrinsic_models
    ):
        return EvidenceQuality.INSUFFICIENT
    agreement_level = agreement.core_intrinsic_agreement
    range_status = fair_value_range.status
    has_high = any(snapshot.confidence == ValuationConfidenceLevel.HIGH for snapshot in intrinsic)
    only_low = all(snapshot.confidence == ValuationConfidenceLevel.LOW for snapshot in intrinsic)
    if (
        len(intrinsic) >= 2
        and agreement_level == AgreementLevel.STRONG
        and has_high
        and range_status == FairValueRangeStatus.COMPLETE
    ):
        return EvidenceQuality.HIGH
    if (
        len(intrinsic) >= 2
        and agreement_level in (AgreementLevel.STRONG, AgreementLevel.MODERATE)
        and range_status in (FairValueRangeStatus.COMPLETE, FairValueRangeStatus.PARTIAL)
    ):
        return EvidenceQuality.LOW if only_low else EvidenceQuality.MEDIUM
    if fair_value_range.base_value is not None:
        return EvidenceQuality.LOW
    return EvidenceQuality.INSUFFICIENT


def _decision(
    valuation: ValuationCondition,
    momentum: MomentumCondition,
    evidence: EvidenceQuality,
    agreement: AgreementResult | None,
    configuration: RecommendationV2Configuration,
) -> RecommendationV2Decision:
    if evidence == EvidenceQuality.INSUFFICIENT or valuation == ValuationCondition.UNAVAILABLE:
        return RecommendationV2Decision.INSUFFICIENT_DATA
    if valuation == ValuationCondition.DEEPLY_UNDERVALUED:
        if evidence in (EvidenceQuality.HIGH, EvidenceQuality.MEDIUM):
            if momentum in (MomentumCondition.STRONG_POSITIVE, MomentumCondition.POSITIVE, MomentumCondition.NEUTRAL):
                decision = RecommendationV2Decision.STRONG_BUY
            elif momentum == MomentumCondition.WEAK:
                decision = RecommendationV2Decision.BUY
            else:
                decision = RecommendationV2Decision.ACCUMULATE
        else:
            decision = RecommendationV2Decision.ACCUMULATE
    elif valuation == ValuationCondition.UNDERVALUED:
        if evidence == EvidenceQuality.HIGH:
            decision = (
                RecommendationV2Decision.BUY
                if momentum in (MomentumCondition.STRONG_POSITIVE, MomentumCondition.POSITIVE, MomentumCondition.NEUTRAL)
                else RecommendationV2Decision.ACCUMULATE
            )
        elif evidence == EvidenceQuality.MEDIUM:
            decision = RecommendationV2Decision.ACCUMULATE
        else:
            decision = RecommendationV2Decision.HOLD
    elif valuation == ValuationCondition.SLIGHTLY_UNDERVALUED:
        decision = (
            RecommendationV2Decision.ACCUMULATE
            if evidence == EvidenceQuality.HIGH and momentum in (MomentumCondition.STRONG_POSITIVE, MomentumCondition.POSITIVE)
            else RecommendationV2Decision.HOLD
        )
    elif valuation == ValuationCondition.NEAR_FAIR_VALUE:
        if momentum == MomentumCondition.STRONG_POSITIVE:
            decision = RecommendationV2Decision.ACCUMULATE
        elif momentum == MomentumCondition.STRONG_NEGATIVE:
            decision = RecommendationV2Decision.REDUCE
        else:
            decision = RecommendationV2Decision.HOLD
    elif valuation == ValuationCondition.MODERATELY_OVERVALUED:
        decision = RecommendationV2Decision.HOLD if momentum == MomentumCondition.STRONG_POSITIVE else RecommendationV2Decision.REDUCE
    elif valuation == ValuationCondition.SIGNIFICANTLY_OVERVALUED:
        if evidence in (EvidenceQuality.HIGH, EvidenceQuality.MEDIUM):
            decision = (
                RecommendationV2Decision.REDUCE
                if momentum in (MomentumCondition.STRONG_POSITIVE, MomentumCondition.POSITIVE)
                else RecommendationV2Decision.SELL
            )
        else:
            decision = RecommendationV2Decision.REDUCE
    elif valuation == ValuationCondition.EXTREMELY_OVERVALUED:
        decision = (
            RecommendationV2Decision.SELL
            if evidence in (EvidenceQuality.HIGH, EvidenceQuality.MEDIUM)
            else RecommendationV2Decision.REDUCE
        )
    else:
        decision = RecommendationV2Decision.INSUFFICIENT_DATA
    if agreement is not None and agreement.core_intrinsic_agreement == AgreementLevel.CONFLICTED:
        decision = _cap_conflicted(decision)
    if (
        configuration.require_agreement_for_strong_buy
        and decision == RecommendationV2Decision.STRONG_BUY
        and (agreement is None or agreement.core_intrinsic_agreement != AgreementLevel.STRONG)
    ):
        decision = RecommendationV2Decision.BUY
    if (
        configuration.require_agreement_for_sell
        and decision == RecommendationV2Decision.SELL
        and (
            agreement is None
            or agreement.core_intrinsic_agreement
            not in (AgreementLevel.STRONG, AgreementLevel.MODERATE)
        )
    ):
        decision = RecommendationV2Decision.REDUCE
    return decision


def _cap_conflicted(decision: RecommendationV2Decision) -> RecommendationV2Decision:
    rank = _DECISION_RANK.get(decision)
    if rank is None:
        return decision
    if rank > _DECISION_RANK[RecommendationV2Decision.ACCUMULATE]:
        return RecommendationV2Decision.ACCUMULATE
    if rank < _DECISION_RANK[RecommendationV2Decision.REDUCE]:
        return RecommendationV2Decision.REDUCE
    return decision


def _result(
    symbol: str,
    status: RecommendationV2Status,
    decision: RecommendationV2Decision,
    valuation: ValuationCondition,
    momentum: MomentumCondition,
    evidence: EvidenceQuality,
    fair_value_range: FairValueRangeResult | None,
    agreement: AgreementResult | None,
    momentum_reference: RsiMomentumReference | None,
    collection: ValuationSnapshotCollection | None,
    legacy: ValuationRecommendation | None,
    generated: datetime,
    warnings: tuple[str, ...],
    alignment: RecommendationAlignment = RecommendationAlignment.NOT_COMPARABLE,
) -> RecommendationV2Result:
    analyst = _analyst_context(agreement)
    result = RecommendationV2Result(
        symbol=symbol,
        status=status,
        decision=decision,
        valuation_condition=valuation,
        momentum_condition=momentum,
        evidence_quality=evidence,
        current_price=None if fair_value_range is None else fair_value_range.current_price,
        conservative_value=None if fair_value_range is None else fair_value_range.conservative_value,
        base_value=None if fair_value_range is None else fair_value_range.base_value,
        optimistic_intrinsic_value=None if fair_value_range is None else fair_value_range.optimistic_intrinsic_value,
        current_vs_base_pct=None if fair_value_range is None else fair_value_range.current_vs_base_pct,
        core_agreement=None if agreement is None else agreement.core_intrinsic_agreement,
        extended_agreement=None if agreement is None else agreement.extended_intrinsic_agreement,
        intrinsic_model_count=len(_intrinsic_snapshots(collection)),
        reference_model_count=len(_reference_snapshots(collection)),
        current_rsi=None if momentum_reference is None else momentum_reference.current_rsi,
        rsi_reference_price=None if momentum_reference is None else momentum_reference.reference_price,
        current_vs_rsi_reference_pct=None if momentum_reference is None else momentum_reference.price_change_since_reference_pct,
        analyst_expectation=analyst[0],
        analyst_outlier_status=analyst[1],
        analyst_confidence=analyst[2],
        legacy_recommendation=legacy,
        alignment=alignment,
        rationale=(),
        warnings=warnings,
        calculation_steps=("Classify valuation", "Classify evidence", "Classify momentum", "Apply decision matrix", "Compare legacy recommendation"),
        generated_at=generated,
    )
    return RecommendationV2Result(**{**result.__dict__, "rationale": _rationale(result)})


def _status(
    decision: RecommendationV2Decision,
    fair_value_range: FairValueRangeResult | None,
    evidence: EvidenceQuality,
) -> RecommendationV2Status:
    if decision == RecommendationV2Decision.INSUFFICIENT_DATA or evidence == EvidenceQuality.INSUFFICIENT:
        return RecommendationV2Status.INSUFFICIENT
    if fair_value_range is not None and fair_value_range.status == FairValueRangeStatus.PARTIAL:
        return RecommendationV2Status.PARTIAL
    return RecommendationV2Status.COMPLETE


def _warnings(
    fair_value_range: FairValueRangeResult | None,
    agreement: AgreementResult | None,
    momentum: RsiMomentumReference | None,
    evidence: EvidenceQuality,
    configuration: RecommendationV2Configuration,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if fair_value_range is None or fair_value_range.base_value is None:
        warnings.append("Fair value range is unavailable; Recommendation V2 cannot issue a valuation decision.")
    elif fair_value_range.status == FairValueRangeStatus.PARTIAL:
        warnings.append("Fair value range is partial.")
    if agreement is None:
        warnings.append("Agreement result is unavailable.")
    elif agreement.core_intrinsic_agreement == AgreementLevel.CONFLICTED:
        warnings.append("Core intrinsic agreement is conflicted.")
    if evidence == EvidenceQuality.INSUFFICIENT:
        warnings.append("Intrinsic model count is below the Recommendation V2 minimum.")
    if momentum is None or momentum.status not in (MomentumReferenceStatus.COMPLETE, MomentumReferenceStatus.FALLBACK):
        warnings.append("Momentum is unavailable.")
    elif momentum.status == MomentumReferenceStatus.FALLBACK or momentum.cross_direction == RsiCrossDirection.NEAREST_TO_50:
        warnings.append("RSI reference uses nearest-to-50 fallback.")
    if agreement is None or not agreement.market_expectation_analyses:
        warnings.append("Analyst consensus context is unavailable.")
    return tuple(dict.fromkeys(warnings))


def _rationale(result: RecommendationV2Result) -> tuple[str, ...]:
    lines: list[str] = []
    if result.current_vs_base_pct is not None:
        direction = "above" if result.current_vs_base_pct >= 0 else "below"
        lines.append(
            f"{result.symbol} trades approximately {abs(result.current_vs_base_pct):.2f}% {direction} its base intrinsic value and is classified as {_text(result.valuation_condition)}."
        )
    if result.core_agreement is not None:
        lines.append(
            f"Core intrinsic models show {_text(result.core_agreement)} agreement and evidence quality is {_text(result.evidence_quality)}."
        )
    if result.momentum_condition != MomentumCondition.UNAVAILABLE:
        if result.current_rsi is not None and result.current_vs_rsi_reference_pct is not None:
            direction = "above" if result.current_vs_rsi_reference_pct >= 0 else "below"
            lines.append(
                f"Momentum is {_text(result.momentum_condition)} because RSI(14) is {result.current_rsi:.2f} and the current price is {abs(result.current_vs_rsi_reference_pct):.2f}% {direction} the latest RSI 50 reference price."
            )
        else:
            lines.append(f"Momentum is {_text(result.momentum_condition)}.")
    if result.analyst_expectation is None:
        lines.append("Analyst Consensus is unavailable and does not affect the Recommendation V2 decision.")
    elif result.analyst_confidence == ValuationConfidenceLevel.LOW or result.analyst_outlier_status == OutlierStatus.OUTLIER:
        confidence = "low-confidence " if result.analyst_confidence == ValuationConfidenceLevel.LOW else ""
        outlier = " outlier" if result.analyst_outlier_status == OutlierStatus.OUTLIER else ""
        lines.append(
            f"Analyst Consensus is a {confidence}market-expectation{outlier} and does not override the intrinsic valuation conclusion."
        )
    else:
        lines.append("Analyst Consensus is included as market-expectation context only.")
    lines.append(f"Recommendation V2 is {result.decision.value}.")
    return tuple(lines)


def _analyst_context(
    agreement: AgreementResult | None,
) -> tuple[float | None, OutlierStatus | None, ValuationConfidenceLevel | None]:
    if agreement is None or not agreement.market_expectation_analyses:
        return None, None, None
    analysis = agreement.market_expectation_analyses[0]
    return analysis.selected_value, analysis.outlier_status, analysis.confidence


def _alignment(
    decision: RecommendationV2Decision,
    legacy: ValuationRecommendation | None,
) -> RecommendationAlignment:
    legacy_decision = _legacy_to_v2(legacy)
    if legacy_decision is None or decision == RecommendationV2Decision.INSUFFICIENT_DATA:
        return RecommendationAlignment.NOT_COMPARABLE
    if decision == legacy_decision:
        return RecommendationAlignment.ALIGNED
    return (
        RecommendationAlignment.V2_MORE_BULLISH
        if _DECISION_RANK[decision] > _DECISION_RANK[legacy_decision]
        else RecommendationAlignment.V2_MORE_BEARISH
    )


def _legacy_decision(value: Any) -> ValuationRecommendation | None:
    if isinstance(value, ValuationRecommendation):
        return value
    if isinstance(value, str):
        try:
            return ValuationRecommendation(value)
        except ValueError:
            return None
    return None


def _legacy_to_v2(value: ValuationRecommendation | None) -> RecommendationV2Decision | None:
    return {
        ValuationRecommendation.BUY: RecommendationV2Decision.BUY,
        ValuationRecommendation.HOLD: RecommendationV2Decision.HOLD,
        ValuationRecommendation.SELL: RecommendationV2Decision.SELL,
    }.get(value)


def _intrinsic_snapshots(collection: ValuationSnapshotCollection | None):
    if collection is None:
        return ()
    return tuple(
        snapshot
        for snapshot in collection.snapshots
        if snapshot.value_type == ValuationValueType.INTRINSIC_VALUE
        and snapshot.status in (ValuationSnapshotStatus.COMPLETE, ValuationSnapshotStatus.PARTIAL)
        and _finite(snapshot.selected_fair_value)
        and snapshot.selected_fair_value > 0
    )


def _reference_snapshots(collection: ValuationSnapshotCollection | None):
    if collection is None:
        return ()
    return tuple(
        snapshot
        for snapshot in collection.snapshots
        if snapshot.value_type == ValuationValueType.REFERENCE_VALUE
        and snapshot.status in (ValuationSnapshotStatus.COMPLETE, ValuationSnapshotStatus.PARTIAL)
        and _finite(snapshot.selected_fair_value)
        and snapshot.selected_fair_value > 0
    )


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def _text(value: Enum) -> str:
    return value.value.lower().replace("_", " ")


_DECISION_RANK = {
    RecommendationV2Decision.STRONG_BUY: 7,
    RecommendationV2Decision.BUY: 6,
    RecommendationV2Decision.ACCUMULATE: 5,
    RecommendationV2Decision.HOLD: 4,
    RecommendationV2Decision.REDUCE: 3,
    RecommendationV2Decision.SELL: 2,
    RecommendationV2Decision.AVOID: 1,
}
