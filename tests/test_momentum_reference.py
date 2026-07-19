from datetime import date, datetime, timedelta, timezone

import pytest

from src.analysis.momentum_reference import (
    MomentumReferenceStatus,
    RsiCrossDirection,
    calculate_rsi_momentum_reference,
    calculate_wilder_rsi,
)
from src.config.momentum_reference import MomentumReferenceConfiguration
from src.yahoo.prices import HistoricalPriceRow, HistoricalPriceSeries


GENERATED_AT = datetime(2026, 7, 18, tzinfo=timezone.utc)


def config(**overrides):
    values = {
        "enabled": True,
        "rsi_period": 14,
        "neutral_level": 50.0,
        "history_period": "1y",
        "history_interval": "1d",
        "minimum_observations": 30,
        "fallback_to_nearest": True,
        "prefer_adjusted_close": True,
    }
    values.update(overrides)
    return MomentumReferenceConfiguration(**values)


def rows(values, adjusted=True):
    start = date(2026, 1, 1)
    return tuple(
        HistoricalPriceRow(
            start + timedelta(days=index),
            close=float(value) if value is not None else None,
            adjusted_close=float(value) if adjusted and value is not None else None,
        )
        for index, value in enumerate(values)
    )


def series(values, adjusted=True):
    return HistoricalPriceSeries("MU", rows(values, adjusted))


def test_wilder_rsi_flat_prices_are_neutral() -> None:
    points = calculate_wilder_rsi(rows([100.0] * 31), 14)

    assert points
    assert all(point.rsi == 50.0 for point in points)


def test_monotonic_prices_have_extreme_rsi_without_crossing() -> None:
    rising = calculate_rsi_momentum_reference(
        series([100 + index for index in range(40)]),
        config(),
        GENERATED_AT,
    )
    falling = calculate_rsi_momentum_reference(
        series([100 - index for index in range(40)]),
        config(),
        GENERATED_AT,
    )

    assert rising.status == MomentumReferenceStatus.FALLBACK
    assert rising.current_rsi == 100.0
    assert rising.cross_direction == RsiCrossDirection.NEAREST_TO_50
    assert falling.current_rsi == 0.0


def test_detects_latest_cross_above() -> None:
    prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86]
    prices += [88, 90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 112, 114, 116]

    result = calculate_rsi_momentum_reference(series(prices), config(), GENERATED_AT)

    assert result.status == MomentumReferenceStatus.COMPLETE
    assert result.cross_direction == RsiCrossDirection.CROSS_ABOVE
    assert result.reference_date is not None
    assert result.reference_price is not None
    assert result.current_rsi is not None
    assert result.price_change_since_reference_pct is not None


def test_detects_latest_cross_below() -> None:
    prices = [100 + index for index in range(18)] + [116, 114, 112, 110, 108, 106, 104, 102, 100, 98, 96, 94]

    result = calculate_rsi_momentum_reference(series(prices), config(), GENERATED_AT)

    assert result.status == MomentumReferenceStatus.COMPLETE
    assert result.cross_direction == RsiCrossDirection.CROSS_BELOW


def test_insufficient_history_is_not_crashing() -> None:
    result = calculate_rsi_momentum_reference(series([100.0] * 10), config(), GENERATED_AT)

    assert result.status == MomentumReferenceStatus.INSUFFICIENT_DATA
    assert result.cross_direction == RsiCrossDirection.NOT_AVAILABLE


def test_falls_back_to_close_when_adjusted_close_unavailable() -> None:
    result = calculate_rsi_momentum_reference(
        series([100 + index for index in range(40)], adjusted=False),
        config(),
        GENERATED_AT,
    )

    assert result.price_field.value == "CLOSE"
    assert "Close was used" in result.warnings[0]


def test_ignores_missing_prices_and_sorts_rows() -> None:
    raw_rows = list(rows([100 + index for index in range(35)]))
    raw_rows.append(HistoricalPriceRow(date(2025, 1, 1), None, None))
    reversed_series = HistoricalPriceSeries("MU", tuple(reversed(raw_rows)))

    result = calculate_rsi_momentum_reference(reversed_series, config(), GENERATED_AT)

    assert result.observation_count == 35
    assert result.lookback_start == date(2026, 1, 1)
