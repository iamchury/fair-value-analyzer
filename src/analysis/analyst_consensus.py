from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotStatus,
    ValuationSnapshotStep,
    ValuationValueType,
)
from src.config.analyst_consensus import (
    AnalystConsensusRule,
    AnalystValuationMethod,
)


class AnalystDispersionClassification(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AnalystConsensusInputs:
    symbol: str
    current_price: float | None
    target_mean: float | None
    target_high: float | None
    target_low: float | None
    currency: str | None
    source_timestamp: datetime
    treasury_multiplier: float | None
    rule: AnalystConsensusRule


def calculate_analyst_consensus(
    inputs: AnalystConsensusInputs,
) -> ValuationSnapshot:
    """Calculate analyst-consensus market expectation directly as a snapshot."""
    symbol = _normalize_symbol(inputs.symbol)
    _require_aware_datetime("source_timestamp", inputs.source_timestamp)
    generated_at = inputs.source_timestamp.astimezone(timezone.utc)
    warnings: list[str] = []

    if not inputs.rule.enabled:
        return _snapshot(
            symbol=symbol,
            currency=inputs.currency,
            generated_at=generated_at,
            status=ValuationSnapshotStatus.UNAVAILABLE,
            confidence=ValuationConfidenceLevel.UNKNOWN,
            raw_fair_value=None,
            adjusted_fair_value=None,
            selected_fair_value=None,
            assumptions=_assumptions(inputs.rule),
            metrics={},
            rationale=inputs.rule.rationale,
            warnings=("Analyst consensus is disabled.",),
            calculation_steps=(),
        )

    current_price = _optional_positive(inputs.current_price, "current_price", warnings)
    mean = _optional_positive(inputs.target_mean, "target_mean", warnings)
    high = _optional_positive(inputs.target_high, "target_high", warnings)
    low = _optional_positive(inputs.target_low, "target_low", warnings)
    multiplier = _optional_positive(
        inputs.treasury_multiplier,
        "treasury_multiplier",
        warnings,
    )
    ordering_valid = _ordering_valid(low, mean, high, warnings)
    midpoint = (high + low) / 2 if high is not None and low is not None else None
    target_range = high - low if high is not None and low is not None else None
    dispersion = (
        target_range / mean * 100
        if target_range is not None and mean is not None
        else None
    )
    classification = _classify_dispersion(dispersion, inputs.rule)
    raw_fair_value = _raw_fair_value(inputs.rule, mean, midpoint, warnings)

    treasury_applied = inputs.rule.apply_treasury
    adjusted_fair_value = raw_fair_value
    if treasury_applied:
        if raw_fair_value is None or multiplier is None:
            adjusted_fair_value = None
            warnings.append("Treasury multiplier was requested but unavailable.")
        else:
            adjusted_fair_value = raw_fair_value * multiplier

    if not ordering_valid:
        raw_fair_value = None
        adjusted_fair_value = None
    status = _status(raw_fair_value, adjusted_fair_value, mean, high, low)
    confidence = _confidence(status, classification, mean, high, low)
    if classification == AnalystDispersionClassification.EXTREME:
        warnings.append("Analyst target dispersion is extreme.")

    steps = ()
    if raw_fair_value is not None:
        steps = (
            ValuationSnapshotStep(
                name="Analyst weighted fair value",
                input_values={
                    "target_mean": mean,
                    "target_midpoint": midpoint,
                    "mean_weight": inputs.rule.mean_weight,
                    "midpoint_weight": inputs.rule.midpoint_weight,
                },
                formula="target_mean * mean_weight + target_midpoint * midpoint_weight",
                result=raw_fair_value,
                explanation="Calculated Yahoo analyst target weighted mean/midpoint.",
            ),
        )

    return _snapshot(
        symbol=symbol,
        currency=inputs.currency,
        generated_at=generated_at,
        status=status,
        confidence=confidence,
        raw_fair_value=raw_fair_value,
        adjusted_fair_value=adjusted_fair_value,
        selected_fair_value=adjusted_fair_value,
        assumptions=_assumptions(inputs.rule),
        metrics={
            "current_price": current_price,
            "target_mean": mean,
            "target_high": high,
            "target_low": low,
            "target_midpoint": midpoint,
            "target_range": target_range,
            "dispersion_percent": dispersion,
            "dispersion_classification": classification.value,
            "treasury_applied": treasury_applied,
            "treasury_multiplier": multiplier,
        },
        rationale=inputs.rule.rationale,
        warnings=tuple(dict.fromkeys(warnings)),
        calculation_steps=steps,
    )


def _snapshot(
    *,
    symbol: str,
    currency: str | None,
    generated_at: datetime,
    status: ValuationSnapshotStatus,
    confidence: ValuationConfidenceLevel,
    raw_fair_value: float | None,
    adjusted_fair_value: float | None,
    selected_fair_value: float | None,
    assumptions: dict[str, object],
    metrics: dict[str, object],
    rationale: str | None,
    warnings: tuple[str, ...],
    calculation_steps: tuple[ValuationSnapshotStep, ...],
) -> ValuationSnapshot:
    return ValuationSnapshot(
        symbol=symbol,
        model_type=ValuationModelType.ANALYST_CONSENSUS,
        model_name="Analyst Consensus Model",
        value_type=ValuationValueType.MARKET_EXPECTATION,
        status=status,
        confidence=confidence,
        raw_fair_value=raw_fair_value,
        adjusted_fair_value=adjusted_fair_value,
        selected_fair_value=selected_fair_value,
        currency=currency,
        valuation_date=None,
        source_as_of=None,
        generated_at=generated_at,
        methodology="Weighted Mean / Midpoint",
        rationale=rationale,
        assumptions=assumptions,
        metrics={key: value for key, value in metrics.items() if value is not None},
        warnings=warnings,
        calculation_steps=calculation_steps,
    )


def _assumptions(rule: AnalystConsensusRule) -> dict[str, object]:
    return {
        "valuation_method": rule.valuation_method.value,
        "mean_weight": rule.mean_weight,
        "midpoint_weight": rule.midpoint_weight,
        "apply_treasury": rule.apply_treasury,
        "low_dispersion": rule.low_dispersion,
        "medium_dispersion": rule.medium_dispersion,
        "high_dispersion": rule.high_dispersion,
    }


def _raw_fair_value(
    rule: AnalystConsensusRule,
    mean: float | None,
    midpoint: float | None,
    warnings: list[str],
) -> float | None:
    if rule.valuation_method == AnalystValuationMethod.MEAN:
        if mean is None:
            warnings.append("Target mean is unavailable.")
        return mean
    if rule.valuation_method == AnalystValuationMethod.MIDPOINT:
        if midpoint is None:
            warnings.append("Target midpoint is unavailable.")
        return midpoint
    if mean is None or midpoint is None:
        warnings.append("Weighted mean/midpoint fair value is unavailable.")
        return None
    return mean * rule.mean_weight + midpoint * rule.midpoint_weight


def _classify_dispersion(
    dispersion_percent: float | None,
    rule: AnalystConsensusRule,
) -> AnalystDispersionClassification:
    if dispersion_percent is None:
        return AnalystDispersionClassification.UNKNOWN
    if dispersion_percent <= rule.low_dispersion:
        return AnalystDispersionClassification.LOW
    if dispersion_percent <= rule.medium_dispersion:
        return AnalystDispersionClassification.MEDIUM
    if dispersion_percent <= rule.high_dispersion:
        return AnalystDispersionClassification.HIGH
    return AnalystDispersionClassification.EXTREME


def _status(
    raw_fair_value: float | None,
    adjusted_fair_value: float | None,
    mean: float | None,
    high: float | None,
    low: float | None,
) -> ValuationSnapshotStatus:
    if raw_fair_value is None or adjusted_fair_value is None:
        if mean is not None or high is not None or low is not None:
            return ValuationSnapshotStatus.PARTIAL
        return ValuationSnapshotStatus.UNAVAILABLE
    if mean is None or high is None or low is None:
        return ValuationSnapshotStatus.PARTIAL
    return ValuationSnapshotStatus.COMPLETE


def _confidence(
    status: ValuationSnapshotStatus,
    classification: AnalystDispersionClassification,
    mean: float | None,
    high: float | None,
    low: float | None,
) -> ValuationConfidenceLevel:
    if status == ValuationSnapshotStatus.UNAVAILABLE:
        return ValuationConfidenceLevel.UNKNOWN
    if status == ValuationSnapshotStatus.PARTIAL:
        return ValuationConfidenceLevel.LOW
    if mean is None or high is None or low is None:
        return ValuationConfidenceLevel.LOW
    if classification == AnalystDispersionClassification.LOW:
        return ValuationConfidenceLevel.HIGH
    if classification == AnalystDispersionClassification.MEDIUM:
        return ValuationConfidenceLevel.MEDIUM
    if classification in (
        AnalystDispersionClassification.HIGH,
        AnalystDispersionClassification.EXTREME,
    ):
        return ValuationConfidenceLevel.LOW
    return ValuationConfidenceLevel.UNKNOWN


def _ordering_valid(
    low: float | None,
    mean: float | None,
    high: float | None,
    warnings: list[str],
) -> bool:
    if low is not None and high is not None and low > high:
        warnings.append("Analyst target ordering is invalid: low is above high.")
        return False
    if low is not None and mean is not None and mean < low:
        warnings.append("Analyst target ordering is invalid: mean is below low.")
        return False
    if high is not None and mean is not None and mean > high:
        warnings.append("Analyst target ordering is invalid: mean is above high.")
        return False
    return True


def _optional_positive(value: object, name: str, warnings: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        warnings.append(f"{name} is invalid and was treated as unavailable.")
        return None
    if not isfinite(value) or value <= 0:
        warnings.append(f"{name} is invalid and was treated as unavailable.")
        return None
    return float(value)


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    if any(character.isspace() for character in normalized):
        raise ValueError("symbol must not contain whitespace.")
    return normalized


def _require_aware_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
