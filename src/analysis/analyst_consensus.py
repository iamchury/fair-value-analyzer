from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from src.config.analyst_consensus import (
    AnalystConsensusRule,
    AnalystFairValueMethod,
)


class AnalystConsensusStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class AnalystDispersionLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class AnalystConsensusQuality(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    UNRELIABLE = "UNRELIABLE"
    UNKNOWN = "UNKNOWN"


class StaleStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CalculationStep:
    name: str
    input_values: Mapping[str, object]
    formula: str | None
    result: float | None
    explanation: str


@dataclass(frozen=True)
class AnalystConsensusInputs:
    symbol: str
    current_price: float | None
    target_mean: float | None
    target_high: float | None
    target_low: float | None
    analyst_count: int | None
    source_timestamp: datetime
    treasury_multiplier: float | None
    rule: AnalystConsensusRule
    analyst_target_as_of: datetime | None = None


@dataclass(frozen=True)
class AnalystConsensusResult:
    symbol: str
    status: AnalystConsensusStatus
    fair_value_method: AnalystFairValueMethod
    target_mean: float | None
    target_high: float | None
    target_low: float | None
    target_midpoint: float | None
    target_range: float | None
    dispersion_percent: float | None
    dispersion_level: AnalystDispersionLevel
    analyst_count: int | None
    consensus_quality: AnalystConsensusQuality
    current_price: float | None
    mean_upside_percent: float | None
    low_upside_percent: float | None
    high_upside_percent: float | None
    raw_analyst_fair_value: float | None
    treasury_applied: bool
    treasury_multiplier: float | None
    adjusted_analyst_fair_value: float | None
    analyst_target_as_of: datetime | None
    retrieved_at: datetime
    stale_status: StaleStatus
    rationale: str | None
    warnings: tuple[str, ...]
    calculation_steps: tuple[CalculationStep, ...]


def calculate_analyst_consensus(
    inputs: AnalystConsensusInputs,
) -> AnalystConsensusResult:
    symbol = _normalize_symbol(inputs.symbol)
    _require_aware_datetime("source_timestamp", inputs.source_timestamp)
    retrieved_at = inputs.source_timestamp.astimezone(timezone.utc)
    warnings: list[str] = []
    steps: list[CalculationStep] = []
    if not inputs.rule.enabled:
        return _unavailable(inputs, symbol, retrieved_at, ("Analyst consensus is disabled.",))

    current_price = _optional_positive(inputs.current_price, "current_price", warnings)
    mean = _optional_positive(inputs.target_mean, "target_mean", warnings)
    high = _optional_positive(inputs.target_high, "target_high", warnings)
    low = _optional_positive(inputs.target_low, "target_low", warnings)
    analyst_count = _optional_count(inputs.analyst_count, warnings)
    multiplier = _optional_multiplier(inputs.treasury_multiplier, warnings)
    ordering_valid = _ordering_valid(low, mean, high, warnings)
    midpoint = (low + high) / 2 if low is not None and high is not None else None
    target_range = high - low if low is not None and high is not None else None
    dispersion = (
        target_range / max(abs(mean), 1e-9) * 100
        if target_range is not None and mean is not None
        else None
    )
    dispersion_level = _classify_dispersion(dispersion, inputs.rule)
    raw_fair_value = _raw_fair_value(inputs.rule, mean, midpoint, warnings)
    if raw_fair_value is not None:
        steps.append(CalculationStep(
            "Analyst fair value",
            {"method": inputs.rule.fair_value_method.value, "mean": mean, "midpoint": midpoint},
            _formula(inputs.rule.fair_value_method),
            raw_fair_value,
            "Calculated independent analyst consensus fair value.",
        ))
    if not ordering_valid:
        raw_fair_value = None
    treasury_applied = inputs.rule.apply_treasury_multiplier
    adjusted = raw_fair_value
    if treasury_applied:
        if raw_fair_value is None or multiplier is None:
            adjusted = None
            warnings.append("Treasury multiplier was requested but unavailable.")
        else:
            adjusted = raw_fair_value * multiplier
    stale_status = _stale_status(inputs.analyst_target_as_of, retrieved_at, inputs.rule, warnings)
    status = _status(raw_fair_value, adjusted, ordering_valid, mean, high, low, analyst_count, inputs.rule)
    quality = _quality(status, dispersion_level, analyst_count, stale_status, ordering_valid, mean, high, low)
    if dispersion_level == AnalystDispersionLevel.EXTREME:
        warnings.append("Analyst target dispersion is extreme.")
    return AnalystConsensusResult(
        symbol=symbol,
        status=status,
        fair_value_method=inputs.rule.fair_value_method,
        target_mean=mean,
        target_high=high,
        target_low=low,
        target_midpoint=midpoint,
        target_range=target_range,
        dispersion_percent=dispersion,
        dispersion_level=dispersion_level,
        analyst_count=analyst_count,
        consensus_quality=quality,
        current_price=current_price,
        mean_upside_percent=_upside(mean, current_price),
        low_upside_percent=_upside(low, current_price),
        high_upside_percent=_upside(high, current_price),
        raw_analyst_fair_value=raw_fair_value,
        treasury_applied=treasury_applied,
        treasury_multiplier=multiplier,
        adjusted_analyst_fair_value=adjusted,
        analyst_target_as_of=inputs.analyst_target_as_of,
        retrieved_at=retrieved_at,
        stale_status=stale_status,
        rationale=inputs.rule.rationale,
        warnings=tuple(dict.fromkeys(warnings)),
        calculation_steps=tuple(steps),
    )


def _unavailable(inputs, symbol, retrieved_at, warnings):
    return AnalystConsensusResult(symbol, AnalystConsensusStatus.UNAVAILABLE, inputs.rule.fair_value_method, None, None, None, None, None, None, AnalystDispersionLevel.UNKNOWN, None, AnalystConsensusQuality.UNKNOWN, inputs.current_price, None, None, None, None, False, None, None, None, retrieved_at, StaleStatus.UNKNOWN, inputs.rule.rationale, tuple(warnings), ())


def _status(raw, adjusted, ordering_valid, mean, high, low, analyst_count, rule):
    if raw is None or not ordering_valid or (rule.apply_treasury_multiplier and adjusted is None):
        return AnalystConsensusStatus.UNAVAILABLE
    if analyst_count is None or high is None or low is None:
        return AnalystConsensusStatus.PARTIAL
    return AnalystConsensusStatus.COMPLETE


def _quality(status, dispersion, analyst_count, stale, ordering_valid, mean, high, low):
    if not ordering_valid or analyst_count == 0 or status == AnalystConsensusStatus.UNAVAILABLE:
        return AnalystConsensusQuality.UNRELIABLE
    if dispersion == AnalystDispersionLevel.EXTREME:
        return AnalystConsensusQuality.UNRELIABLE
    if dispersion == AnalystDispersionLevel.HIGH or stale == StaleStatus.STALE or (analyst_count is not None and analyst_count <= 4):
        return AnalystConsensusQuality.WEAK
    if dispersion == AnalystDispersionLevel.MEDIUM:
        return AnalystConsensusQuality.MODERATE
    if dispersion == AnalystDispersionLevel.LOW and status == AnalystConsensusStatus.COMPLETE and (analyst_count is None or analyst_count >= 10):
        return AnalystConsensusQuality.STRONG
    if mean is None or high is None or low is None:
        return AnalystConsensusQuality.UNKNOWN
    return AnalystConsensusQuality.MODERATE


def _classify_dispersion(value, rule):
    if value is None:
        return AnalystDispersionLevel.UNKNOWN
    if value <= rule.low_dispersion_threshold_percent:
        return AnalystDispersionLevel.LOW
    if value <= rule.medium_dispersion_threshold_percent:
        return AnalystDispersionLevel.MEDIUM
    if value <= rule.extreme_dispersion_threshold_percent:
        return AnalystDispersionLevel.HIGH
    return AnalystDispersionLevel.EXTREME


def _raw_fair_value(rule, mean, midpoint, warnings):
    if rule.fair_value_method == AnalystFairValueMethod.MEAN:
        if mean is None:
            warnings.append("Target mean is unavailable.")
        return mean
    if rule.fair_value_method == AnalystFairValueMethod.MIDPOINT:
        if midpoint is None:
            warnings.append("Target midpoint is unavailable.")
        return midpoint
    if mean is None or midpoint is None:
        warnings.append("Weighted mean/midpoint fair value is unavailable.")
        return None
    return mean * rule.mean_weight + midpoint * rule.midpoint_weight


def _ordering_valid(low, mean, high, warnings):
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


def _stale_status(as_of, retrieved_at, rule, warnings):
    if as_of is None:
        warnings.append("Yahoo did not provide a reliable analyst-target as-of date.")
        return StaleStatus.UNKNOWN
    _require_aware_datetime("analyst_target_as_of", as_of)
    age_days = (retrieved_at - as_of.astimezone(timezone.utc)).days
    if age_days < 0:
        warnings.append("Analyst target as-of date is in the future.")
        return StaleStatus.UNKNOWN
    return StaleStatus.STALE if age_days > rule.stale_after_days else StaleStatus.FRESH


def _upside(target, current):
    if target is None or current is None:
        return None
    return (target / current - 1) * 100


def _optional_positive(value, name, warnings):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        warnings.append(f"{name} is invalid and was treated as unavailable.")
        return None
    return float(value)


def _optional_multiplier(value, warnings):
    if value is None:
        return None
    return _optional_positive(value, "treasury_multiplier", warnings)


def _optional_count(value, warnings):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        warnings.append("analyst_count is invalid and was treated as unavailable.")
        return None
    return value


def _formula(method):
    if method == AnalystFairValueMethod.MEAN:
        return "target_mean"
    if method == AnalystFairValueMethod.MIDPOINT:
        return "(target_low + target_high) / 2"
    return "target_mean * mean_weight + target_midpoint * midpoint_weight"


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    return normalized


def _require_aware_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
