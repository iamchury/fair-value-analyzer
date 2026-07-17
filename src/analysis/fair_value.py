from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FairValueInputs:
    forward_eps: float
    recommended_target_pe: float
    macro_adjustment_multiplier: float = 1.0


@dataclass(frozen=True)
class FairValueResult:
    forward_eps: float
    recommended_target_pe: float
    macro_adjustment_multiplier: float
    base_fair_value: float
    adjusted_fair_value: float


def validate_fair_value_inputs(inputs: FairValueInputs) -> None:
    """Validate inputs for fair-value calculation."""
    _require_number("forward_eps", inputs.forward_eps)
    _require_number("recommended_target_pe", inputs.recommended_target_pe)
    _require_number(
        "macro_adjustment_multiplier",
        inputs.macro_adjustment_multiplier,
    )

    if inputs.recommended_target_pe <= 0:
        raise ValueError("recommended_target_pe must be greater than 0.")
    if inputs.macro_adjustment_multiplier < 0:
        raise ValueError("macro_adjustment_multiplier must be non-negative.")


def calculate_base_fair_value(
    forward_eps: float,
    recommended_target_pe: float,
) -> float:
    """Calculate base fair value from forward EPS and recommended Target PE."""
    _require_number("forward_eps", forward_eps)
    _require_number("recommended_target_pe", recommended_target_pe)
    if recommended_target_pe <= 0:
        raise ValueError("recommended_target_pe must be greater than 0.")
    return forward_eps * recommended_target_pe


def calculate_adjusted_fair_value(
    base_fair_value: float,
    macro_adjustment_multiplier: float,
) -> float:
    """Apply a macro adjustment multiplier to base fair value."""
    _require_number("base_fair_value", base_fair_value)
    _require_number(
        "macro_adjustment_multiplier",
        macro_adjustment_multiplier,
    )
    if macro_adjustment_multiplier < 0:
        raise ValueError("macro_adjustment_multiplier must be non-negative.")
    return base_fair_value * macro_adjustment_multiplier


def calculate_fair_value(inputs: FairValueInputs) -> FairValueResult:
    """Calculate base and macro-adjusted fair value."""
    validate_fair_value_inputs(inputs)
    base_fair_value = calculate_base_fair_value(
        inputs.forward_eps,
        inputs.recommended_target_pe,
    )
    adjusted_fair_value = calculate_adjusted_fair_value(
        base_fair_value,
        inputs.macro_adjustment_multiplier,
    )
    return FairValueResult(
        forward_eps=inputs.forward_eps,
        recommended_target_pe=inputs.recommended_target_pe,
        macro_adjustment_multiplier=inputs.macro_adjustment_multiplier,
        base_fair_value=base_fair_value,
        adjusted_fair_value=adjusted_fair_value,
    )


def _require_number(field_name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
