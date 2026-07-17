import math

import pytest

from src.analysis.macro_adjustment import (
    MacroAdjustment,
    TreasuryYieldConfig,
    YieldTrend,
    adjust_fair_value,
    calculate_macro_adjustment,
    calculate_total_adjustment_multiplier,
    calculate_yield_level_discount,
    classify_yield_trend,
    get_trend_adjustment_percent,
    validate_config,
)


@pytest.fixture
def config() -> TreasuryYieldConfig:
    return TreasuryYieldConfig(
        threshold_yield_percent=4.3,
        maximum_discount_percent=25.0,
        trend_tolerance_percentage_points=0.05,
        rising_adjustment_percent=-10.0,
        neutral_adjustment_percent=0.0,
        falling_adjustment_percent=10.0,
    )


@pytest.mark.parametrize(
    ("current_yield_percent", "expected_discount_percent"),
    [
        (4.2, 0.0),
        (4.3, 0.0),
        (4.4, 1.0),
        (4.5, 4.0),
        (4.6, 9.0),
        (4.7, 16.0),
        (4.8, 25.0),
        (5.0, 25.0),
    ],
)
def test_yield_level_discount_examples(
    config: TreasuryYieldConfig,
    current_yield_percent: float,
    expected_discount_percent: float,
) -> None:
    assert calculate_yield_level_discount(
        current_yield_percent,
        config,
    ) == pytest.approx(expected_discount_percent)


def test_below_threshold_yield_has_zero_discount(
    config: TreasuryYieldConfig,
) -> None:
    assert calculate_yield_level_discount(3.9, config) == 0.0


def test_classify_yield_trend_rising(config: TreasuryYieldConfig) -> None:
    assert classify_yield_trend(4.66, 4.60, 4.50, config) == YieldTrend.RISING


def test_classify_yield_trend_falling(config: TreasuryYieldConfig) -> None:
    assert classify_yield_trend(4.44, 4.50, 4.60, config) == YieldTrend.FALLING


def test_classify_yield_trend_neutral(config: TreasuryYieldConfig) -> None:
    assert classify_yield_trend(4.60, 4.60, 4.50, config) == YieldTrend.NEUTRAL


@pytest.mark.parametrize(
    ("current_yield_percent", "sma_short_percent", "sma_long_percent"),
    [
        (4.65, 4.60, 4.50),
        (4.55, 4.60, 4.70),
    ],
)
def test_exact_tolerance_boundary_is_neutral(
    config: TreasuryYieldConfig,
    current_yield_percent: float,
    sma_short_percent: float,
    sma_long_percent: float,
) -> None:
    assert (
        classify_yield_trend(
            current_yield_percent,
            sma_short_percent,
            sma_long_percent,
            config,
        )
        == YieldTrend.NEUTRAL
    )


@pytest.mark.parametrize(
    ("trend", "expected_adjustment_percent"),
    [
        (YieldTrend.RISING, -10.0),
        (YieldTrend.NEUTRAL, 0.0),
        (YieldTrend.FALLING, 10.0),
    ],
)
def test_get_trend_adjustment_percent(
    config: TreasuryYieldConfig,
    trend: YieldTrend,
    expected_adjustment_percent: float,
) -> None:
    assert get_trend_adjustment_percent(trend, config) == expected_adjustment_percent


def test_total_adjustment_multiplier() -> None:
    assert calculate_total_adjustment_multiplier(9.0, -10.0) == pytest.approx(
        0.819
    )


def test_full_calculate_macro_adjustment_result(
    config: TreasuryYieldConfig,
) -> None:
    result = calculate_macro_adjustment(4.6, 4.5, 4.4, config)

    assert isinstance(result, MacroAdjustment)
    assert result.current_yield_percent == 4.6
    assert result.sma_short_percent == 4.5
    assert result.sma_long_percent == 4.4
    assert result.trend == YieldTrend.RISING
    assert result.level_discount_percent == pytest.approx(9.0)
    assert result.trend_adjustment_percent == -10.0
    assert result.total_adjustment_multiplier == pytest.approx(0.819)


def test_adjust_fair_value() -> None:
    assert adjust_fair_value(75.0, 0.819) == pytest.approx(61.425)


def test_zero_fair_value_is_valid() -> None:
    assert adjust_fair_value(0.0, 0.819) == 0.0


@pytest.mark.parametrize(
    "bad_config",
    [
        TreasuryYieldConfig(0.0, 25.0, 0.05, -10.0, 0.0, 10.0),
        TreasuryYieldConfig(4.3, -1.0, 0.05, -10.0, 0.0, 10.0),
        TreasuryYieldConfig(4.3, 100.0, 0.05, -10.0, 0.0, 10.0),
        TreasuryYieldConfig(4.3, 25.0, -0.01, -10.0, 0.0, 10.0),
        TreasuryYieldConfig(4.3, 25.0, 0.05, -100.0, 0.0, 10.0),
        TreasuryYieldConfig(4.3, 25.0, 0.05, -10.0, -100.0, 10.0),
        TreasuryYieldConfig(4.3, 25.0, 0.05, -10.0, 0.0, -100.0),
    ],
)
def test_invalid_configuration_raises(bad_config: TreasuryYieldConfig) -> None:
    with pytest.raises(ValueError):
        validate_config(bad_config)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_invalid_nan_and_infinity_values_raise(
    config: TreasuryYieldConfig,
    bad_value: float,
) -> None:
    with pytest.raises(ValueError):
        calculate_yield_level_discount(bad_value, config)

    with pytest.raises(ValueError):
        classify_yield_trend(bad_value, 4.5, 4.4, config)

    with pytest.raises(ValueError):
        calculate_total_adjustment_multiplier(9.0, bad_value)

    with pytest.raises(ValueError):
        adjust_fair_value(75.0, bad_value)


@pytest.mark.parametrize(
    ("current_yield_percent", "sma_short_percent", "sma_long_percent"),
    [
        (-4.6, 4.5, 4.4),
        (0.0, 4.5, 4.4),
        (4.6, -4.5, 4.4),
        (4.6, 0.0, 4.4),
        (4.6, 4.5, -4.4),
        (4.6, 4.5, 0.0),
    ],
)
def test_invalid_negative_or_zero_yield_inputs_raise(
    config: TreasuryYieldConfig,
    current_yield_percent: float,
    sma_short_percent: float,
    sma_long_percent: float,
) -> None:
    with pytest.raises(ValueError):
        calculate_macro_adjustment(
            current_yield_percent,
            sma_short_percent,
            sma_long_percent,
            config,
        )


def test_invalid_negative_multiplier_inputs_raise() -> None:
    with pytest.raises(ValueError):
        calculate_total_adjustment_multiplier(-1.0, 0.0)

    with pytest.raises(ValueError):
        calculate_total_adjustment_multiplier(25.0, -100.0)


def test_negative_base_fair_value_raises() -> None:
    with pytest.raises(ValueError):
        adjust_fair_value(-0.01, 1.0)
