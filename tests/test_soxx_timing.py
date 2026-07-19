from __future__ import annotations

from datetime import date, timedelta
import json

import pandas as pd
import pytest

from src.analysis.soxx_timing import (
    EMA50Trend,
    EMA50TurnEvent,
    SIGNAL_COLOR_KEYS,
    SoxxCrossDirection,
    SoxxMovingAverageCross,
    SoxxTimingConfiguration,
    SoxxTimingEvent,
    SoxxTimingSignal,
    SoxxTimingStatus,
    detect_cross,
    detect_ma_cross,
    soxx_event_invariant_errors,
    calculate_soxx_timing,
)
from src.analysis import soxx_timing as soxx_analysis
from src.config.soxx_timing import load_soxx_timing_configuration, parse_soxx_timing_configuration
from src.reports.soxx_timing_report import format_soxx_timing_report, soxx_timing_csv, soxx_timing_json
from src.services import soxx_timing as soxx_service
from src.yahoo.prices import HistoricalPriceRow, HistoricalPriceSeries


def series(values: list[float]) -> HistoricalPriceSeries:
    start = date(2026, 1, 1)
    return series_from_date(values, start)


def series_from_date(values: list[float], start: date) -> HistoricalPriceSeries:
    return HistoricalPriceSeries(
        "SOXX",
        tuple(
            HistoricalPriceRow(start + timedelta(days=index), close=value, adjusted_close=None)
            for index, value in enumerate(values)
        ),
    )


def pattern(a: int, b: int, c: int, d: int, e: int) -> list[float]:
    return [100.0] * 60 + [float(a)] * 8 + [float(b)] * 8 + [float(c)] * 8 + [float(d)] * 8 + [float(e)]


def result(values: list[float]):
    return calculate_soxx_timing(series(values), SoxxTimingConfiguration())


def cross(direction: SoxxCrossDirection, slow: int) -> SoxxMovingAverageCross:
    previous_fast = 9.0 if direction == SoxxCrossDirection.CROSS_ABOVE else 11.0
    current_fast = 11.0 if direction == SoxxCrossDirection.CROSS_ABOVE else 9.0
    return SoxxMovingAverageCross(5, slow, direction, date(2026, 1, 1), previous_fast, 10.0, current_fast, 10.0)


def no_cross(slow: int) -> SoxxMovingAverageCross:
    return SoxxMovingAverageCross(5, slow, SoxxCrossDirection.NONE, None, 9.0, 10.0, 9.0, 10.0)


def graded_events(timing):
    graded = {
        SoxxTimingSignal.BUY,
        SoxxTimingSignal.STRONG_BUY,
        SoxxTimingSignal.VERY_STRONG_BUY,
        SoxxTimingSignal.SELL,
        SoxxTimingSignal.STRONG_SELL,
        SoxxTimingSignal.VERY_STRONG_SELL,
    }
    return [event for event in timing.events if event.signal in graded]


def test_repository_config_loads() -> None:
    config = load_soxx_timing_configuration("config/soxx_timing.yaml")

    assert config.symbol == "SOXX"
    assert config.moving_average_type == "EMA"
    assert config.exponential_adjust is False
    assert config.fast_period == 5
    assert config.initial_period == 10
    assert config.strong_period == 15
    assert config.very_strong_period == 20
    assert config.long_period == 50
    assert config.chart_trading_days == 100
    assert config.buy_filter_require_below_ema50 is True
    assert config.ema50_turn_enabled is True
    assert config.ema50_slope_tolerance == pytest.approx(1.0e-8)
    assert config.ema50_bridge_flat_periods is True
    assert config.show_ema50_turn_markers is True


def test_invalid_config_rejects_non_soxx_symbol() -> None:
    with pytest.raises(ValueError):
        parse_soxx_timing_configuration({"symbol": "QQQ"})


def test_invalid_config_rejects_unsupported_moving_average_method() -> None:
    with pytest.raises(ValueError, match="moving_average_type must be EMA"):
        parse_soxx_timing_configuration({"moving_averages": {"method": "SMA"}})


