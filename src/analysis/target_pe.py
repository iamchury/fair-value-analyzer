from dataclasses import dataclass
from enum import Enum
from math import isfinite


class AdjustmentCategory(str, Enum):
    GROWTH = "GROWTH"
    PEG = "PEG"
    SECTOR = "SECTOR"
    VALUATION = "VALUATION"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class TargetPEConfig:
    minimum_target_pe: float
    maximum_target_pe: float
    default_target_peg: float
    low_peg_threshold: float
    normal_peg_upper_threshold: float
    high_peg_threshold: float
    low_peg_adjustment: float
    normal_peg_adjustment: float
    elevated_peg_adjustment: float
    high_peg_adjustment: float
    preferred_sector_adjustment: float
    ordinary_sector_adjustment: float
    high_forward_pe_premium_threshold: float
    high_forward_pe_adjustment: float
    preferred_sectors: tuple[str, ...]


@dataclass(frozen=True)
class TargetPEInputs:
    forward_eps_growth_percent: float
    peg_ratio: float | None
    sector: str | None
    industry: str | None
    current_forward_pe: float | None


@dataclass(frozen=True)
class TargetPEAdjustment:
    category: AdjustmentCategory
    label: str
    value: float
    explanation: str


@dataclass(frozen=True)
class TargetPERecommendation:
    growth_based_pe: float
    raw_target_pe: float
    recommended_target_pe: float
    minimum_target_pe: float
    maximum_target_pe: float
    was_minimum_applied: bool
    was_maximum_applied: bool
    adjustments: tuple[TargetPEAdjustment, ...]


def validate_target_pe_config(config: TargetPEConfig) -> None:
    """Validate rule configuration for Target PE recommendation."""
    for field_name, value in (
        ("minimum_target_pe", config.minimum_target_pe),
        ("maximum_target_pe", config.maximum_target_pe),
        ("default_target_peg", config.default_target_peg),
        ("low_peg_threshold", config.low_peg_threshold),
        ("normal_peg_upper_threshold", config.normal_peg_upper_threshold),
        ("high_peg_threshold", config.high_peg_threshold),
        ("low_peg_adjustment", config.low_peg_adjustment),
        ("normal_peg_adjustment", config.normal_peg_adjustment),
        ("elevated_peg_adjustment", config.elevated_peg_adjustment),
        ("high_peg_adjustment", config.high_peg_adjustment),
        ("preferred_sector_adjustment", config.preferred_sector_adjustment),
        ("ordinary_sector_adjustment", config.ordinary_sector_adjustment),
        (
            "high_forward_pe_premium_threshold",
            config.high_forward_pe_premium_threshold,
        ),
        ("high_forward_pe_adjustment", config.high_forward_pe_adjustment),
    ):
        _require_finite(field_name, value)

    if config.minimum_target_pe <= 0:
        raise ValueError("minimum_target_pe must be greater than 0.")
    if config.maximum_target_pe <= config.minimum_target_pe:
        raise ValueError("maximum_target_pe must be greater than minimum_target_pe.")
    if config.default_target_peg <= 0:
        raise ValueError("default_target_peg must be greater than 0.")
    if config.low_peg_threshold <= 0:
        raise ValueError("low_peg_threshold must be greater than 0.")
    if config.normal_peg_upper_threshold <= config.low_peg_threshold:
        raise ValueError(
            "normal_peg_upper_threshold must be greater than low_peg_threshold."
        )
    if config.high_peg_threshold <= config.normal_peg_upper_threshold:
        raise ValueError(
            "high_peg_threshold must be greater than normal_peg_upper_threshold."
        )
    if config.high_forward_pe_premium_threshold <= 0:
        raise ValueError(
            "high_forward_pe_premium_threshold must be greater than 0."
        )
    for sector in config.preferred_sectors:
        if not isinstance(sector, str) or not sector.strip():
            raise ValueError("preferred_sectors must not contain empty strings.")


