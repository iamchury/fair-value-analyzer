import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from math import isnan, isfinite
from time import sleep
from typing import Any
from urllib.request import urlopen

import yfinance as yf


class TreasuryDataStatus(str, Enum):
    LIVE = "LIVE"
    PARTIAL_LIVE = "PARTIAL_LIVE"
    CACHED = "CACHED"
    CONFIG_FALLBACK = "CONFIG_FALLBACK"
    STALE_FALLBACK = "STALE_FALLBACK"
    UNAVAILABLE = "UNAVAILABLE"


class TreasuryDataSource(str, Enum):
    YAHOO_TNX = "YAHOO_TNX"
    FRED_DGS10 = "FRED_DGS10"
    US_TREASURY = "US_TREASURY"
    CACHE = "CACHE"
    CONFIG = "CONFIG"
    NONE = "NONE"


_PROVIDER_LABELS = {
    TreasuryDataSource.YAHOO_TNX: "Yahoo ^TNX",
    TreasuryDataSource.FRED_DGS10: "FRED DGS10",
    TreasuryDataSource.US_TREASURY: "U.S. Treasury",
    TreasuryDataSource.CACHE: "Cache",
    TreasuryDataSource.CONFIG: "Configured Fallback",
    TreasuryDataSource.NONE: "None",
}

_PROVIDER_NAMES = {
    "yahoo_tnx": TreasuryDataSource.YAHOO_TNX,
    "fred_dgs10": TreasuryDataSource.FRED_DGS10,
    "us_treasury": TreasuryDataSource.US_TREASURY,
}


@dataclass(frozen=True)
class TreasuryHistoryConfig:
    symbol: str
    value_scale: str
    short_window_observations: int
    long_window_observations: int
    providers: tuple[str, ...] = ("yahoo_tnx",)
    fred_series: str = "DGS10"
    max_live_business_days_old: int = 3
    fallback_yield_percent: float | None = 4.30
    max_cached_age_hours: int = 24
    allow_config_fallback: bool = True
    allow_neutral_fallback: bool = True
    fail_analysis_on_download_error: bool = False
    source_difference_warning_pct_points: float = 0.15


@dataclass(frozen=True)
class TreasuryYieldSnapshot:
    symbol: str
    yield_date: str
    current_yield_percent: float
    sma_short_percent: float
    sma_long_percent: float
    observation_count: int
    data_status: TreasuryDataStatus = TreasuryDataStatus.LIVE
    source: TreasuryDataSource = TreasuryDataSource.YAHOO_TNX
    source_name: str = "Yahoo ^TNX"
    warnings: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    provider_diagnostics: tuple[str, ...] = ()
    used_fallback: bool = False
    fetched_at: datetime | None = None
    yahoo_quote_yield: float | None = None
    yahoo_quote_field: str | None = None
    yahoo_short_history_yield: float | None = None
    yahoo_short_history_date: str | None = None
    yahoo_short_history_available: bool = False
    yahoo_full_history_available: bool = False
    source_difference_percentage_points: float | None = None


def validate_history_config(config: TreasuryHistoryConfig) -> None:
    """Validate settings used to build a Treasury yield snapshot."""
    if not config.symbol or not config.symbol.strip():
        raise ValueError("symbol is required.")
    _normalize_scale(config.value_scale)
    _validate_window("short_window_observations", config.short_window_observations)
    _validate_window("long_window_observations", config.long_window_observations)
    if config.long_window_observations <= config.short_window_observations:
        raise ValueError(
            "long_window_observations must be greater than "
            "short_window_observations."
        )
    _validate_providers(config.providers)
    if not config.fred_series or not config.fred_series.strip():
        raise ValueError("fred_series is required.")
    if isinstance(config.max_live_business_days_old, bool) or not isinstance(
        config.max_live_business_days_old,
        int,
    ):
        raise ValueError("max_live_business_days_old must be an integer.")
    if config.max_live_business_days_old < 0:
        raise ValueError("max_live_business_days_old must be greater than or equal to 0.")
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
    _validate_non_negative_percent(
        "source_difference_warning_pct_points",
        config.source_difference_warning_pct_points,
    )


def normalize_yield_value(raw_value: float, value_scale: str) -> float:
    """Normalize a raw yield value to a percentage such as 4.6."""
    scale = _normalize_scale(value_scale)
    value = _coerce_float("raw_value", raw_value)

    if scale == "decimal":
        value *= 100

    _validate_yield_percent("yield_percent", value)
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
    """Calculate current Treasury yield and SMAs from raw observations."""
    validate_history_config(config)
    return _snapshot_from_observations(
        symbol=symbol,
        dates=dates,
        raw_values=raw_close_values,
        config=config,
        source=TreasuryDataSource.YAHOO_TNX,
        status=TreasuryDataStatus.LIVE,
        fetched_at=None,
    )


