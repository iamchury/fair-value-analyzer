from datetime import date, datetime
from math import inf, nan

import pytest

from src.yahoo import treasury
from src.yahoo.treasury import (
    TreasuryDataStatus,
    TreasuryHistoryConfig,
    TreasuryYieldSnapshot,
    calculate_treasury_snapshot,
    configured_fallback_treasury_snapshot,
    download_treasury_yield_snapshot,
    extract_valid_close_values,
    normalize_yield_value,
    unavailable_treasury_snapshot,
    validate_history_config,
)


@pytest.fixture
def config() -> TreasuryHistoryConfig:
    return TreasuryHistoryConfig(
        symbol="^TNX",
        value_scale="percent",
        short_window_observations=2,
        long_window_observations=5,
    )


class FakeHistory:
    def __init__(self, closes, index, empty=False):
        self._closes = closes
        self.index = index
        self.empty = empty

    def __getitem__(self, key):
        if key != "Close":
            raise KeyError(key)
        return self._closes


class FakeTicker:
    history_calls = []

    def __init__(self, symbol, history=None, error=None):
        self.symbol = symbol
        self._history = history
        self._error = error

    def history(self, **kwargs):
        self.history_calls.append((self.symbol, kwargs))
        if self._error:
            raise self._error
        return self._history


def test_percent_scale_normalization() -> None:
    assert normalize_yield_value(4.6, "percent") == 4.6


def test_decimal_scale_normalization() -> None:
    assert normalize_yield_value(0.046, "decimal") == pytest.approx(4.6)


def test_unknown_scale_raises() -> None:
    with pytest.raises(ValueError):
        normalize_yield_value(4.6, "basis_points")


@pytest.mark.parametrize("raw_value", [0.0, -1.0, nan, inf, -inf])
def test_invalid_raw_values_raise(raw_value: float) -> None:
    with pytest.raises(ValueError):
        normalize_yield_value(raw_value, "percent")


def test_over_20_normalized_value_raises() -> None:
    with pytest.raises(ValueError):
        normalize_yield_value(20.01, "percent")

    with pytest.raises(ValueError):
        normalize_yield_value(0.201, "decimal")


@pytest.mark.parametrize(
    "bad_config",
    [
        TreasuryHistoryConfig("", "percent", 2, 5),
        TreasuryHistoryConfig("^TNX", "unknown", 2, 5),
        TreasuryHistoryConfig("^TNX", "percent", 0, 5),
        TreasuryHistoryConfig("^TNX", "percent", 2, 2),
        TreasuryHistoryConfig("^TNX", "percent", 5, 2),
        TreasuryHistoryConfig("^TNX", "percent", True, 5),
    ],
)
def test_invalid_window_configuration_raises(
    bad_config: TreasuryHistoryConfig,
) -> None:
    with pytest.raises(ValueError):
        validate_history_config(bad_config)


def test_insufficient_observations_raise(config: TreasuryHistoryConfig) -> None:
    with pytest.raises(ValueError):
        calculate_treasury_snapshot(
            "^TNX",
            ["2024-01-01", "2024-01-02"],
            [4.1, 4.2],
            config,
        )


def test_missing_and_nan_close_values_are_ignored(
    config: TreasuryHistoryConfig,
) -> None:
    snapshot = calculate_treasury_snapshot(
        "^TNX",
        [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-06",
            "2024-01-07",
        ],
        [None, 4.1, nan, 4.2, 4.3, 4.4, 4.5],
        config,
    )

    assert snapshot.current_yield_percent == 4.5
    assert snapshot.yield_date == "2024-01-07"
    assert snapshot.observation_count == 5


@pytest.mark.parametrize("bad_close", [-1.0, 0.0, 21.0])
def test_invalid_finite_close_values_raise(
    config: TreasuryHistoryConfig,
    bad_close: float,
) -> None:
    with pytest.raises(ValueError):
        calculate_treasury_snapshot(
            "^TNX",
            [
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
            ],
            [4.1, 4.2, bad_close, 4.4, 4.5],
            config,
        )


def test_extract_valid_close_values_ignores_missing_and_nan() -> None:
    history = FakeHistory([None, 4.1, nan, 4.2], ["a", "b", "c", "d"])
    assert extract_valid_close_values(history) == [4.1, 4.2]


def test_deterministic_snapshot_example(config: TreasuryHistoryConfig) -> None:
    snapshot = calculate_treasury_snapshot(
        "^TNX",
        [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
        ],
        [4.1, 4.2, 4.3, 4.4, 4.5],
        config,
    )

    assert isinstance(snapshot, TreasuryYieldSnapshot)
    assert snapshot.symbol == "^TNX"
    assert snapshot.current_yield_percent == 4.5
    assert snapshot.sma_short_percent == pytest.approx(4.45)
    assert snapshot.sma_long_percent == pytest.approx(4.3)
    assert snapshot.yield_date == "2024-01-05"
    assert snapshot.observation_count == 5


