from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from src.config.valuation_profiles import ValuationProfile


class ResearchValuationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ResearchValuationInputs:
    profile: ValuationProfile
    macro_adjustment_multiplier: float


@dataclass(frozen=True)
class ResearchValuationResult:
    profile: ValuationProfile
    status: ResearchValuationStatus
    macro_adjustment_multiplier: float
    research_base_fair_value: float
    research_adjusted_fair_value: float
    dcf_fair_value: float | None


@dataclass(frozen=True)
class ValuationComparisonResult:
    automatic_fair_value: float | None
    research_fair_value: float
    dcf_fair_value: float | None
    automatic_vs_research_difference: float | None
    automatic_vs_research_difference_percent: float | None
    research_vs_dcf_difference: float | None
    research_vs_dcf_difference_percent: float | None


def calculate_research_valuation(
    inputs: ResearchValuationInputs,
) -> ResearchValuationResult:
    """Calculate research fair value from configured EPS and Target PE."""
    _require_number(
        "macro_adjustment_multiplier",
        inputs.macro_adjustment_multiplier,
    )
    if inputs.macro_adjustment_multiplier < 0:
        raise ValueError("macro_adjustment_multiplier must be non-negative.")

    profile = inputs.profile
    base_fair_value = profile.valuation_eps * profile.target_pe
    adjusted_fair_value = base_fair_value * inputs.macro_adjustment_multiplier
    status = (
        ResearchValuationStatus.COMPLETE
        if adjusted_fair_value > 0
        else ResearchValuationStatus.NOT_APPLICABLE
    )
    return ResearchValuationResult(
        profile=profile,
        status=status,
        macro_adjustment_multiplier=inputs.macro_adjustment_multiplier,
        research_base_fair_value=base_fair_value,
        research_adjusted_fair_value=adjusted_fair_value,
        dcf_fair_value=profile.dcf_fair_value,
    )


def compare_valuations(
    automatic_fair_value: float | None,
    research: ResearchValuationResult,
) -> ValuationComparisonResult:
    """Compare automatic fair value, research fair value, and DCF reference."""
    if automatic_fair_value is not None:
        _require_number("automatic_fair_value", automatic_fair_value)

    research_value = research.research_adjusted_fair_value
    automatic_difference = (
        None
        if automatic_fair_value is None
        else automatic_fair_value - research_value
    )
    automatic_difference_percent = _percent_difference(
        automatic_difference,
        research_value,
    )

    dcf_value = research.dcf_fair_value
    if dcf_value is None:
        dcf_difference = None
        dcf_difference_percent = None
    else:
        dcf_difference = research_value - dcf_value
        dcf_difference_percent = _percent_difference(dcf_difference, dcf_value)

    return ValuationComparisonResult(
        automatic_fair_value=automatic_fair_value,
        research_fair_value=research_value,
        dcf_fair_value=dcf_value,
        automatic_vs_research_difference=automatic_difference,
        automatic_vs_research_difference_percent=automatic_difference_percent,
        research_vs_dcf_difference=dcf_difference,
        research_vs_dcf_difference_percent=dcf_difference_percent,
    )


def _percent_difference(difference: float | None, denominator: float) -> float | None:
    if difference is None or denominator == 0:
        return None
    return difference / abs(denominator) * 100


def _require_number(field_name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