def download_treasury_yield_snapshot(
    config: TreasuryHistoryConfig,
    period: str = "1y",
    attempts: int = 1,
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Download Yahoo ^TNX history and return a yield snapshot."""
    validate_history_config(config)
    _validate_attempts(attempts)

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
    snapshot = _snapshot_from_observations(
        symbol=config.symbol,
        dates=dates,
        raw_values=raw_close_values,
        config=config,
        source=TreasuryDataSource.YAHOO_TNX,
        status=TreasuryDataStatus.LIVE,
        fetched_at=_utc_now(),
    )
    return TreasuryYieldSnapshot(
        **{
            **snapshot.__dict__,
            "yahoo_full_history_available": True,
        }
    )


def download_treasury_yield_snapshot_with_ticker_history(
    config: TreasuryHistoryConfig,
    period: str = "1y",
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Try a bounded alternative Yahoo Ticker.history full-history request."""
    validate_history_config(config)
    ticker = yf.Ticker(config.symbol)
    try:
        history = ticker.history(
            period=period,
            interval="1d",
            auto_adjust=False,
            actions=False,
            timeout=timeout_seconds,
        )
    except Exception as error:
        raise RuntimeError(
            f"{config.symbol}: failed alternative Treasury yield history request."
        ) from error
    snapshot = _snapshot_from_yahoo_history(
        config=config,
        history=history,
        symbol=config.symbol,
        source=TreasuryDataSource.YAHOO_TNX,
        status=TreasuryDataStatus.LIVE,
    )
    return TreasuryYieldSnapshot(
        **{
            **snapshot.__dict__,
            "yahoo_full_history_available": True,
        }
    )


def probe_yahoo_treasury_diagnostics(
    config: TreasuryHistoryConfig,
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Probe Yahoo quote and short history for diagnostics only."""
    validate_history_config(config)
    ticker = yf.Ticker(config.symbol)
    quote_yield, quote_field = _probe_yahoo_quote(ticker)
    short_yield = None
    short_date = None
    short_available = False
    try:
        history = ticker.history(
            period="5d",
            interval="1d",
            auto_adjust=False,
            actions=False,
            timeout=timeout_seconds,
        )
        if history.empty:
            raise RuntimeError(f"{config.symbol}: no 5-day Treasury yield history returned.")
        dates = [_format_date(value) for value in history.index]
        raw_values = extract_valid_close_values(history)
        if not raw_values:
            raise ValueError("5-day Treasury yield history has no valid Close values.")
        short_yield = normalize_yield_value(raw_values[-1], config.value_scale)
        short_date = dates[-1]
        short_available = True
    except (RuntimeError, ValueError, OSError, KeyError):
        short_available = False

    return TreasuryYieldSnapshot(
        symbol=config.symbol,
        yield_date=short_date or _format_date(_utc_now()),
        current_yield_percent=_diagnostic_yield(config, short_yield, quote_yield),
        sma_short_percent=_diagnostic_yield(config, short_yield, quote_yield),
        sma_long_percent=_diagnostic_yield(config, short_yield, quote_yield),
        observation_count=0,
        data_status=TreasuryDataStatus.PARTIAL_LIVE,
        source=TreasuryDataSource.YAHOO_TNX,
        source_name=_PROVIDER_LABELS[TreasuryDataSource.YAHOO_TNX],
        yahoo_quote_yield=quote_yield,
        yahoo_quote_field=quote_field,
        yahoo_short_history_yield=short_yield,
        yahoo_short_history_date=short_date,
        yahoo_short_history_available=short_available,
        yahoo_full_history_available=False,
        fetched_at=_utc_now(),
    )


def resolve_live_treasury_yield_snapshot(
    config: TreasuryHistoryConfig,
    now: datetime | None = None,
) -> TreasuryYieldSnapshot:
    """Resolve the first valid live Treasury source in configured priority order."""
    validate_history_config(config)
    timestamp = _utc_now() if now is None else now
    diagnostics: list[str] = []
    yahoo_failed = False
    yahoo_probe: TreasuryYieldSnapshot | None = None

    for source in (_PROVIDER_NAMES[name] for name in config.providers):
        try:
            if source == TreasuryDataSource.YAHOO_TNX:
                try:
                    snapshot = download_treasury_yield_snapshot(config)
                except (RuntimeError, ValueError, OSError) as primary_error:
                    diagnostics.append(f"Yahoo ^TNX full history: unavailable")
                    diagnostics.append(f"Yahoo ^TNX primary full history: {primary_error}")
                    try:
                        snapshot = download_treasury_yield_snapshot_with_ticker_history(config)
                    except (RuntimeError, ValueError, OSError) as retry_error:
                        diagnostics.append(f"Yahoo ^TNX full history retry: {retry_error}")
                        yahoo_probe = probe_yahoo_treasury_diagnostics(config)
                        diagnostics.extend(_yahoo_probe_diagnostics(yahoo_probe))
                        raise RuntimeError(
                            "Yahoo ^TNX complete history required for SMA20/SMA60 was unavailable."
                        ) from retry_error
            elif source == TreasuryDataSource.FRED_DGS10:
                snapshot = download_fred_treasury_yield_snapshot(config, now=timestamp)
            elif source == TreasuryDataSource.US_TREASURY:
                snapshot = download_us_treasury_yield_snapshot(config, now=timestamp)
            else:
                raise RuntimeError(f"Unsupported Treasury provider: {source}")
            _validate_live_freshness(snapshot, config, timestamp)
        except (RuntimeError, ValueError, OSError) as exc:
            diagnostics.append(f"{_PROVIDER_LABELS[source]}: {exc}")
            if source == TreasuryDataSource.YAHOO_TNX:
                yahoo_failed = True
            continue

        messages = snapshot.messages
        if yahoo_failed and source != TreasuryDataSource.YAHOO_TNX:
            messages = (
                f"Yahoo ^TNX was unavailable. Treasury data was loaded from "
                f"{_PROVIDER_LABELS[source]}.",
            )
            if yahoo_probe and _has_yahoo_probe_value(yahoo_probe):
                messages = (
                    "Yahoo ^TNX short history is available, but complete history "
                    "required for SMA20/SMA60 was unavailable. "
                    f"{_PROVIDER_LABELS[source]} is used for the valuation yield and trend.",
                )
        source_difference = _source_difference(yahoo_probe, snapshot)
        warnings = snapshot.warnings
        if (
            source_difference is not None
            and abs(source_difference) > config.source_difference_warning_pct_points
        ):
            warnings = (
                *warnings,
                "Yahoo ^TNX latest yield differs materially from the resolved Treasury source.",
            )
        return TreasuryYieldSnapshot(
            **{
                **snapshot.__dict__,
                "warnings": warnings,
                "messages": messages,
                "provider_diagnostics": tuple(
                    [
                        *diagnostics,
                        f"{_PROVIDER_LABELS[source]}: success",
                        *_resolved_source_diagnostics(snapshot, source_difference),
                    ]
                ),
                "used_fallback": False,
                "yahoo_quote_yield": None
                if yahoo_probe is None
                else yahoo_probe.yahoo_quote_yield,
                "yahoo_quote_field": None if yahoo_probe is None else yahoo_probe.yahoo_quote_field,
                "yahoo_short_history_yield": None
                if yahoo_probe is None
                else yahoo_probe.yahoo_short_history_yield,
                "yahoo_short_history_date": None
                if yahoo_probe is None
                else yahoo_probe.yahoo_short_history_date,
                "yahoo_short_history_available": False
                if yahoo_probe is None
                else yahoo_probe.yahoo_short_history_available,
                "yahoo_full_history_available": source == TreasuryDataSource.YAHOO_TNX,
                "source_difference_percentage_points": source_difference,
            }
        )

    raise RuntimeError("; ".join(diagnostics) or "No Treasury provider succeeded.")


def download_fred_treasury_yield_snapshot(
    config: TreasuryHistoryConfig,
    now: datetime | None = None,
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Download FRED DGS10 CSV history and return a live yield snapshot."""
    validate_history_config(config)
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={config.fred_series.strip()}"
    )
    text = _read_url_text(url, timeout_seconds)
    rows = csv.DictReader(io.StringIO(text))
    dates: list[str] = []
    values: list[float] = []
    for row in rows:
        raw_date = (row.get("observation_date") or row.get("DATE") or "").strip()
        raw_value = (row.get(config.fred_series) or row.get("DGS10") or "").strip()
        if not raw_date or raw_value in {"", "."}:
            continue
        parsed_date = _parse_iso_date(raw_date)
        value = _coerce_float(config.fred_series, raw_value)
        _validate_yield_percent(config.fred_series, value)
        dates.append(parsed_date.isoformat())
        values.append(value)
    snapshot = _snapshot_from_observations(
        symbol=config.fred_series,
        dates=dates,
        raw_values=values,
        config=config,
        source=TreasuryDataSource.FRED_DGS10,
        status=TreasuryDataStatus.LIVE,
        fetched_at=_utc_now() if now is None else now,
    )
    return snapshot


def download_us_treasury_yield_snapshot(
    config: TreasuryHistoryConfig,
    now: datetime | None = None,
    timeout_seconds: int = 10,
) -> TreasuryYieldSnapshot:
    """Download official daily Treasury par yield data and return a snapshot."""
    validate_history_config(config)
    url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/"
        "accounting/od/daily_treasury_rates"
        "?fields=record_date,bc_10year&sort=-record_date&page[size]=400"
    )
    payload = json.loads(_read_url_text(url, timeout_seconds))
    dates: list[str] = []
    values: list[float] = []
    for row in payload.get("data", ()):
        raw_date = row.get("record_date")
        raw_value = row.get("bc_10year")
        if raw_value in {None, "", "."}:
            continue
        parsed_date = _parse_iso_date(str(raw_date))
        value = _coerce_float("bc_10year", raw_value)
        _validate_yield_percent("bc_10year", value)
        dates.append(parsed_date.isoformat())
        values.append(value)
    dates.reverse()
    values.reverse()
    status = (
        TreasuryDataStatus.LIVE
        if len(values) >= config.long_window_observations
        else TreasuryDataStatus.PARTIAL_LIVE
    )
    if not values:
        raise RuntimeError("official Treasury data did not contain 10-year yields.")
    if len(values) < config.long_window_observations:
        latest = values[-1]
        timestamp = _utc_now() if now is None else now
        return TreasuryYieldSnapshot(
            symbol="US_TREASURY_10Y",
            yield_date=dates[-1],
            current_yield_percent=latest,
            sma_short_percent=latest,
            sma_long_percent=latest,
            observation_count=len(values),
            data_status=status,
            source=TreasuryDataSource.US_TREASURY,
            source_name=_PROVIDER_LABELS[TreasuryDataSource.US_TREASURY],
            fetched_at=timestamp,
        )
    return _snapshot_from_observations(
        symbol="US_TREASURY_10Y",
        dates=dates,
        raw_values=values,
        config=config,
        source=TreasuryDataSource.US_TREASURY,
        status=status,
        fetched_at=_utc_now() if now is None else now,
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
        source=TreasuryDataSource.CONFIG,
        source_name=_PROVIDER_LABELS[TreasuryDataSource.CONFIG],
        warnings=(warning, reason),
        provider_diagnostics=(reason,),
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
        source=TreasuryDataSource.NONE,
        source_name=_PROVIDER_LABELS[TreasuryDataSource.NONE],
        warnings=(
            "Treasury yield unavailable. Macro adjustment was applied neutrally.",
            reason,
        ),
        provider_diagnostics=(reason,),
        used_fallback=True,
        fetched_at=timestamp,
    )


