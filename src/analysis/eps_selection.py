from dataclasses import dataclass
from enum import Enum
from math import isfinite

from src.config.eps_selection import EPSSelectionMethod, EPSSelectionRule


MATERIAL_DIFFERENCE_THRESHOLD_PERCENT = 5.0
_SMALL_EPSILON = 1e-9


class EPSSelectionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    FALLBACK_USED = "FALLBACK_USED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EPSSelectionStep:
    name: str
    input_values: tuple[tuple[str, object], ...]
    formula: str | None
    result: float | None
    explanation: str


@dataclass(frozen=True)
class EPSSelectionInputs:
    symbol: str
    legacy_forward_eps: float | None
    legacy_forward_period_label: str | None
    current_year_eps: float | None
    current_year_period_label: str | None
    next_year_eps: float | None
    next_year_period_label: str | None
    rule: EPSSelectionRule


@dataclass(frozen=True)
class EPSSelectionResult:
    symbol: str
    requested_method: EPSSelectionMethod
    applied_method: EPSSelectionMethod | None
    status: EPSSelectionStatus
    selected_eps: float | None
    selected_period_label: str | None
    legacy_forward_eps: float | None
    current_year_eps: float | None
    next_year_eps: float | None
    current_year_weight: float | None
    next_year_weight: float | None
    fallback_reason: str | None
    rationale: str | None
    selected_vs_legacy_difference_percent: float | None
    warnings: tuple[str, ...]
    calculation_steps: tuple[EPSSelectionStep, ...]


def select_eps(inputs: EPSSelectionInputs) -> EPSSelectionResult:
    """Select the EPS value used for fair value from an explicit policy rule."""
    _validate_inputs(inputs)
    method = inputs.rule.method
    steps: list[EPSSelectionStep] = []
    fallback_reason = None

    if method == EPSSelectionMethod.LEGACY_FORWARD:
        selected = inputs.legacy_forward_eps
        applied = EPSSelectionMethod.LEGACY_FORWARD if selected is not None else None
        status = EPSSelectionStatus.COMPLETE if selected is not None else EPSSelectionStatus.UNAVAILABLE
        period = inputs.legacy_forward_period_label or "Yahoo forwardEps"
    elif method == EPSSelectionMethod.CURRENT_YEAR:
        selected, applied, status, period, fallback_reason = _select_current_year(inputs)
    elif method == EPSSelectionMethod.NEXT_YEAR:
        selected, applied, status, period, fallback_reason = _select_next_year(inputs)
    elif method == EPSSelectionMethod.WEIGHTED_CURRENT_NEXT:
        selected, applied, status, period, fallback_reason = _select_weighted(inputs, steps)
    elif method == EPSSelectionMethod.MANUAL:
        selected = inputs.rule.manual_eps
        applied = EPSSelectionMethod.MANUAL
        status = EPSSelectionStatus.COMPLETE
        period = inputs.rule.manual_period_label
    else:
        raise ValueError(f"Unsupported EPS selection method: {method}")

    difference = _difference_percent(selected, inputs.legacy_forward_eps)
    warnings = _warnings(method, selected, inputs.legacy_forward_eps, difference, fallback_reason)
    if not steps:
        steps.append(
            EPSSelectionStep(
                name="select_eps",
                input_values=(
                    ("requested_method", method.value),
                    ("legacy_forward_eps", inputs.legacy_forward_eps),
                    ("current_year_eps", inputs.current_year_eps),
                    ("next_year_eps", inputs.next_year_eps),
                    ("manual_eps", inputs.rule.manual_eps),
                ),
                formula=_formula(method),
                result=selected,
                explanation=f"Selected EPS using {method.value}.",
            )
        )

    return EPSSelectionResult(
        symbol=_normalize_symbol(inputs.symbol),
        requested_method=method,
        applied_method=applied,
        status=status,
        selected_eps=selected,
        selected_period_label=period if selected is not None else None,
        legacy_forward_eps=inputs.legacy_forward_eps,
        current_year_eps=inputs.current_year_eps,
        next_year_eps=inputs.next_year_eps,
        current_year_weight=inputs.rule.current_year_weight,
        next_year_weight=inputs.rule.next_year_weight,
        fallback_reason=fallback_reason,
        rationale=inputs.rule.rationale,
        selected_vs_legacy_difference_percent=difference,
        warnings=warnings,
        calculation_steps=tuple(steps),
    )


def _select_current_year(
    inputs: EPSSelectionInputs,
) -> tuple[float | None, EPSSelectionMethod | None, EPSSelectionStatus, str | None, str | None]:
    if inputs.current_year_eps is not None:
        return (
            inputs.current_year_eps,
            EPSSelectionMethod.CURRENT_YEAR,
            EPSSelectionStatus.COMPLETE,
            inputs.current_year_period_label,
            None,
        )
    if inputs.legacy_forward_eps is not None:
        return (
            inputs.legacy_forward_eps,
            EPSSelectionMethod.LEGACY_FORWARD,
            EPSSelectionStatus.FALLBACK_USED,
            inputs.legacy_forward_period_label or "Yahoo forwardEps",
            "Current-year estimate unavailable; used Yahoo forwardEps.",
        )
    return None, None, EPSSelectionStatus.UNAVAILABLE, None, "Current-year estimate and Yahoo forwardEps are unavailable."