def test_invalid_config_rejects_ema_adjust_true() -> None:
    with pytest.raises(ValueError, match="exponential_adjust must be false"):
        parse_soxx_timing_configuration({"moving_averages": {"exponential": {"adjust": True}}})


def test_invalid_config_rejects_bad_ema50_turn_values() -> None:
    with pytest.raises(ValueError, match="ema50_slope_tolerance must be non-negative"):
        parse_soxx_timing_configuration({"ema50_turn": {"slope_tolerance": -0.1}})

    with pytest.raises(ValueError, match="buy_filter.require_below_ema50 must be a boolean"):
        parse_soxx_timing_configuration({"buy_filter": {"require_below_ema50": "yes"}})


def test_moving_average_calculations() -> None:
    values = [float(value) for value in range(1, 61)]
    timing = result(values)
    prices = pd.Series(values, dtype="float64")

    assert timing.moving_average_type == "EMA"
    assert timing.exponential_adjust is False
    assert timing.ma5 == pytest.approx(prices.ewm(span=5, adjust=False, min_periods=5).mean().iloc[-1])
    assert timing.ma10 == pytest.approx(prices.ewm(span=10, adjust=False, min_periods=10).mean().iloc[-1])
    assert timing.ma15 == pytest.approx(prices.ewm(span=15, adjust=False, min_periods=15).mean().iloc[-1])
    assert timing.ma20 == pytest.approx(prices.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1])
    assert timing.ma50 == pytest.approx(prices.ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1])
    assert timing.ema50_slope == pytest.approx(timing.daily_points[-1].ma50 - timing.daily_points[-2].ma50)
    assert timing.ema50_trend == EMA50Trend.RISING


def test_no_signal_before_sufficient_history() -> None:
    timing = result([100.0] * 59)

    assert timing.status == SoxxTimingStatus.INSUFFICIENT_DATA
    assert timing.primary_signal == SoxxTimingSignal.INSUFFICIENT_DATA


@pytest.mark.parametrize(
    ("values", "signal", "cross_name"),
    [
        (pattern(60, 60, 70, 60, 70), SoxxTimingSignal.BUY, "ma5_ma10_cross"),
        (pattern(60, 60, 80, 60, 80), SoxxTimingSignal.STRONG_BUY, "ma5_ma15_cross"),
        (pattern(60, 60, 60, 60, 70), SoxxTimingSignal.VERY_STRONG_BUY, "ma5_ma20_cross"),
        (pattern(60, 60, 60, 80, 60), SoxxTimingSignal.SELL, "ma5_ma10_cross"),
        (pattern(60, 60, 70, 90, 60), SoxxTimingSignal.STRONG_SELL, "ma5_ma15_cross"),
        (pattern(60, 60, 60, 70, 60), SoxxTimingSignal.VERY_STRONG_SELL, "ma5_ma20_cross"),
    ],
)
def test_graded_cross_signals(values: list[float], signal: SoxxTimingSignal, cross_name: str) -> None:
    timing = result(values)

    assert timing.primary_signal == signal
    assert getattr(timing, cross_name).direction in {
        SoxxCrossDirection.CROSS_ABOVE,
        SoxxCrossDirection.CROSS_BELOW,
    }


@pytest.mark.parametrize(
    ("previous_fast", "previous_slow", "current_fast", "current_slow", "direction"),
    [
        (10.0, 10.0, 10.1, 10.0, SoxxCrossDirection.CROSS_ABOVE),
        (9.9, 10.0, 10.1, 10.0, SoxxCrossDirection.CROSS_ABOVE),
        (10.0, 10.0, 9.9, 10.0, SoxxCrossDirection.CROSS_BELOW),
        (10.1, 10.0, 9.9, 10.0, SoxxCrossDirection.CROSS_BELOW),
        (10.1, 10.0, 10.2, 10.0, SoxxCrossDirection.NONE),
        (9.9, 10.0, 9.8, 10.0, SoxxCrossDirection.NONE),
    ],
)
def test_detect_ma_cross_boundaries(
    previous_fast: float,
    previous_slow: float,
    current_fast: float,
    current_slow: float,
    direction: SoxxCrossDirection,
) -> None:
    assert detect_ma_cross(previous_fast, previous_slow, current_fast, current_slow) == direction