def _snapshot_from_observations(
    symbol: str,
    dates: list[str],
    raw_values: list[float],
    config: TreasuryHistoryConfig,
    source: TreasuryDataSource,
    status: TreasuryDataStatus,
    fetched_at: datetime | None,
) -> TreasuryYieldSnapshot:
    if len(dates) != len(raw_values):
        raise ValueError("dates and raw_close_values must have the same length.")

    valid_dates: list[str] = []
    valid_yields: list[float] = []
    for raw_date, raw_value in zip(dates, raw_values):
        if _is_missing(raw_value):
            continue
        valid_dates.append(_format_date(raw_date))
        valid_yields.append(normalize_yield_value(raw_value, config.value_scale))

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
        data_status=status,
        source=source,
        source_name=_PROVIDER_LABELS[source],
        fetched_at=fetched_at,
    )


def _snapshot_from_yahoo_history(
    config: TreasuryHistoryConfig,
    history: Any,
    symbol: str,
    source: TreasuryDataSource,
    status: TreasuryDataStatus,
) -> TreasuryYieldSnapshot:
    if history.empty:
        raise RuntimeError(f"{symbol}: no Treasury yield history returned.")
    dates = [_format_date(value) for value in history.index]
    try:
        raw_close_values = list(history["Close"])
    except Exception as error:
        raise RuntimeError(f"{symbol}: Treasury yield history is missing Close.") from error
    return _snapshot_from_observations(
        symbol=symbol,
        dates=dates,
        raw_values=raw_close_values,
        config=config,
        source=source,
        status=status,
        fetched_at=_utc_now(),
    )