def validate_target_pe_inputs(inputs: TargetPEInputs) -> None:
    """Validate inputs used by the Target PE recommendation engine."""
    _require_finite(
        "forward_eps_growth_percent",
        inputs.forward_eps_growth_percent,
    )
    if inputs.peg_ratio is not None:
        _require_finite("peg_ratio", inputs.peg_ratio)
        if inputs.peg_ratio <= 0:
            raise ValueError("peg_ratio must be greater than 0 when present.")
    if inputs.current_forward_pe is not None:
        _require_finite("current_forward_pe", inputs.current_forward_pe)


def calculate_growth_based_pe(
    forward_eps_growth_percent: float,
    config: TargetPEConfig,
) -> float:
    """Calculate PE implied by EPS growth and target PEG."""
    validate_target_pe_config(config)
    _require_finite("forward_eps_growth_percent", forward_eps_growth_percent)
    return forward_eps_growth_percent * config.default_target_peg


def calculate_peg_adjustment(
    peg_ratio: float | None,
    config: TargetPEConfig,
) -> TargetPEAdjustment:
    """Calculate Target PE adjustment from PEG ratio bands."""
    validate_target_pe_config(config)
    if peg_ratio is None:
        return TargetPEAdjustment(
            category=AdjustmentCategory.PEG,
            label="PEG unavailable",
            value=0.0,
            explanation="PEG data was unavailable, so no PEG adjustment was applied.",
        )
    _require_finite("peg_ratio", peg_ratio)
    if peg_ratio <= 0:
        raise ValueError("peg_ratio must be greater than 0 when present.")

    if peg_ratio < config.low_peg_threshold:
        label = f"PEG below {config.low_peg_threshold}"
        value = config.low_peg_adjustment
        explanation = (
            f"PEG of {peg_ratio} indicates growth is inexpensive relative "
            "to valuation."
        )
    elif peg_ratio <= config.normal_peg_upper_threshold:
        label = "PEG normal"
        value = config.normal_peg_adjustment
        explanation = f"PEG of {peg_ratio} is within the normal valuation range."
    elif peg_ratio <= config.high_peg_threshold:
        label = "PEG elevated"
        value = config.elevated_peg_adjustment
        explanation = f"PEG of {peg_ratio} is elevated relative to growth."
    else:
        label = f"PEG above {config.high_peg_threshold}"
        value = config.high_peg_adjustment
        explanation = f"PEG of {peg_ratio} is high relative to growth."

    return TargetPEAdjustment(
        category=AdjustmentCategory.PEG,
        label=label,
        value=value,
        explanation=explanation,
    )


def calculate_sector_adjustment(
    sector: str | None,
    industry: str | None,
    config: TargetPEConfig,
) -> TargetPEAdjustment:
    """Calculate Target PE adjustment from sector or industry classification."""
    validate_target_pe_config(config)
    preferred = {_normalize_text(value) for value in config.preferred_sectors}
    sector_key = _normalize_text(sector)
    industry_key = _normalize_text(industry)

    if sector_key is None and industry_key is None:
        return TargetPEAdjustment(
            category=AdjustmentCategory.SECTOR,
            label="Sector unavailable",
            value=config.ordinary_sector_adjustment,
            explanation=(
                "Sector data was unavailable, so no preferred-sector premium "
                "was applied."
            ),
        )

    if sector_key in preferred:
        label_source = f"Sector '{sector.strip()}'"
    elif industry_key in preferred:
        label_source = f"Industry '{industry.strip()}'"
    else:
        label_source = ""

    if label_source:
        return TargetPEAdjustment(
            category=AdjustmentCategory.SECTOR,
            label="Preferred growth sector",
            value=config.preferred_sector_adjustment,
            explanation=(
                f"{label_source} qualifies for the preferred-sector premium."
            ),
        )

    return TargetPEAdjustment(
        category=AdjustmentCategory.SECTOR,
        label="Ordinary sector",
        value=config.ordinary_sector_adjustment,
        explanation="No preferred sector or industry classification matched.",
    )


