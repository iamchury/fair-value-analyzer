from dataclasses import dataclass
from enum import Enum
from math import isfinite


class EPSTransition(str, Enum):
    POSITIVE_GROWTH = "POSITIVE_GROWTH"
    NEGATIVE_GROWTH = "NEGATIVE_GROWTH"
    FLAT = "FLAT"
    LOSS_TO_PROFIT = "LOSS_TO_PROFIT"
    PROFIT_TO_LOSS = "PROFIT_TO_LOSS"
    LOSS_NARROWING = "LOSS_NARROWING"
    LOSS_WIDENING = "LOSS_WIDENING"
    ZERO_BASE = "ZERO_BASE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class EPSGrowthInputs:
    trailing_eps: float | None
    forward_eps: float | None


@dataclass(frozen=True)
class EPSGrowthResult:
    trailing_eps: float | None
    forward_eps: float | None
    growth_percent: float | None
    transition: EPSTransition
    is_growth_rate_usable_for_target_pe: bool
    explanation: str


def validate_eps_growth_inputs(inputs: EPSGrowthInputs) -> None:
    """Validate EPS values used for forward EPS growth calculation."""
    if not isinstance(inputs, EPSGrowthInputs):
        raise ValueError("inputs must be EPSGrowthInputs.")

    _require_optional_number("trailing_eps", inputs.trailing_eps)
    _require_optional_number("forward_eps", inputs.forward_eps)


def classify_eps_transition(
    trailing_eps: float | None,
    forward_eps: float | None,
) -> EPSTransition:
    """Classify the economic EPS transition before using the growth number."""
    if trailing_eps is None or forward_eps is None:
        return EPSTransition.UNAVAILABLE
    if trailing_eps == 0:
        return EPSTransition.ZERO_BASE
    if trailing_eps < 0 and forward_eps >= 0:
        return EPSTransition.LOSS_TO_PROFIT
    if trailing_eps > 0 and forward_eps < 0:
        return EPSTransition.PROFIT_TO_LOSS
    if trailing_eps > 0 and forward_eps > trailing_eps:
        return EPSTransition.POSITIVE_GROWTH
    if trailing_eps > 0 and forward_eps < trailing_eps:
        return EPSTransition.NEGATIVE_GROWTH
    if trailing_eps > 0 and forward_eps == trailing_eps:
        return EPSTransition.FLAT
    if trailing_eps < 0 and forward_eps < 0:
        if abs(forward_eps) < abs(trailing_eps):
            return EPSTransition.LOSS_NARROWING
        if abs(forward_eps) > abs(trailing_eps):
            return EPSTransition.LOSS_WIDENING
        return EPSTransition.FLAT

    raise ValueError("unsupported EPS transition.")


def calculate_eps_growth_percent(
    trailing_eps: float,
    forward_eps: float,
) -> float:
    """Calculate forward EPS growth percent without rounding."""
    _require_number("trailing_eps", trailing_eps)
    _require_number("forward_eps", forward_eps)
    if trailing_eps == 0:
        raise ValueError("trailing_eps must not be zero.")
    return (forward_eps - trailing_eps) / abs(trailing_eps) * 100


def is_growth_rate_usable_for_target_pe(
    trailing_eps: float | None,
    forward_eps: float | None,
    transition: EPSTransition,
) -> bool:
    """Return whether growth can feed the conventional Target PE engine."""
    return (
        trailing_eps is not None
        and forward_eps is not None
        and trailing_eps > 0
        and forward_eps >= 0
        and transition
        in {
            EPSTransition.POSITIVE_GROWTH,
            EPSTransition.NEGATIVE_GROWTH,
            EPSTransition.FLAT,
        }
    )


def calculate_eps_growth(inputs: EPSGrowthInputs) -> EPSGrowthResult:
    """Calculate EPS growth and explain whether it is usable for Target PE."""
    validate_eps_growth_inputs(inputs)
    transition = classify_eps_transition(inputs.trailing_eps, inputs.forward_eps)

    if transition in {EPSTransition.UNAVAILABLE, EPSTransition.ZERO_BASE}:
        growth_percent = None
    else:
        growth_percent = calculate_eps_growth_percent(
            inputs.trailing_eps,
            inputs.forward_eps,
        )

    usable = is_growth_rate_usable_for_target_pe(
        inputs.trailing_eps,
        inputs.forward_eps,
        transition,
    )

    return EPSGrowthResult(
        trailing_eps=inputs.trailing_eps,
        forward_eps=inputs.forward_eps,
        growth_percent=growth_percent,
        transition=transition,
        is_growth_rate_usable_for_target_pe=usable,
        explanation=_build_explanation(
            inputs.trailing_eps,
            inputs.forward_eps,
            growth_percent,
            transition,
        ),
    )


def _build_explanation(
    trailing_eps: float | None,
    forward_eps: float | None,
    growth_percent: float | None,
    transition: EPSTransition,
) -> str:
    if transition == EPSTransition.UNAVAILABLE:
        return "Trailing EPS and Forward EPS are both required to calculate EPS growth."
    if transition == EPSTransition.ZERO_BASE:
        return "Trailing EPS is zero, so percentage EPS growth cannot be calculated."
    if transition == EPSTransition.POSITIVE_GROWTH:
        return (
            f"Forward EPS increases from {_fmt(trailing_eps)} to {_fmt(forward_eps)}, "
            f"representing growth of {_fmt(growth_percent)}%."
        )
    if transition == EPSTransition.NEGATIVE_GROWTH:
        return (
            f"Forward EPS decreases from {_fmt(trailing_eps)} to {_fmt(forward_eps)}, "
            f"representing growth of {_fmt(growth_percent)}%."
        )
    if transition == EPSTransition.FLAT:
        return f"Forward EPS is unchanged from trailing EPS at {_fmt(trailing_eps)}."
    if transition == EPSTransition.LOSS_TO_PROFIT:
        return (
            f"EPS changes from a loss of {_fmt(trailing_eps)} to {_fmt(forward_eps)}; "
            f"the mathematical change is {_fmt(growth_percent)}%, but it is not "
            "a conventional growth rate for Target PE."
        )
    if transition == EPSTransition.PROFIT_TO_LOSS:
        return (
            f"EPS changes from a profit of {_fmt(trailing_eps)} to a loss of "
            f"{_fmt(forward_eps)}; the mathematical change is {_fmt(growth_percent)}%, "
            "but it is not usable as a conventional Target PE growth rate."
        )
    if transition == EPSTransition.LOSS_NARROWING:
        return (
            f"The projected loss narrows from {_fmt(trailing_eps)} to {_fmt(forward_eps)}; "
            f"the mathematical change is {_fmt(growth_percent)}%, but it is not usable "
            "as a conventional Target PE growth rate."
        )
    if transition == EPSTransition.LOSS_WIDENING:
        return (
            f"The projected loss widens from {_fmt(trailing_eps)} to {_fmt(forward_eps)}; "
            f"the mathematical change is {_fmt(growth_percent)}%, but it is not usable "
            "as a conventional Target PE growth rate."
        )
    raise ValueError(f"Unsupported EPS transition: {transition}")


def _require_optional_number(field_name: str, value: float | None) -> None:
    if value is None:
        return
    _require_number(field_name, value)


def _require_number(field_name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number or None.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _fmt(value: float | None) -> str:
    if value is None:
        return "None"
    return str(float(value))