def _select_next_year(
    inputs: EPSSelectionInputs,
) -> tuple[float | None, EPSSelectionMethod | None, EPSSelectionStatus, str | None, str | None]:
    if inputs.next_year_eps is not None:
        return (
            inputs.next_year_eps,
            EPSSelectionMethod.NEXT_YEAR,
            EPSSelectionStatus.COMPLETE,
            inputs.next_year_period_label,
            None,
        )
    if inputs.legacy_forward_eps is not None:
        return (
            inputs.legacy_forward_eps,
            EPSSelectionMethod.LEGACY_FORWARD,
            EPSSelectionStatus.FALLBACK_USED,
            inputs.legacy_forward_period_label or "Yahoo forwardEps",
            "Next-year estimate unavailable; used Yahoo forwardEps.",
        )
    return None, None, EPSSelectionStatus.UNAVAILABLE, None, "Next-year estimate and Yahoo forwardEps are unavailable."


def _select_weighted(
    inputs: EPSSelectionInputs,
    steps: list[EPSSelectionStep],
) -> tuple[float | None, EPSSelectionMethod | None, EPSSelectionStatus, str | None, str | None]:
    current_weight = inputs.rule.current_year_weight
    next_weight = inputs.rule.next_year_weight
    if current_weight is None or next_weight is None:
        raise ValueError("weighted EPS selection requires both weights.")

    if inputs.current_year_eps is not None and inputs.next_year_eps is not None:
        selected = (
            inputs.current_year_eps * current_weight
            + inputs.next_year_eps * next_weight
        )
        period = (
            f"{current_weight:.2f}*{inputs.current_year_period_label or '0y'} + "
            f"{next_weight:.2f}*{inputs.next_year_period_label or '+1y'}"
        )
        steps.append(
            EPSSelectionStep(
                name="weighted_current_next",
                input_values=(
                    ("current_year_eps", inputs.current_year_eps),
                    ("current_year_weight", current_weight),
                    ("next_year_eps", inputs.next_year_eps),
                    ("next_year_weight", next_weight),
                ),
                formula=(
                    "current_year_eps * current_year_weight + "
                    "next_year_eps * next_year_weight"
                ),
                result=selected,
                explanation="Calculated weighted current-year and next-year EPS.",
            )
        )
        return selected, EPSSelectionMethod.WEIGHTED_CURRENT_NEXT, EPSSelectionStatus.COMPLETE, period, None

    if inputs.current_year_eps is not None:
        return (
            inputs.current_year_eps,
            EPSSelectionMethod.CURRENT_YEAR,
            EPSSelectionStatus.FALLBACK_USED,
            inputs.current_year_period_label,
            "Next-year estimate unavailable; used current-year EPS only.",
        )
    if inputs.next_year_eps is not None:
        return (
            inputs.next_year_eps,
            EPSSelectionMethod.NEXT_YEAR,
            EPSSelectionStatus.FALLBACK_USED,
            inputs.next_year_period_label,
            "Current-year estimate unavailable; used next-year EPS only.",
        )
    if inputs.legacy_forward_eps is not None:
        return (
            inputs.legacy_forward_eps,
            EPSSelectionMethod.LEGACY_FORWARD,
            EPSSelectionStatus.FALLBACK_USED,
            inputs.legacy_forward_period_label or "Yahoo forwardEps",
            "Annual estimates unavailable; used Yahoo forwardEps.",
        )
    return None, None, EPSSelectionStatus.UNAVAILABLE, None, "Annual estimates and Yahoo forwardEps are unavailable."


def _warnings(
    requested_method: EPSSelectionMethod,
    selected: float | None,
    legacy: float | None,
    difference_percent: float | None,
    fallback_reason: str | None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if fallback_reason:
        warnings.append(fallback_reason)
    if selected is None:
        warnings.append("EPS selection did not produce a valuation EPS.")
    if (
        requested_method != EPSSelectionMethod.LEGACY_FORWARD
        and difference_percent is not None
        and abs(difference_percent) > MATERIAL_DIFFERENCE_THRESHOLD_PERCENT
    ):
        warnings.append(
            "Fair-value EPS differs from Yahoo forwardEps by "
            f"{abs(difference_percent):.2f}%; Target PE growth logic still uses "
            "Yahoo forwardEps in this version."
        )
    return tuple(warnings)


def _difference_percent(selected: float | None, legacy: float | None) -> float | None:
    if selected is None or legacy is None:
        return None
    return (selected - legacy) / max(abs(legacy), _SMALL_EPSILON) * 100


def _formula(method: EPSSelectionMethod) -> str | None:
    return {
        EPSSelectionMethod.LEGACY_FORWARD: "legacy_forward_eps",
        EPSSelectionMethod.CURRENT_YEAR: "current_year_eps",
        EPSSelectionMethod.NEXT_YEAR: "next_year_eps",
        EPSSelectionMethod.WEIGHTED_CURRENT_NEXT: (
            "current_year_eps * current_year_weight + "
            "next_year_eps * next_year_weight"
        ),
        EPSSelectionMethod.MANUAL: "manual_eps",
    }[method]


def _validate_inputs(inputs: EPSSelectionInputs) -> None:
    _normalize_symbol(inputs.symbol)
    for field_name in (
        "legacy_forward_eps",
        "current_year_eps",
        "next_year_eps",
    ):
        _validate_optional_number(field_name, getattr(inputs, field_name))


def _validate_optional_number(field_name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number or None.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    if any(character.isspace() for character in normalized):
        raise ValueError("symbol must not contain whitespace.")
    return normalized