def test_detect_cross_unavailable_for_missing_or_nonfinite_values() -> None:
    assert detect_cross(None, 10.0, 11.0, 10.0) == SoxxCrossDirection.UNAVAILABLE
    assert detect_cross(10.0, 10.0, float("nan"), 10.0) == SoxxCrossDirection.UNAVAILABLE


def test_observed_2026_06_10_values_cannot_emit_strong_or_very_strong_sell() -> None:
    previous_ma5 = 570.0
    current_ma5 = 560.0
    current_ma10 = 563.0
    current_ma15 = 557.0
    current_ma20 = 547.0

    assert detect_cross(previous_ma5, 562.0, current_ma5, current_ma10) == SoxxCrossDirection.CROSS_BELOW
    assert detect_cross(previous_ma5, 556.0, current_ma5, current_ma15) == SoxxCrossDirection.NONE
    assert detect_cross(previous_ma5, 546.0, current_ma5, current_ma20) == SoxxCrossDirection.NONE


@pytest.mark.parametrize(
    ("target_period", "forbidden_signal"),
    [
        (10, SoxxTimingSignal.SELL),
        (15, SoxxTimingSignal.STRONG_SELL),
        (20, SoxxTimingSignal.VERY_STRONG_SELL),
        (10, SoxxTimingSignal.BUY),
        (15, SoxxTimingSignal.STRONG_BUY),
        (20, SoxxTimingSignal.VERY_STRONG_BUY),
    ],
)
def test_price_position_without_ma5_cross_does_not_create_graded_signal(
    target_period: int,
    forbidden_signal: SoxxTimingSignal,
) -> None:
    active, primary = soxx_analysis._signals(
        {
            10: no_cross(10),
            15: no_cross(15),
            20: no_cross(20),
        },
        {5: 9.0, 10: 10.0, 15: 10.0, 20: 10.0, 50: 11.0, target_period: 10.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert forbidden_signal not in active
    assert primary == SoxxTimingSignal.NEUTRAL


@pytest.mark.parametrize(
    ("target_period", "direction", "expected_signal"),
    [
        (10, SoxxCrossDirection.CROSS_BELOW, SoxxTimingSignal.SELL),
        (15, SoxxCrossDirection.CROSS_BELOW, SoxxTimingSignal.STRONG_SELL),
        (20, SoxxCrossDirection.CROSS_BELOW, SoxxTimingSignal.VERY_STRONG_SELL),
        (10, SoxxCrossDirection.CROSS_ABOVE, SoxxTimingSignal.BUY),
        (15, SoxxCrossDirection.CROSS_ABOVE, SoxxTimingSignal.STRONG_BUY),
        (20, SoxxCrossDirection.CROSS_ABOVE, SoxxTimingSignal.VERY_STRONG_BUY),
    ],
)
def test_only_ma5_crosses_create_graded_signals(
    target_period: int,
    direction: SoxxCrossDirection,
    expected_signal: SoxxTimingSignal,
) -> None:
    crosses = {10: no_cross(10), 15: no_cross(15), 20: no_cross(20)}
    crosses[target_period] = cross(direction, target_period)

    active, primary = soxx_analysis._signals(
        crosses,
        {5: 9.0, 10: 10.0, 15: 10.0, 20: 10.0, 50: 11.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert expected_signal in active
    assert primary == expected_signal


@pytest.mark.parametrize(
    ("target_period", "expected_signal"),
    [
        (10, SoxxTimingSignal.BUY),
        (15, SoxxTimingSignal.STRONG_BUY),
        (20, SoxxTimingSignal.VERY_STRONG_BUY),
    ],
)
def test_bullish_cross_below_ema50_creates_buy_signal(target_period: int, expected_signal: SoxxTimingSignal) -> None:
    crosses = {10: no_cross(10), 15: no_cross(15), 20: no_cross(20)}
    crosses[target_period] = cross(SoxxCrossDirection.CROSS_ABOVE, target_period)

    active, primary = soxx_analysis._signals(
        crosses,
        {5: 11.0, 10: 10.0, 15: 10.0, 20: 10.0, 50: 12.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert expected_signal in active
    assert primary == expected_signal


@pytest.mark.parametrize(
    ("target_period", "filtered_signal"),
    [
        (10, SoxxTimingSignal.BUY),
        (15, SoxxTimingSignal.STRONG_BUY),
        (20, SoxxTimingSignal.VERY_STRONG_BUY),
    ],
)
def test_bullish_cross_above_ema50_does_not_create_buy_signal(target_period: int, filtered_signal: SoxxTimingSignal) -> None:
    crosses = {10: no_cross(10), 15: no_cross(15), 20: no_cross(20)}
    crosses[target_period] = cross(SoxxCrossDirection.CROSS_ABOVE, target_period)

    active, primary = soxx_analysis._signals(
        crosses,
        {5: 11.0, 10: 10.0, 15: 10.0, 20: 10.0, 50: 9.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert filtered_signal not in active
    assert primary == SoxxTimingSignal.NEUTRAL


def test_2026_06_11_regression_bullish_cross_above_ema50_is_rejected() -> None:
    crosses = {10: cross(SoxxCrossDirection.CROSS_ABOVE, 10), 15: no_cross(15), 20: no_cross(20)}

    active, primary = soxx_analysis._signals(
        crosses,
        {5: 554.11, 10: 553.58, 15: 560.0, 20: 565.0, 50: 548.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert SoxxTimingSignal.BUY not in active
    assert primary == SoxxTimingSignal.NEUTRAL


def test_multiple_bullish_crosses_choose_strongest_and_preserve_conditions() -> None:
    timing = result(pattern(60, 60, 60, 60, 70))

    assert timing.primary_signal == SoxxTimingSignal.VERY_STRONG_BUY
    assert SoxxTimingSignal.BUY in timing.active_conditions
    assert SoxxTimingSignal.STRONG_BUY in timing.active_conditions
    assert SoxxTimingSignal.VERY_STRONG_BUY in timing.active_conditions


def test_multiple_bearish_crosses_choose_strongest_and_preserve_conditions() -> None:
    timing = result(pattern(40, 40, 40, 50, 40))

    assert timing.primary_signal == SoxxTimingSignal.VERY_STRONG_SELL
    assert SoxxTimingSignal.SELL in timing.active_conditions
    assert SoxxTimingSignal.STRONG_SELL in timing.active_conditions
    assert SoxxTimingSignal.VERY_STRONG_SELL in timing.active_conditions


def test_bearish_cross_behavior_is_unchanged_by_ema50_location() -> None:
    active, primary = soxx_analysis._signals(
        {10: cross(SoxxCrossDirection.CROSS_BELOW, 10), 15: no_cross(15), 20: no_cross(20)},
        {5: 9.0, 10: 10.0, 15: 10.0, 20: 10.0, 50: 100.0},
        None,
        False,
        SoxxTimingConfiguration(),
    )

    assert SoxxTimingSignal.SELL in active
    assert primary == SoxxTimingSignal.SELL


def test_persistent_position_does_not_repeat_cross_signal() -> None:
    values = pattern(60, 60, 60, 60, 70) + [70.0]
    timing = result(values)

    assert timing.primary_signal in {SoxxTimingSignal.SELL_CAUTION, SoxxTimingSignal.NEUTRAL}
    assert sum(1 for event in timing.events if event.signal == SoxxTimingSignal.VERY_STRONG_BUY) == 1


def test_persistent_ma5_below_ma15_produces_only_one_strong_sell_event() -> None:
    timing = result([100.0] * 35 + [90.0] * 15 + [80.0] * 12)

    assert sum(1 for event in timing.events if event.signal == SoxxTimingSignal.STRONG_SELL) <= 1


def test_second_sell_event_requires_intervening_recovery_cross() -> None:
    timing = result([100.0] * 40 + [80.0] * 10 + [110.0] * 10 + [80.0] * 10)
    bearish_events = [
        event
        for event in timing.events
        if event.signal in {
            SoxxTimingSignal.SELL,
            SoxxTimingSignal.STRONG_SELL,
            SoxxTimingSignal.VERY_STRONG_SELL,
        }
    ]
    bullish_events = [
        event
        for event in timing.events
        if event.signal in {
            SoxxTimingSignal.BUY,
            SoxxTimingSignal.STRONG_BUY,
            SoxxTimingSignal.VERY_STRONG_BUY,
        }
    ]

    assert len(bearish_events) >= 2
    assert any(bearish_events[0].date < event.date < bearish_events[-1].date for event in bullish_events)


def test_sell_caution_does_not_upgrade_to_strong_sell_without_ma5_cross() -> None:
    timing = calculate_soxx_timing(
        series_from_date([100.0] * 35 + [90.0] * 15 + [80.0] * 10, date(2026, 4, 12)),
        SoxxTimingConfiguration(signal_history_days=500),
    )
    latest = timing.daily_points[-1]

    assert latest.date == date(2026, 6, 10)
    assert latest.close < latest.ma20
    assert latest.primary_signal == SoxxTimingSignal.SELL_CAUTION
    assert latest.ma5_ma10_cross.direction == SoxxCrossDirection.NONE
    assert latest.ma5_ma15_cross.direction == SoxxCrossDirection.NONE
    assert latest.ma5_ma20_cross.direction == SoxxCrossDirection.NONE
    assert not any(event.date == date(2026, 6, 10) and event.signal in {
        SoxxTimingSignal.SELL,
        SoxxTimingSignal.STRONG_SELL,
        SoxxTimingSignal.VERY_STRONG_SELL,
    } for event in timing.events)


def test_event_date_equals_current_crossover_row_and_previous_is_adjacent_observation() -> None:
    timing = result(pattern(60, 60, 70, 90, 60))
    event = next(event for event in timing.events if event.signal == SoxxTimingSignal.STRONG_SELL)
    dates = [point.date for point in timing.daily_points]
    current_index = dates.index(event.current_date)

    assert event.date == event.current_date
    assert event.previous_date == dates[current_index - 1]


def test_descending_input_is_sorted_before_cross_generation() -> None:
    ascending = series([100.0] * 40 + [80.0] * 10 + [110.0] * 10)
    descending = HistoricalPriceSeries("SOXX", tuple(reversed(ascending.rows)))

    timing = calculate_soxx_timing(descending, SoxxTimingConfiguration(signal_history_days=500))

    assert timing.lookback_start < timing.lookback_end
    assert all(
        previous.date < current.date
        for previous, current in zip(timing.daily_points, timing.daily_points[1:])
    )
    assert all(event.previous_date is None or event.previous_date < event.current_date for event in timing.events)


def test_duplicate_dates_are_normalized_without_cross_misalignment() -> None:
    base = list(series([100.0] * 40 + [80.0] * 10 + [110.0] * 10).rows)
    duplicate = HistoricalPriceRow(base[-1].date, close=120.0, adjusted_close=None)
    timing = calculate_soxx_timing(
        HistoricalPriceSeries("SOXX", tuple(base + [duplicate])),
        SoxxTimingConfiguration(signal_history_days=500),
    )

    assert timing.daily_points[-1].date == duplicate.date
    assert timing.daily_points[-1].close == pytest.approx(120.0)
    assert len({point.date for point in timing.daily_points}) == len(timing.daily_points)


def test_event_values_match_daily_point_values_on_same_date() -> None:
    timing = result(pattern(70, 70, 80, 75, 70))
    points = {point.date: point for point in timing.daily_points}

    for event in graded_events(timing):
        point = points[event.current_date]
        assert event.current_ma5 == point.ma5
        assert event.current_target_ma == getattr(point, f"ma{event.crossed_average}")


def test_impossible_event_fails_invariant_validator() -> None:
    event = SoxxTimingEvent(
        date=date(2026, 6, 10),
        previous_date=date(2026, 6, 9),
        current_date=date(2026, 6, 10),
        close=541.0,
        ma5=560.0,
        ma10=563.0,
        ma15=557.0,
        ma20=547.0,
        ma50=550.0,
        prior_high=610.0,
        drawdown_pct=-11.0,
        crossed_average=15,
        fast_average=5,
        cross_direction=SoxxCrossDirection.CROSS_BELOW,
        previous_ma5=570.0,
        previous_target_ma=556.0,
        current_ma5=560.0,
        current_target_ma=557.0,
        signal=SoxxTimingSignal.STRONG_SELL,
        active_conditions=(SoxxTimingSignal.STRONG_SELL,),
        rationale=(),
    )

    assert soxx_event_invariant_errors(event)


def test_deep_drawdown_does_not_become_strong_buy_without_ma5_cross() -> None:
    active, primary = soxx_analysis._signals(
        {10: no_cross(10), 15: no_cross(15), 20: no_cross(20)},
        {5: 70.0, 10: 72.0, 15: 74.0, 20: 76.0, 50: 100.0},
        -30.0,
        False,
        SoxxTimingConfiguration(),
    )

    assert SoxxTimingSignal.STRONG_BUY not in active
    assert primary == SoxxTimingSignal.SELL_CAUTION


def test_event_table_identifies_crossed_ma_explicitly() -> None:
    timing = result(pattern(60, 60, 70, 90, 60))
    event = next(event for event in timing.events if event.signal == SoxxTimingSignal.STRONG_SELL)

    assert event.fast_average == 5
    assert event.crossed_average == 15
    assert event.cross_direction == SoxxCrossDirection.CROSS_BELOW
    assert event.previous_ma5 is not None
    assert event.previous_target_ma is not None
    assert event.current_ma5 is not None
    assert event.current_target_ma is not None


def test_cli_signal_history_identifies_cross_basis() -> None:
    timing = result(pattern(60, 60, 70, 90, 60))

    report = format_soxx_timing_report(timing, show_event_audit=True)

    assert "SIGNAL HISTORY" in report
    assert "SOXX EVENT AUDIT" in report
    assert "STRONG_SELL" in report
    assert "EMA5 crossed below EMA15" in report
    assert "Invariant Valid" in report


def test_every_historical_graded_signal_has_matching_ma5_cross_basis() -> None:
    timing = result([100.0] * 40 + [80.0] * 10 + [110.0] * 10 + [80.0] * 10 + [120.0] * 10)
    expected = {
        SoxxTimingSignal.BUY: (10, SoxxCrossDirection.CROSS_ABOVE),
        SoxxTimingSignal.STRONG_BUY: (15, SoxxCrossDirection.CROSS_ABOVE),
        SoxxTimingSignal.VERY_STRONG_BUY: (20, SoxxCrossDirection.CROSS_ABOVE),
        SoxxTimingSignal.SELL: (10, SoxxCrossDirection.CROSS_BELOW),
        SoxxTimingSignal.STRONG_SELL: (15, SoxxCrossDirection.CROSS_BELOW),
        SoxxTimingSignal.VERY_STRONG_SELL: (20, SoxxCrossDirection.CROSS_BELOW),
    }

    assert graded_events(timing)
    for event in graded_events(timing):
        crossed_average, direction = expected[event.signal]
        assert event.fast_average == 5
        assert event.crossed_average == crossed_average
        assert event.cross_direction == direction


def test_sell_caution_at_exactly_minus_10_and_not_at_minus_9_99() -> None:
    caution = result([100.0] * 55 + [90.0] * 5)
    no_caution = result([100.0] * 55 + [90.01] * 5)

    assert SoxxTimingSignal.SELL_CAUTION in caution.active_conditions
    assert SoxxTimingSignal.SELL_CAUTION not in no_caution.active_conditions


def test_prior_high_excludes_current_day_and_window() -> None:
    values = [100.0] * 59 + [120.0]
    timing = result(values)

    assert timing.prior_high_price == pytest.approx(100.0)
    assert timing.drawdown_pct == pytest.approx(20.0)


def test_deep_drawdown_recovery_condition_at_exactly_minus_30() -> None:
    timing = result([100.0] * 40 + [70.0] * 14 + [70.0] * 5 + [70.0])

    assert timing.drawdown_pct == pytest.approx(-30.0)


def test_convergence_threshold_and_cluster_context() -> None:
    timing = result([100.0] * 60)

    assert timing.short_ma_converged is True
    assert timing.short_ma_spread_pct == pytest.approx(0.0)


def test_color_keys_and_text_labels_cover_signals() -> None:
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.BUY] == "BUY_LIGHT_GREEN"
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.STRONG_BUY] == "BUY_MEDIUM_GREEN"
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.VERY_STRONG_BUY] == "BUY_DARK_GREEN"
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.SELL] == "SELL_LIGHT_RED"
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.STRONG_SELL] == "SELL_MEDIUM_RED"
    assert SIGNAL_COLOR_KEYS[SoxxTimingSignal.VERY_STRONG_SELL] == "SELL_DARK_RED"


def test_csv_and_json_serialization() -> None:
    timing = result(pattern(60, 60, 60, 60, 70))

    csv_text = soxx_timing_csv(timing)
    json_payload = json.loads(soxx_timing_json(timing))

    assert "primary_signal" in csv_text
    assert "VERY_STRONG_BUY" in csv_text
    assert json_payload["symbol"] == "SOXX"
    assert json_payload["signal"]["primary"] == "VERY_STRONG_BUY"
    assert json_payload["moving_averages"]["type"] == "EMA"
    assert json_payload["moving_averages"]["adjust"] is False
    assert json_payload["moving_averages"]["ema50_trend"] in {"RISING", "FALLING", "FLAT"}
    assert json_payload["events"]
    assert json_payload["events"][-1]["fast_average"] == 5
    assert json_payload["events"][-1]["crossed_average"] == 20


def test_ema50_slope_trends_and_turns() -> None:
    config = SoxxTimingConfiguration(ema50_slope_tolerance=1.0e-8)
    values = [None, 10.0, 11.0, 11.0, 10.0, 9.0, 9.0, 10.0]

    slopes, previous_slopes, trends, turns = soxx_analysis._ema50_trend_series(values, config)

    assert slopes[2] == pytest.approx(1.0)
    assert previous_slopes[3] == pytest.approx(1.0)
    assert trends[2] == EMA50Trend.RISING
    assert trends[4] == EMA50Trend.FALLING
    assert trends[6] == EMA50Trend.FLAT
    assert turns[4] == EMA50TurnEvent.TURN_DOWN
    assert turns[5] == EMA50TurnEvent.NONE
    assert turns[7] == EMA50TurnEvent.TURN_UP


def test_ema50_turn_events_do_not_change_trade_signal_or_sell_caution() -> None:
    timing = result([100.0] * 60 + [90.0] * 20 + [95.0] * 10 + [90.0] * 10)

    assert all(event.event in {EMA50TurnEvent.TURN_UP, EMA50TurnEvent.TURN_DOWN} for event in timing.ema50_turn_events)
    assert timing.primary_signal in {
        SoxxTimingSignal.NEUTRAL,
        SoxxTimingSignal.SELL_CAUTION,
        SoxxTimingSignal.SELL,
        SoxxTimingSignal.STRONG_SELL,
        SoxxTimingSignal.VERY_STRONG_SELL,
    }


def test_cli_exposes_ema50_trend_and_turn_history() -> None:
    timing = result([100.0] * 60 + [90.0] * 20 + [95.0] * 10 + [90.0] * 10)

    report = format_soxx_timing_report(timing)

    assert "EMA50 Trend" in report
    assert "EMA50 Daily Change" in report
    assert "EMA50 Turning Point" in report
    assert "EMA50 TURNING POINT HISTORY" in report


def test_service_downloads_soxx_history_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        soxx_service,
        "download_daily_price_history",
        lambda symbol, period, interval: calls.append((symbol, period, interval)) or series([100.0] * 60),
    )

    timing = soxx_service.analyze_soxx_timing(SoxxTimingConfiguration())

    assert timing.status == SoxxTimingStatus.COMPLETE
    assert calls == [("SOXX", "2y", "1d")]


def test_service_failure_returns_error_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        soxx_service,
        "download_daily_price_history",
        lambda symbol, period, interval: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    timing = soxx_service.analyze_soxx_timing(SoxxTimingConfiguration())

    assert timing.status == SoxxTimingStatus.ERROR
    assert timing.primary_signal == SoxxTimingSignal.ERROR