def test_date_selection_supports_datetime_and_date(
    config: TreasuryHistoryConfig,
) -> None:
    snapshot = calculate_treasury_snapshot(
        "^TNX",
        [
            datetime(2024, 1, 1, 12, 30),
            date(2024, 1, 2),
            "2024-01-03 00:00:00",
            "2024-01-04",
            "2024-01-05",
        ],
        [4.1, 4.2, 4.3, 4.4, 4.5],
        config,
    )

    assert snapshot.yield_date == "2024-01-05"


def test_yahoo_history_call_arguments(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    history = FakeHistory(
        [4.1, 4.2, 4.3, 4.4, 4.5],
        ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    )
    FakeTicker.history_calls = []
    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, history=history),
    )

    snapshot = download_treasury_yield_snapshot(config, period="6mo")

    assert snapshot.current_yield_percent == 4.5
    assert FakeTicker.history_calls == [
        (
            "^TNX",
            {
                "period": "6mo",
                "auto_adjust": False,
                "repair": True,
                "timeout": 10,
            },
        )
    ]


def test_empty_yahoo_history_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, history=FakeHistory([], [], empty=True)),
    )

    with pytest.raises(RuntimeError, match=r"\^TNX"):
        download_treasury_yield_snapshot(config)


def test_yahoo_exception_raises_runtime_error_with_symbol(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, error=OSError("network down")),
    )

    with pytest.raises(RuntimeError, match=r"\^TNX"):
        download_treasury_yield_snapshot(config)


def test_download_retries_with_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    FakeTicker.history_calls = []
    monkeypatch.setattr(treasury, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, error=TimeoutError("timeout")),
    )

    with pytest.raises(RuntimeError, match="failed to download"):
        download_treasury_yield_snapshot(config, attempts=2, timeout_seconds=7)

    assert len(FakeTicker.history_calls) == 2
    assert FakeTicker.history_calls[0][1]["timeout"] == 7


def test_missing_close_column_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    class MissingCloseHistory:
        empty = False
        index = ["2024-01-01"]

        def __getitem__(self, key):
            raise KeyError(key)

    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, history=MissingCloseHistory()),
    )

    with pytest.raises(RuntimeError, match="missing Close"):
        download_treasury_yield_snapshot(config, attempts=1)


def test_non_finite_latest_download_value_raises(
    monkeypatch: pytest.MonkeyPatch,
    config: TreasuryHistoryConfig,
) -> None:
    history = FakeHistory(
        [4.1, 4.2, 4.3, 4.4, nan],
        ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    )
    monkeypatch.setattr(
        treasury.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, history=history),
    )

    with pytest.raises(ValueError, match="valid observations"):
        download_treasury_yield_snapshot(config, attempts=1)


def test_invalid_fallback_history_configuration_raises() -> None:
    bad = TreasuryHistoryConfig("^TNX", "percent", 2, 5, fallback_yield_percent=nan)

    with pytest.raises(ValueError, match="fallback_yield_percent"):
        validate_history_config(bad)


def test_configured_fallback_snapshot_records_status_and_warning(
    config: TreasuryHistoryConfig,
) -> None:
    snapshot = configured_fallback_treasury_snapshot(config, "network down")

    assert snapshot.data_status == TreasuryDataStatus.CONFIG_FALLBACK
    assert snapshot.current_yield_percent == pytest.approx(4.3)
    assert snapshot.sma_short_percent == pytest.approx(4.3)
    assert snapshot.sma_long_percent == pytest.approx(4.3)
    assert snapshot.used_fallback is True
    assert "configured fallback yield" in snapshot.warnings[0]


def test_unavailable_snapshot_records_neutral_status_and_warning(
    config: TreasuryHistoryConfig,
) -> None:
    config = TreasuryHistoryConfig(
        symbol=config.symbol,
        value_scale=config.value_scale,
        short_window_observations=config.short_window_observations,
        long_window_observations=config.long_window_observations,
        fallback_yield_percent=None,
        allow_config_fallback=False,
    )

    snapshot = unavailable_treasury_snapshot(config, 4.3, "missing")

    assert snapshot.data_status == TreasuryDataStatus.UNAVAILABLE
    assert snapshot.current_yield_percent == pytest.approx(4.3)
    assert snapshot.used_fallback is True
    assert "applied neutrally" in snapshot.warnings[0]
