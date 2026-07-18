from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite

from src.yahoo.company import EPSRawFieldSource, YahooEPSRawSnapshot


DEFAULT_MATCH_TOLERANCE_PERCENT = 1.0
_SMALL_EPSILON = 1e-9


class EPSPeriodType(str, Enum):
    TRAILING_TWELVE_MONTHS = "TRAILING_TWELVE_MONTHS"
    CURRENT_FISCAL_YEAR = "CURRENT_FISCAL_YEAR"
    NEXT_FISCAL_YEAR = "NEXT_FISCAL_YEAR"
    NEXT_TWELVE_MONTHS = "NEXT_TWELVE_MONTHS"
    CURRENT_QUARTER = "CURRENT_QUARTER"
    NEXT_QUARTER = "NEXT_QUARTER"
    UNKNOWN = "UNKNOWN"


class EPSBasisType(str, Enum):
    GAAP = "GAAP"
    NON_GAAP = "NON_GAAP"
    ADJUSTED = "ADJUSTED"
    UNKNOWN = "UNKNOWN"


class EPSInspectionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class EPSAmbiguityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class EPSInspectionStep:
    name: str
    input_values: tuple[tuple[str, object], ...]
    formula: str | None
    result: float | bool | None
    explanation: str


@dataclass(frozen=True)
class EPSInspectionResult:
    symbol: str
    status: EPSInspectionStatus
    selected_forward_eps: float | None
    selected_forward_eps_raw_field: str | None
    inferred_period_type: EPSPeriodType
    inferred_period_label: str | None
    basis_type: EPSBasisType
    trailing_eps: float | None
    current_year_eps_estimate: float | None
    next_year_eps_estimate: float | None
    current_quarter_eps_estimate: float | None
    next_quarter_eps_estimate: float | None
    last_fiscal_year_end: date | datetime | None
    next_fiscal_year_end: date | datetime | None
    most_recent_quarter: date | datetime | None
    source_timestamp: datetime
    forward_eps_matches_current_year: bool | None
    forward_eps_current_year_difference_percent: float | None
    forward_eps_matches_next_year: bool | None
    forward_eps_next_year_difference_percent: float | None
    match_tolerance_percent: float
    ambiguity_level: EPSAmbiguityLevel
    warnings: tuple[str, ...]
    calculation_steps: tuple[EPSInspectionStep, ...]
    raw_field_sources: tuple[EPSRawFieldSource, ...]


def inspect_eps_source(
    snapshot: YahooEPSRawSnapshot,
    match_tolerance_percent: float = DEFAULT_MATCH_TOLERANCE_PERCENT,
) -> EPSInspectionResult:
    """Inspect Yahoo EPS source fields without changing valuation inputs."""
    _validate_tolerance(match_tolerance_percent)
    forward_eps = snapshot.forward_eps
    current_year = _estimate_value(snapshot.current_year_estimate)
    next_year = _estimate_value(snapshot.next_year_estimate)
    current_quarter = _estimate_value(snapshot.current_quarter_estimate)
    next_quarter = _estimate_value(snapshot.next_quarter_estimate)

    warnings = list(snapshot.warnings)
    steps: list[EPSInspectionStep] = []

    current_diff = _difference_percent(forward_eps, current_year)
    next_diff = _difference_percent(forward_eps, next_year)
    current_match = _matches(current_diff, match_tolerance_percent)
    next_match = _matches(next_diff, match_tolerance_percent)

    steps.append(
        EPSInspectionStep(
            name="current_year_match",
            input_values=(
                ("forward_eps", forward_eps),
                ("current_year_estimate", current_year),
                ("tolerance_percent", match_tolerance_percent),
            ),
            formula=(
                "abs(forward_eps - estimate) / "
                "max(abs(estimate), small_epsilon) * 100"
            ),
            result=current_diff,
            explanation="Compared Yahoo forwardEps with current-year EPS estimate.",
        )
    )
    steps.append(
        EPSInspectionStep(
            name="next_year_match",
            input_values=(
                ("forward_eps", forward_eps),
                ("next_year_estimate", next_year),
                ("tolerance_percent", match_tolerance_percent),
            ),
            formula=(
                "abs(forward_eps - estimate) / "
                "max(abs(estimate), small_epsilon) * 100"
            ),
            result=next_diff,
            explanation="Compared Yahoo forwardEps with next-year EPS estimate.",
        )
    )

    period_type = EPSPeriodType.UNKNOWN
    period_label = None
    if forward_eps is None:
        warnings.append("Yahoo forwardEps is unavailable.")
    elif current_year is None and next_year is None:
        warnings.append("annual estimate table unavailable.")
    elif current_match and not next_match:
        period_type = EPSPeriodType.CURRENT_FISCAL_YEAR
        period_label = snapshot.current_year_estimate.period_label
    elif next_match and not current_match:
        period_type = EPSPeriodType.NEXT_FISCAL_YEAR
        period_label = snapshot.next_year_estimate.period_label
    elif current_match and next_match:
        warnings.append("forwardEps matches both current-year and next-year estimates.")
    else:
        warnings.append("Yahoo forwardEps does not match available annual estimates.")

    basis_type = EPSBasisType.UNKNOWN
    warnings.append("GAAP/non-GAAP basis is unavailable.")

    status = _status(snapshot, current_year, next_year, current_quarter, next_quarter)
    ambiguity = _ambiguity(
        period_type=period_type,
        period_label=period_label,
        basis_type=basis_type,
        status=status,
        current_match=current_match,
        next_match=next_match,
    )

    return EPSInspectionResult(
        symbol=snapshot.symbol,
        status=status,
        selected_forward_eps=forward_eps,
        selected_forward_eps_raw_field=_forward_eps_raw_field(snapshot.raw_field_sources),
        inferred_period_type=period_type,
        inferred_period_label=period_label,
        basis_type=basis_type,
        trailing_eps=snapshot.trailing_eps,
        current_year_eps_estimate=current_year,
        next_year_eps_estimate=next_year,
        current_quarter_eps_estimate=current_quarter,
        next_quarter_eps_estimate=next_quarter,
        last_fiscal_year_end=snapshot.last_fiscal_year_end,
        next_fiscal_year_end=snapshot.next_fiscal_year_end,
        most_recent_quarter=snapshot.most_recent_quarter,
        source_timestamp=snapshot.source_timestamp,
        forward_eps_matches_current_year=current_match,
        forward_eps_current_year_difference_percent=current_diff,
        forward_eps_matches_next_year=next_match,
        forward_eps_next_year_difference_percent=next_diff,
        match_tolerance_percent=match_tolerance_percent,
        ambiguity_level=ambiguity,
        warnings=_deduplicate(warnings),
        calculation_steps=tuple(steps),
        raw_field_sources=snapshot.raw_field_sources,
    )


