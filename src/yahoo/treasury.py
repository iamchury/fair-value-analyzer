from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isnan, isfinite
from time import sleep
from typing import Any

import yfinance as yf


class TreasuryDataStatus(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    CONFIG_FALLBACK = "CONFIG_FALLBACK"
    STALE_FALLBACK = "STALE_FALLBACK"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class TreasuryHistoryConfig:
    symbol: str
    value_scale: str
    short_window_observations: int
    long_window_observations: int
    fallback_yield_percent: float | None = 4.30
    max_cached_age_hours: int = 24
    allow_config_fallback: bool = True
    allow_neutral_fallback: bool = True
    fail_analysis_on_download_error: bool = False


@dataclass(frozen=True)
class TreasuryYieldSnapshot:
    symbol: str
    yield_date: str
    current_yield_percent: float
    sma_short_percent: float
    sma_long_percent: float
    observation_count: int
    data_status: TreasuryDataStatus = TreasuryDataStatus.LIVE
    warnings: tuple[str, ...] = ()
    used_fallback: bool = False
    fetched_at: datetime | None = None


def validate_history_config(config: TreasuryHistoryConfig) -> None:
    """Validate settings used to build a Treasury yield snapshot."""
    if not config.symbol or not config.symbol.strip():
        raise ValueError("symbol is required.")
    _normalize_scale(config.value_scale)
    _validate_window("short_window_observations", config.short_window_observations)
    _validate_window("long_window_observations", config.long_window_observations)
    if config.fallback_yield_percent is not None:
        _validate_yield_percent("fallback_yield_percent", config.fallback_yield_percent)
    if isinstance(config.max_cached_age_hours, bool) or not isinstance(config.max_cached_age_hours, int):
        raise ValueError("max_cached_age_hours must be an integer.")
    if config.max_cached_age_hours < 0:
        raise ValueError("max_cached_age_hours must be greater than or equal to 0.")
    for name in (
        "allow_config_fallback",
        "allow_neutral_fallback",
        "fail_analysis_on_download_error",
    ):
        if not isinstance(getattr(config, name), bool):
            raise ValueError(f"{name} must be a boolean.")
    if config.long_window_observations <= config.short_window_observations:
        raise ValueError(
            "long_window_observations must be greater than "
            "short_window_observations."
        )


def normalize_yield_value(raw_value: float, value_scale: str) -> float:
    """Normalize a raw yield value to a percentage such as 4.6."""
    scale = _normalize_scale(value_scale)
    value = _coerce_float("raw_value", raw_value)

    if scale == "decimal":
        value *= 100

    if value <= 0:
        raise ValueError("yield_percent must be greater than 0.")
    if value > 20:
        raise ValueError("yield_percent must be less than or equal to 20.")
    return value


def extract_valid_close_values(history_dataframe: Any) -> list[float]:
    """Extract non-missing raw Close values from a history dataframe-like object."""
    try:
        close_values = history_dataframe["Close"]
    except Exception as error:
        raise ValueError("history dataframe must contain a Close column.") from error

    values = []
    for raw_value in close_values:
        if _is_missing(raw_value):
            continue
        value = _coerce_float("Close", raw_value)
        if value <= 0:
            raise ValueError("Close values must be greater than 0.")
        if value > 20:
            raise ValueError("Close values must be less than or equal to 20.")
        values.append(value)
    return values


def calculate_treasury_snapshot(
    symbol: str,
    dates: list[str],
    raw_close_values: list[float],
    config: TreasuryHistoryConfig,
) -> TreasuryYieldSnapshot:
    """Calculate current Treasury yield and SMAs from raw Close observations."""
    validate_history_config(config)
    if len(dates) != len(raw_close_values):
        raise ValueError("dates and raw_close_values must have the same length.")

    valid_dates: list[str] = []
    valid_yields: list[float] = []
    for raw_date, raw_close in zip(dates, raw_close_values):
        if _is_missing(raw_close):
            continue
        valid_dates.append(_format_date(raw_date))
        valid_yields.append(normalize_yield_value(raw_close, config.value_scale))

    observation_count = len(valid_yields)
    if observation_count < config.long_window_observations:
        raise ValueError(
            "at least long_window_observations valid observations are required."
        )

    short_values = valid_yields[-config.short_window_observations :]
    long_values = valid_yields[-config.long_window_observations :]

    return TreasuryYieldSnapshot(
        symbol=symbol,
        yield_date=valid_dates[-1],
        current_yield_percent=valid_yields[-1],
        sma_short_percent=sum(short_values) / len(short_values),
        sma_long_percent=sum(long_values) / len(long_values),
        observation_count=observation_count,
    )


def download_treasury_yield_snapshot(
    config: TreasuryHistoryConfig,
    period: str = "1y",
    attempts: int = 2,
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Download Treasury yield history from Yahoo and return a yield snapshot."""
    validate_history_config(config)
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ValueError("attempts must be an integer.")
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3.")

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            history = yf.Ticker(config.symbol).history(
                period=period,
                auto_adjust=False,
                repair=True,
                timeout=timeout_seconds,
            )
            break
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                sleep(0.25 * (2**attempt))
    else:
        raise RuntimeError(
            f"{config.symbol}: failed to download Treasury yield history."
        ) from last_error

    if history.empty:
        raise RuntimeError(f"{config.symbol}: no Treasury yield history returned.")

    dates = [_format_date(value) for value in history.index]
    try:
        raw_close_values = list(history["Close"])
    except Exception as error:
        raise RuntimeError(f"{config.symbol}: Treasury yield history is missing Close.") from error
    snapshot = calculate_treasury_snapshot(
        config.symbol,
        dates,
        raw_close_values,
        config,
    )
    return TreasuryYieldSnapshot(
        **{
            **snapshot.__dict__,
            "data_status": TreasuryDataStatus.LIVE,
            "warnings": (),
            "used_fallback": False,
            "fetched_at": _utc_now(),
        }
    )


def configured_fallback_treasury_snapshot(
    config: TreasuryHistoryConfig,
    reason: str,
    now: datetime | None = None,
) -> TreasuryYieldSnapshot:
    validate_history_config(config)
    if config.fallback_yield_percent is None or not config.allow_config_fallback:
        raise RuntimeError("configured Treasury fallback is not available.")
    timestamp = _utc_now() if now is None else now
    warning = (
        f"Treasury yield download failed. Using configured fallback yield of "
        f"{config.fallback_yield_percent:.2f}%."
    )
    return TreasuryYieldSnapshot(
        symbol=config.symbol,
        yield_date=_format_date(timestamp),
        current_yield_percent=float(config.fallback_yield_percent),
        sma_short_percent=float(config.fallback_yield_percent),
        sma_long_percent=float(config.fallback_yield_percent),
        observation_count=0,
        data_status=TreasuryDataStatus.CONFIG_FALLBACK,
        warnings=(warning, reason),
        used_fallback=True,
        fetched_at=timestamp,
    )


def unavailable_treasury_snapshot(
    config: TreasuryHistoryConfig,
    neutral_yield_percent: float,
    reason: str,
    now: datetime | None = None,
) -> TreasuryYieldSnapshot:
    validate_history_config(config)
    _validate_yield_percent("neutral_yield_percent", neutral_yield_percent)
    if not config.allow_neutral_fallback:
        raise RuntimeError("neutral Treasury fallback is disabled.")
    timestamp = _utc_now() if now is None else now
    return TreasuryYieldSnapshot(
        symbol=config.symbol,
        yield_date=_format_date(timestamp),
        current_yield_percent=float(neutral_yield_percent),
        sma_short_percent=float(neutral_yield_percent),
        sma_long_percent=float(neutral_yield_percent),
        observation_count=0,
        data_status=TreasuryDataStatus.UNAVAILABLE,
        warnings=(
            "Treasury yield unavailable. Macro adjustment was applied neutrally.",
            reason,
        ),
        used_fallback=True,
        fetched_at=timestamp,
    )


def _normalize_scale(value_scale: str) -> str:
    scale = str(value_scale).strip().lower()
    if scale not in {"percent", "decimal"}:
        raise ValueError("value_scale must be 'percent' or 'decimal'.")
    return scale


def _validate_window(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def _coerce_float(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric.") from error
    if not isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


def _validate_yield_percent(name: str, value: float) -> None:
    number = _coerce_float(name, value)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0.")
    if number > 20:
        raise ValueError(f"{name} must be less than or equal to 20.")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def _format_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if not text:
        raise ValueError("date values must not be empty.")

    try:
        return datetime.fromisoformat(text[:10]).strftime("%Y-%m-%d")
    except ValueError:
        return text[:10]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
