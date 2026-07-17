from dataclasses import dataclass
from enum import Enum
from math import isclose, isfinite


class YieldTrend(str, Enum):
    RISING = "RISING"
    NEUTRAL = "NEUTRAL"
    FALLING = "FALLING"


@dataclass(frozen=True)
class TreasuryYieldConfig:
    threshold_yield_percent: float
    maximum_discount_percent: float
    trend_tolerance_percentage_points: float
    rising_adjustment_percent: float
    neutral_adjustment_percent: float
    falling_adjustment_percent: float


@dataclass(frozen=True)
class MacroAdjustment:
    current_yield_percent: float
    sma_short_percent: float
    sma_long_percent: float
    trend: YieldTrend
    level_discount_percent: float
    trend_adjustment_percent: float
    total_adjustment_multiplier: float


def validate_config(config: TreasuryYieldConfig) -> None:
    """Validate treasury-yield macro adjustment configuration."""
    _require_finite("threshold_yield_percent", config.threshold_yield_percent)
    _require_finite("maximum_discount_percent", config.maximum_discount_percent)
    _require_finite(
        "trend_tolerance_percentage_points",
        config.trend_tolerance_percentage_points,
    )
    _validate_adjustment(
        "rising_adjustment_percent",
        config.rising_adjustment_percent,
    )
    _validate_adjustment(
        "neutral_adjustment_percent",
        config.neutral_adjustment_percent,
    )
    _validate_adjustment(
        "falling_adjustment_percent",
        config.falling_adjustment_percent,
    )

    if config.threshold_yield_percent <= 0:
        raise ValueError("threshold_yield_percent must be greater than 0.")
    if config.maximum_discount_percent < 0:
        raise ValueError("maximum_discount_percent must be non-negative.")
    if config.maximum_discount_percent >= 100:
        raise ValueError("maximum_discount_percent must be less than 100.")
    if config.trend_tolerance_percentage_points < 0:
        raise ValueError(
            "trend_tolerance_percentage_points must be non-negative."
        )


def calculate_yield_level_discount(
    current_yield_percent: float,
    config: TreasuryYieldConfig,
) -> float:
    """Calculate valuation discount from the current Treasury yield level."""
    validate_config(config)
    _validate_positive("current_yield_percent", current_yield_percent)

    if current_yield_percent <= config.threshold_yield_percent:
        return 0.0

    excess = (current_yield_percent - config.threshold_yield_percent) * 10
    raw_discount_percent = excess**2
    return min(raw_discount_percent, config.maximum_discount_percent)


def classify_yield_trend(
    current_yield_percent: float,
    sma_short_percent: float,
    sma_long_percent: float,
    config: TreasuryYieldConfig,
) -> YieldTrend:
    """Classify Treasury yield trend using current yield and two SMAs."""
    validate_config(config)
    _validate_yield_inputs(
        current_yield_percent,
        sma_short_percent,
        sma_long_percent,
    )

    tolerance = config.trend_tolerance_percentage_points
    short_gap = current_yield_percent - sma_short_percent
    if _is_greater_than_tolerance(short_gap, tolerance) and (
        sma_short_percent > sma_long_percent
    ):
        return YieldTrend.RISING
    if _is_greater_than_tolerance(-short_gap, tolerance) and (
        sma_short_percent < sma_long_percent
    ):
        return YieldTrend.FALLING
    return YieldTrend.NEUTRAL


def get_trend_adjustment_percent(
    trend: YieldTrend,
    config: TreasuryYieldConfig,
) -> float:
    """Return configured valuation adjustment percent for a yield trend."""
    validate_config(config)
    if trend == YieldTrend.RISING:
        return config.rising_adjustment_percent
    if trend == YieldTrend.FALLING:
        return config.falling_adjustment_percent
    if trend == YieldTrend.NEUTRAL:
        return config.neutral_adjustment_percent
    raise ValueError(f"Unsupported yield trend: {trend}")


def calculate_total_adjustment_multiplier(
    level_discount_percent: float,
    trend_adjustment_percent: float,
) -> float:
    """Combine yield-level discount and trend adjustment into a multiplier."""
    _require_finite("level_discount_percent", level_discount_percent)
    _validate_adjustment("trend_adjustment_percent", trend_adjustment_percent)
    if level_discount_percent < 0:
        raise ValueError("level_discount_percent must be non-negative.")

    multiplier = (1 - level_discount_percent / 100) * (
        1 + trend_adjustment_percent / 100
    )
    if multiplier < 0:
        raise ValueError("total_adjustment_multiplier must be non-negative.")
    return multiplier


def calculate_macro_adjustment(
    current_yield_percent: float,
    sma_short_percent: float,
    sma_long_percent: float,
    config: TreasuryYieldConfig,
) -> MacroAdjustment:
    """Calculate the complete macro interest-rate adjustment result."""
    level_discount_percent = calculate_yield_level_discount(
        current_yield_percent,
        config,
    )
    trend = classify_yield_trend(
        current_yield_percent,
        sma_short_percent,
        sma_long_percent,
        config,
    )
    trend_adjustment_percent = get_trend_adjustment_percent(trend, config)
    total_adjustment_multiplier = calculate_total_adjustment_multiplier(
        level_discount_percent,
        trend_adjustment_percent,
    )

    return MacroAdjustment(
        current_yield_percent=current_yield_percent,
        sma_short_percent=sma_short_percent,
        sma_long_percent=sma_long_percent,
        trend=trend,
        level_discount_percent=level_discount_percent,
        trend_adjustment_percent=trend_adjustment_percent,
        total_adjustment_multiplier=total_adjustment_multiplier,
    )


def adjust_fair_value(
    base_fair_value: float,
    total_adjustment_multiplier: float,
) -> float:
    """Apply a macro adjustment multiplier to a base fair value."""
    _require_finite("base_fair_value", base_fair_value)
    _require_finite(
        "total_adjustment_multiplier",
        total_adjustment_multiplier,
    )
    if base_fair_value < 0:
        raise ValueError("base_fair_value must be non-negative.")
    if total_adjustment_multiplier < 0:
        raise ValueError("total_adjustment_multiplier must be non-negative.")
    return base_fair_value * total_adjustment_multiplier


def _validate_yield_inputs(
    current_yield_percent: float,
    sma_short_percent: float,
    sma_long_percent: float,
) -> None:
    _validate_positive("current_yield_percent", current_yield_percent)
    _validate_positive("sma_short_percent", sma_short_percent)
    _validate_positive("sma_long_percent", sma_long_percent)


def _validate_positive(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def _validate_adjustment(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= -100:
        raise ValueError(f"{name} must be greater than -100.")


def _is_greater_than_tolerance(value: float, tolerance: float) -> bool:
    return value > tolerance and not isclose(value, tolerance)


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")