def _status(
    snapshot: YahooEPSRawSnapshot,
    current_year: float | None,
    next_year: float | None,
    current_quarter: float | None,
    next_quarter: float | None,
) -> EPSInspectionStatus:
    if (
        snapshot.trailing_eps is None
        and snapshot.forward_eps is None
        and current_year is None
        and next_year is None
        and current_quarter is None
        and next_quarter is None
    ):
        return EPSInspectionStatus.UNAVAILABLE
    if current_year is None or next_year is None:
        return EPSInspectionStatus.PARTIAL
    return EPSInspectionStatus.COMPLETE


def _ambiguity(
    *,
    period_type: EPSPeriodType,
    period_label: str | None,
    basis_type: EPSBasisType,
    status: EPSInspectionStatus,
    current_match: bool | None,
    next_match: bool | None,
) -> EPSAmbiguityLevel:
    if status == EPSInspectionStatus.UNAVAILABLE:
        return EPSAmbiguityLevel.HIGH
    if current_match and next_match:
        return EPSAmbiguityLevel.HIGH
    if period_type == EPSPeriodType.UNKNOWN:
        return EPSAmbiguityLevel.HIGH
    if basis_type == EPSBasisType.UNKNOWN or period_label is None:
        return EPSAmbiguityLevel.MEDIUM
    return EPSAmbiguityLevel.LOW


def _difference_percent(
    forward_eps: float | None,
    estimate: float | None,
) -> float | None:
    if forward_eps is None or estimate is None:
        return None
    return abs(forward_eps - estimate) / max(abs(estimate), _SMALL_EPSILON) * 100


def _matches(
    difference_percent: float | None,
    tolerance_percent: float,
) -> bool | None:
    if difference_percent is None:
        return None
    return difference_percent <= tolerance_percent


def _estimate_value(estimate: object) -> float | None:
    return None if estimate is None else estimate.estimate


def _forward_eps_raw_field(sources: tuple[EPSRawFieldSource, ...]) -> str | None:
    for source in sources:
        if source.normalized_name == "forward_eps":
            return f'{source.raw_source}["{source.raw_field}"]'
    return None


def _validate_tolerance(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("match_tolerance_percent must be a finite number.")
    if not isfinite(value):
        raise ValueError("match_tolerance_percent must be finite.")
    if value < 0:
        raise ValueError("match_tolerance_percent must be non-negative.")


def _deduplicate(warnings: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning and warning not in seen:
            result.append(warning)
            seen.add(warning)
    return tuple(result)
