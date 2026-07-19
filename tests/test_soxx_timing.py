from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from src.analysis.soxx_timing import (
    SIGNAL_COLOR_KEYS,
    SoxxCrossDirection,
    SoxxTimingConfiguration,
    SoxxTimingSignal,
    SoxxTimingStatus,
    calculate_soxx_timing,
)
from src.config.soxx_timing import load_soxx_timing_configuration, parse_soxx_timing_configuration
from src.reports.soxx_timing_report import soxx_timing_csv, soxx_timing_json
from src.services import soxx_timing as soxx_service
from src.yahoo.prices import HistoricalPriceRow, HistoricalPriceSeries


def series(values: list[float]) -> HistoricalPriceSeries:
    start = date(2026, 1, 1)
    return HistoricalPriceSeries(
        "SOXX",
        tuple(
            HistoricalPriceRow(start + timedelta(days=index), close=value, adjusted_close=None)
            for index, value in enumerate(values)
        ),
    )


def pattern(a: int, b: int, c: int, d: int, e: int) -> list[float]:
    return [100.0] * 40 + [float(a)] * 5 + [float(b)] * 5 + [float(c)] * 4 + [float(d)] * 5 + [float(e)]


def result(values: list[float]):
    return calculate_soxx_timing(series(values), SoxxTimingConfiguration())


def test_repository_config_loads() -> None:
    config = load_soxx_timing_configuration("config/soxx_timing.yaml")

    assert config.symbol == "SOXX"
    assert config.fast_period == 5
    assert config.initial_period == 10
    assert config.strong_period == 15
    assert config.very_strong_period == 20
    assert config.long_period == 50


def test_invalid_config_rejects_non_soxx_symbol() -> None:
    with pytest.raises(ValueError):
        parse_soxx_timing_configuration({"symbol": "QQQ"})


def test_moving_average_calculations() -> None:
    timing = result([float(value) for value in range(1, 61)])

    assert timing.ma5 == pytest.approx(58.0)
    assert timing.ma10 == pytest.approx(55.5)
    assert timing.ma15 == pytest.approx(53.0)
    assert timing.ma20 == pytest.approx(50.5)
    assert timing.ma50 == pytest.approx(35.5)


def test_no_signal_before_sufficient_history() -> None:
    timing = result([100.0] * 59)

    assert timing.status == SoxxTimingStatus.INSUFFICIENT_DATA
    assert timing.primary_signal == SoxxTimingSignal.INSUFFICIENT_DATA


@pytest.mark.parametrize(
    ("values", "signal", "cross_name"),
    [
        (pattern(70, 70, 80, 75, 100), SoxxTimingSignal.BUY, "ma5_ma10_cross"),
        (pattern(70, 70, 95, 80, 90), SoxxTimingSignal.STRONG_BUY, "ma5_ma15_cross"),
        (pattern(70, 70, 75, 70, 80), SoxxTimingSignal.VERY_STRONG_BUY, "ma5_ma20_cross"),
        (pattern(70, 70, 75, 75, 70), SoxxTimingSignal.SELL, "ma5_ma10_cross"),
        (pattern(70, 70, 80, 75, 70), SoxxTimingSignal.STRONG_SELL, "ma5_ma15_cross"),
        (pattern(70, 70, 100, 80, 70), SoxxTimingSignal.VERY_STRONG_SELL, "ma5_ma20_cross"),
    ],
)
def test_graded_cross_signals(values: list[float], signal: SoxxTimingSignal, cross_name: str) -> None:
    timing = result(values)

    assert timing.primary_signal == signal
    assert getattr(timing, cross_name).direction in {
        SoxxCrossDirection.CROSS_ABOVE,
        SoxxCrossDirection.CROSS_BELOW,
    }


def test_multiple_bullish_crosses_choose_strongest_and_preserve_conditions() -> None:
    timing = result(pattern(70, 70, 70, 70, 75))

    assert timing.primary_signal == SoxxTimingSignal.VERY_STRONG_BUY
    assert SoxxTimingSignal.BUY in timing.active_conditions
    assert SoxxTimingSignal.STRONG_BUY in timing.active_conditions
    assert SoxxTimingSignal.VERY_STRONG_BUY in timing.active_conditions


def test_multiple_bearish_crosses_choose_strongest_and_preserve_conditions() -> None:
    timing = result(pattern(75, 80, 80, 80, 70))

    assert timing.primary_signal == SoxxTimingSignal.VERY_STRONG_SELL
    assert SoxxTimingSignal.SELL in timing.active_conditions
    assert SoxxTimingSignal.STRONG_SELL in timing.active_conditions
    assert SoxxTimingSignal.VERY_STRONG_SELL in timing.active_conditions


def test_persistent_position_does_not_repeat_cross_signal() -> None:
    values = pattern(70, 70, 70, 70, 75) + [75.0]
    timing = result(values)

    assert timing.primary_signal in {SoxxTimingSignal.SELL_CAUTION, SoxxTimingSignal.NEUTRAL}
    assert sum(1 for event in timing.events if event.signal == SoxxTimingSignal.VERY_STRONG_BUY) == 1


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
    timing = result(pattern(70, 70, 70, 70, 75))

    csv_text = soxx_timing_csv(timing)
    json_payload = json.loads(soxx_timing_json(timing))

    assert "primary_signal" in csv_text
    assert "VERY_STRONG_BUY" in csv_text
    assert json_payload["symbol"] == "SOXX"
    assert json_payload["signal"]["primary"] == "VERY_STRONG_BUY"


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