def calculate_forward_pe_adjustment(
    current_forward_pe: float | None,
    growth_based_pe: float,
    config: TargetPEConfig,
) -> TargetPEAdjustment:
    """Calculate a caution adjustment for unusually high current Forward PE."""
    validate_target_pe_config(config)
    _require_finite("growth_based_pe", growth_based_pe)

    if current_forward_pe is None:
        return _no_forward_pe_adjustment("Current Forward PE data was unavailable.")
    _require_finite("current_forward_pe", current_forward_pe)
    if current_forward_pe <= 0:
        return _no_forward_pe_adjustment("Current Forward PE was non-positive.")
    if growth_based_pe <= 0:
        return _no_forward_pe_adjustment("Growth-derived PE was non-positive.")

    premium_ratio = current_forward_pe / growth_based_pe
    if premium_ratio > config.high_forward_pe_premium_threshold:
        return TargetPEAdjustment(
            category=AdjustmentCategory.VALUATION,
            label="High current Forward PE",
            value=config.high_forward_pe_adjustment,
            explanation=(
                "Current Forward PE is more than "
                f"{config.high_forward_pe_premium_threshold} times the "
                "growth-derived PE."
            ),
        )

    return _no_forward_pe_adjustment(
        "Current Forward PE premium was not high enough for a valuation penalty."
    )


def recommend_target_pe(
    inputs: TargetPEInputs,
    config: TargetPEConfig,
) -> TargetPERecommendation:
    """Recommend Target PE and return an explainable rule breakdown."""
    validate_target_pe_config(config)
    validate_target_pe_inputs(inputs)

    growth_based_pe = calculate_growth_based_pe(
        inputs.forward_eps_growth_percent,
        config,
    )
    growth_adjustment = TargetPEAdjustment(
        category=AdjustmentCategory.GROWTH,
        label="EPS growth",
        value=growth_based_pe,
        explanation=(
            f"Forward EPS growth of {inputs.forward_eps_growth_percent}% "
            f"produced a base PE of {growth_based_pe}."
        ),
    )
    peg_adjustment = calculate_peg_adjustment(inputs.peg_ratio, config)
    sector_adjustment = calculate_sector_adjustment(
        inputs.sector,
        inputs.industry,
        config,
    )
    forward_pe_adjustment = calculate_forward_pe_adjustment(
        inputs.current_forward_pe,
        growth_based_pe,
        config,
    )

    raw_target_pe = (
        growth_based_pe
        + peg_adjustment.value
        + sector_adjustment.value
        + forward_pe_adjustment.value
    )
    recommended_target_pe = min(
        max(raw_target_pe, config.minimum_target_pe),
        config.maximum_target_pe,
    )
    was_minimum_applied = recommended_target_pe > raw_target_pe
    was_maximum_applied = recommended_target_pe < raw_target_pe

    adjustments = (
        growth_adjustment,
        peg_adjustment,
        sector_adjustment,
        forward_pe_adjustment,
    )
    if was_minimum_applied or was_maximum_applied:
        adjustments = adjustments + (
            _limit_adjustment(raw_target_pe, recommended_target_pe, config),
        )

    return TargetPERecommendation(
        growth_based_pe=growth_based_pe,
        raw_target_pe=raw_target_pe,
        recommended_target_pe=recommended_target_pe,
        minimum_target_pe=config.minimum_target_pe,
        maximum_target_pe=config.maximum_target_pe,
        was_minimum_applied=was_minimum_applied,
        was_maximum_applied=was_maximum_applied,
        adjustments=adjustments,
    )


def _no_forward_pe_adjustment(explanation: str) -> TargetPEAdjustment:
    return TargetPEAdjustment(
        category=AdjustmentCategory.VALUATION,
        label="No current Forward PE penalty",
        value=0.0,
        explanation=explanation,
    )


def _limit_adjustment(
    raw_target_pe: float,
    recommended_target_pe: float,
    config: TargetPEConfig,
) -> TargetPEAdjustment:
    if recommended_target_pe == config.maximum_target_pe:
        return TargetPEAdjustment(
            category=AdjustmentCategory.LIMIT,
            label="Maximum Target PE",
            value=recommended_target_pe - raw_target_pe,
            explanation=(
                "Target PE was capped at the configured maximum of "
                f"{config.maximum_target_pe}."
            ),
        )

    return TargetPEAdjustment(
        category=AdjustmentCategory.LIMIT,
        label="Minimum Target PE",
        value=recommended_target_pe - raw_target_pe,
        explanation=(
            "Target PE was raised to the configured minimum of "
            f"{config.minimum_target_pe}."
        ),
    )


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _require_finite(field_name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