def _probe_yahoo_quote(ticker: Any) -> tuple[float | None, str | None]:
    try:
        info = ticker.get_info()
    except AttributeError:
        info = getattr(ticker, "info", {})
    except Exception:
        info = {}
    if not isinstance(info, dict):
        return None, None
    for field in ("regularMarketPrice", "previousClose"):
        raw_value = info.get(field)
        try:
            value = normalize_yield_value(raw_value, "percent")
        except ValueError:
            continue
        return value, field
    return None, None


def _yahoo_probe_diagnostics(probe: TreasuryYieldSnapshot) -> tuple[str, ...]:
    diagnostics = [
        "Yahoo ^TNX 5-day history: "
        + ("success" if probe.yahoo_short_history_available else "unavailable")
    ]
    if probe.yahoo_short_history_yield is not None:
        diagnostics.append(
            f"Yahoo latest observation: {probe.yahoo_short_history_yield:.3f}% "
            f"on {probe.yahoo_short_history_date}"
        )
    if probe.yahoo_quote_yield is not None:
        diagnostics.append(
            f"Yahoo current quote: {probe.yahoo_quote_yield:.3f}% "
            f"({probe.yahoo_quote_field})"
        )
    return tuple(diagnostics)


def _source_difference(
    yahoo_probe: TreasuryYieldSnapshot | None,
    resolved_snapshot: TreasuryYieldSnapshot,
) -> float | None:
    if yahoo_probe is None:
        return None
    yahoo_yield = yahoo_probe.yahoo_short_history_yield
    if yahoo_yield is None:
        yahoo_yield = yahoo_probe.yahoo_quote_yield
    if yahoo_yield is None:
        return None
    return yahoo_yield - resolved_snapshot.current_yield_percent


def _has_yahoo_probe_value(probe: TreasuryYieldSnapshot) -> bool:
    return probe.yahoo_short_history_available or probe.yahoo_quote_yield is not None


def _diagnostic_yield(
    config: TreasuryHistoryConfig,
    short_yield: float | None,
    quote_yield: float | None,
) -> float:
    if short_yield is not None:
        return short_yield
    if quote_yield is not None:
        return quote_yield
    if config.fallback_yield_percent is not None:
        return config.fallback_yield_percent
    return 4.3


def _resolved_source_diagnostics(
    snapshot: TreasuryYieldSnapshot,
    source_difference: float | None,
) -> tuple[str, ...]:
    diagnostics = [
        f"Resolved source: {snapshot.source_name}",
        f"Resolved yield: {snapshot.current_yield_percent:.3f}%",
    ]
    if source_difference is not None:
        diagnostics.append(f"Yahoo/resolved difference: {source_difference:+.3f} percentage points")
    return tuple(diagnostics)


def _read_url_text(url: str, timeout_seconds: int) -> str:
    with urlopen(url, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8")


def _validate_live_freshness(
    snapshot: TreasuryYieldSnapshot,
    config: TreasuryHistoryConfig,
    now: datetime,
) -> None:
    source_date = _parse_iso_date(snapshot.yield_date)
    age = _business_days_between(source_date, now.date())
    if age > config.max_live_business_days_old:
        raise RuntimeError(
            f"latest observation {snapshot.yield_date} is {age} business days old."
        )


def _business_days_between(start: date, end: date) -> int:
    if start >= end:
        return 0
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count


def _validate_providers(providers: tuple[str, ...]) -> None:
    if not isinstance(providers, tuple) or not providers:
        raise ValueError("providers must be a non-empty tuple.")
    seen: set[str] = set()
    for provider in providers:
        if provider not in _PROVIDER_NAMES:
            raise ValueError(f"Unsupported Treasury provider: {provider}")
        if provider in seen:
            raise ValueError(f"Duplicate Treasury provider: {provider}")
        seen.add(provider)


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


def _validate_attempts(attempts: int) -> None:
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ValueError("attempts must be an integer.")
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3.")


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


def _validate_non_negative_percent(name: str, value: float) -> None:
    number = _coerce_float(name, value)
    if number < 0:
        raise ValueError(f"{name} must be greater than or equal to 0.")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def _parse_iso_date(value: str) -> date:
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError as exc:
        raise ValueError(f"date is not parseable: {value}") from exc


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
