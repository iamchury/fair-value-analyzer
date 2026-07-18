from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite, isnan
from typing import Any, Mapping

import yfinance as yf


@dataclass(frozen=True)
class CompanyFundamentals:
    symbol: str
    company_name: str | None
    currency: str | None
    current_price: float | None
    previous_close: float | None
    market_cap: float | None
    sector: str | None
    industry: str | None
    trailing_eps: float | None
    forward_eps: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    analyst_target_mean_price: float | None
    analyst_target_high_price: float | None
    analyst_target_low_price: float | None
    analyst_count: int | None = None


@dataclass(frozen=True)
class EPSRawFieldSource:
    normalized_name: str
    raw_source: str
    raw_field: str
    value: object
    period_label: str | None
    source_timestamp: datetime | None
    warning: str | None

    def __post_init__(self) -> None:
        _require_non_empty_string("normalized_name", self.normalized_name)
        _require_non_empty_string("raw_source", self.raw_source)
        _require_non_empty_string("raw_field", self.raw_field)
        if self.period_label is not None:
            _require_non_empty_string("period_label", self.period_label)
        if self.warning is not None:
            _require_non_empty_string("warning", self.warning)
        if self.source_timestamp is not None:
            _require_aware_datetime("source_timestamp", self.source_timestamp)


@dataclass(frozen=True)
class YahooEPSEstimate:
    period_label: str
    estimate: float | None
    low_estimate: float | None
    high_estimate: float | None
    year_ago_eps: float | None
    analyst_count: int | None

    def __post_init__(self) -> None:
        _require_non_empty_string("period_label", self.period_label)
        _validate_optional_number("estimate", self.estimate)
        _validate_optional_number("low_estimate", self.low_estimate)
        _validate_optional_number("high_estimate", self.high_estimate)
        _validate_optional_number("year_ago_eps", self.year_ago_eps)
        _validate_optional_analyst_count(self.analyst_count)


@dataclass(frozen=True)
class YahooEPSRawSnapshot:
    symbol: str
    trailing_eps: float | None
    forward_eps: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    earnings_growth: float | None
    quarterly_earnings_growth: float | None
    most_recent_quarter: date | datetime | None
    last_fiscal_year_end: date | datetime | None
    next_fiscal_year_end: date | datetime | None
    last_split_date: date | datetime | None
    shares_outstanding: float | None
    implied_shares_outstanding: float | None
    price_to_book: float | None
    current_quarter_estimate: YahooEPSEstimate | None
    next_quarter_estimate: YahooEPSEstimate | None
    current_year_estimate: YahooEPSEstimate | None
    next_year_estimate: YahooEPSEstimate | None
    source_timestamp: datetime
    raw_field_sources: tuple[EPSRawFieldSource, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        normalize_symbol(self.symbol)
        for field_name in (
            "trailing_eps",
            "forward_eps",
            "trailing_pe",
            "forward_pe",
            "peg_ratio",
            "earnings_growth",
            "quarterly_earnings_growth",
            "shares_outstanding",
            "implied_shares_outstanding",
            "price_to_book",
        ):
            _validate_optional_number(field_name, getattr(self, field_name))
        for field_name in (
            "most_recent_quarter",
            "last_fiscal_year_end",
            "next_fiscal_year_end",
            "last_split_date",
        ):
            _validate_optional_date(field_name, getattr(self, field_name))
        _require_aware_datetime("source_timestamp", self.source_timestamp)
        if not isinstance(self.raw_field_sources, tuple):
            raise ValueError("raw_field_sources must be a tuple.")
        if not isinstance(self.warnings, tuple):
            raise ValueError("warnings must be a tuple.")
        for warning in self.warnings:
            _require_non_empty_string("warnings", warning)


@dataclass(frozen=True)
class CompanyFundamentalsWithEPSRawSnapshot:
    fundamentals: CompanyFundamentals
    eps_snapshot: YahooEPSRawSnapshot


def normalize_symbol(symbol: str) -> str:
    """Normalize a Yahoo Finance ticker symbol for lookup."""
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty.")
    if any(character.isspace() for character in normalized_symbol):
        raise ValueError("symbol must not contain spaces.")
    return normalized_symbol


def normalize_optional_float(value: object, field_name: str) -> float | None:
    """Normalize an optional numeric Yahoo field to float."""
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean.")

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric.") from error

    if not isfinite(normalized_value):
        raise ValueError(f"{field_name} must be finite.")
    return normalized_value


def normalize_optional_string(value: object) -> str | None:
    """Normalize an optional Yahoo string field."""
    if _is_missing(value):
        return None
    if not isinstance(value, str):
        raise ValueError("string field must be a string.")

    normalized_value = value.strip()
    return normalized_value or None


def extract_company_fundamentals(
    symbol: str,
    info: dict,
    fast_info: object | None = None,
) -> CompanyFundamentals:
    """Extract normalized company fundamentals from Yahoo info objects."""
    normalized_symbol = normalize_symbol(symbol)
    if not isinstance(info, dict):
        raise ValueError("info must be a dictionary.")

    return CompanyFundamentals(
        symbol=normalized_symbol,
        company_name=normalize_optional_string(
            _first_present(info, fast_info, ("longName", "shortName"))
        ),
        currency=normalize_optional_string(_first_present(info, fast_info, ("currency",))),
        current_price=_non_negative(
            normalize_optional_float(
                _first_present(
                    info,
                    fast_info,
                    ("currentPrice", "regularMarketPrice", "last_price"),
                ),
                "current_price",
            ),
            "current_price",
        ),
        previous_close=_non_negative(
            normalize_optional_float(
                _first_present(
                    info,
                    fast_info,
                    (
                        "previousClose",
                        "regularMarketPreviousClose",
                        "previous_close",
                    ),
                ),
                "previous_close",
            ),
            "previous_close",
        ),
        market_cap=_non_negative(
            normalize_optional_float(
                _first_present(info, fast_info, ("marketCap", "market_cap")),
                "market_cap",
            ),
            "market_cap",
        ),
        sector=normalize_optional_string(_first_present(info, fast_info, ("sector",))),
        industry=normalize_optional_string(
            _first_present(info, fast_info, ("industry",))
        ),
        trailing_eps=normalize_optional_float(
            _first_present(info, fast_info, ("trailingEps",)),
            "trailing_eps",
        ),
        forward_eps=normalize_optional_float(
            _first_present(info, fast_info, ("forwardEps",)),
            "forward_eps",
        ),
        trailing_pe=normalize_optional_float(
            _first_present(info, fast_info, ("trailingPE",)),
            "trailing_pe",
        ),
        forward_pe=normalize_optional_float(
            _first_present(info, fast_info, ("forwardPE",)),
            "forward_pe",
        ),
        peg_ratio=normalize_optional_float(
            _first_present(info, fast_info, ("pegRatio", "trailingPegRatio")),
            "peg_ratio",
        ),
        fifty_two_week_high=_non_negative(
            normalize_optional_float(
                _first_present(
                    info,
                    fast_info,
                    ("fiftyTwoWeekHigh", "year_high"),
                ),
                "fifty_two_week_high",
            ),
            "fifty_two_week_high",
        ),
        fifty_two_week_low=_non_negative(
            normalize_optional_float(
                _first_present(
                    info,
                    fast_info,
                    ("fiftyTwoWeekLow", "year_low"),
                ),
                "fifty_two_week_low",
            ),
            "fifty_two_week_low",
        ),
        analyst_target_mean_price=_non_negative(
            normalize_optional_float(
                _first_present(info, fast_info, ("targetMeanPrice",)),
                "analyst_target_mean_price",
            ),
            "analyst_target_mean_price",
        ),
        analyst_target_high_price=_non_negative(
            normalize_optional_float(
                _first_present(info, fast_info, ("targetHighPrice",)),
                "analyst_target_high_price",
            ),
            "analyst_target_high_price",
        ),
        analyst_target_low_price=_non_negative(
            normalize_optional_float(
                _first_present(info, fast_info, ("targetLowPrice",)),
                "analyst_target_low_price",
            ),
            "analyst_target_low_price",
        ),
        analyst_count=_non_negative_int(
            _first_present(
                info,
                fast_info,
                ("numberOfAnalystOpinions", "numberOfAnalysts"),
            ),
            "analyst_count",
        ),
    )


def extract_eps_raw_snapshot(
    symbol: str,
    info: dict,
    earnings_estimate: object | None = None,
    source_timestamp: datetime | None = None,
) -> YahooEPSRawSnapshot:
    """Extract plain immutable EPS source data from Yahoo-like objects."""
    normalized_symbol = normalize_symbol(symbol)
    if not isinstance(info, dict):
        raise ValueError("info must be a dictionary.")

    timestamp = source_timestamp or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    warnings: list[str] = []
    sources: list[EPSRawFieldSource] = []

    def field(
        normalized_name: str,
        raw_field: str,
        *,
        date_field: bool = False,
    ) -> Any:
        raw_value = info.get(raw_field)
        if date_field:
            value = normalize_optional_date(raw_value, raw_field, warnings)
        else:
            value = normalize_optional_float(raw_value, normalized_name)
        sources.append(
            EPSRawFieldSource(
                normalized_name=normalized_name,
                raw_source='yfinance.Ticker.info',
                raw_field=raw_field,
                value=value,
                period_label=None,
                source_timestamp=timestamp,
                warning=None if value is not None else f"{raw_field} unavailable.",
            )
        )
        return value

    estimates, estimate_warnings, estimate_sources = extract_eps_estimates(
        earnings_estimate,
        timestamp,
    )
    warnings.extend(estimate_warnings)
    sources.extend(estimate_sources)

    return YahooEPSRawSnapshot(
        symbol=normalized_symbol,
        trailing_eps=field("trailing_eps", "trailingEps"),
        forward_eps=field("forward_eps", "forwardEps"),
        trailing_pe=field("trailing_pe", "trailingPE"),
        forward_pe=field("forward_pe", "forwardPE"),
        peg_ratio=field("peg_ratio", "pegRatio"),
        earnings_growth=field("earnings_growth", "earningsGrowth"),
        quarterly_earnings_growth=field(
            "quarterly_earnings_growth",
            "earningsQuarterlyGrowth",
        ),
        most_recent_quarter=field(
            "most_recent_quarter",
            "mostRecentQuarter",
            date_field=True,
        ),
        last_fiscal_year_end=field(
            "last_fiscal_year_end",
            "lastFiscalYearEnd",
            date_field=True,
        ),
        next_fiscal_year_end=field(
            "next_fiscal_year_end",
            "nextFiscalYearEnd",
            date_field=True,
        ),
        last_split_date=field("last_split_date", "lastSplitDate", date_field=True),
        shares_outstanding=field("shares_outstanding", "sharesOutstanding"),
        implied_shares_outstanding=field(
            "implied_shares_outstanding",
            "impliedSharesOutstanding",
        ),
        price_to_book=field("price_to_book", "priceToBook"),
        current_quarter_estimate=estimates["0q"],
        next_quarter_estimate=estimates["+1q"],
        current_year_estimate=estimates["0y"],
        next_year_estimate=estimates["+1y"],
        source_timestamp=timestamp,
        raw_field_sources=tuple(sources),
        warnings=tuple(warnings),
    )


def extract_eps_estimates(
    earnings_estimate: object | None,
    source_timestamp: datetime,
) -> tuple[dict[str, YahooEPSEstimate | None], tuple[str, ...], tuple[EPSRawFieldSource, ...]]:
    """Normalize supported yfinance earnings estimate table shapes."""
    empty = {"0q": None, "+1q": None, "0y": None, "+1y": None}
    if earnings_estimate is None:
        return empty, ("earnings estimate table unavailable.",), ()
    if getattr(earnings_estimate, "empty", False):
        return empty, ("earnings estimate table unavailable.",), ()
    if not hasattr(earnings_estimate, "loc"):
        return empty, ("earnings estimate table shape is unsupported.",), ()

    columns = set(getattr(earnings_estimate, "columns", ()))
    supported = {"avg", "low", "high", "yearAgoEps", "numberOfAnalysts"}
    if not columns.intersection(supported):
        return empty, ("earnings estimate table columns are unsupported.",), ()

    estimates = dict(empty)
    warnings: list[str] = []
    sources: list[EPSRawFieldSource] = []
    for label in ("0q", "+1q", "0y", "+1y"):
        try:
            row = earnings_estimate.loc[label]
        except Exception:
            warnings.append(f"earnings estimate row {label} unavailable.")
            continue

        estimate = _row_optional_float(row, "avg", f"earnings_estimate[{label}].avg")
        low = _row_optional_float(row, "low", f"earnings_estimate[{label}].low")
        high = _row_optional_float(row, "high", f"earnings_estimate[{label}].high")
        year_ago = _row_optional_float(
            row,
            "yearAgoEps",
            f"earnings_estimate[{label}].yearAgoEps",
        )
        analyst_count = _row_optional_int(
            row,
            "numberOfAnalysts",
            f"earnings_estimate[{label}].numberOfAnalysts",
        )
        estimates[label] = YahooEPSEstimate(
            period_label=label,
            estimate=estimate,
            low_estimate=low,
            high_estimate=high,
            year_ago_eps=year_ago,
            analyst_count=analyst_count,
        )
        sources.append(
            EPSRawFieldSource(
                normalized_name=_estimate_name(label),
                raw_source="yfinance.Ticker.earnings_estimate",
                raw_field=label,
                value=estimate,
                period_label=label,
                source_timestamp=source_timestamp,
                warning=None if estimate is not None else "average estimate unavailable.",
            )
        )
    return estimates, tuple(warnings), tuple(sources)


def download_company_fundamentals(symbol: str) -> CompanyFundamentals:
    """Download and normalize Yahoo Finance company fundamentals."""
    normalized_symbol = normalize_symbol(symbol)

    try:
        ticker = yf.Ticker(normalized_symbol)
        info = ticker.info
        fast_info = ticker.fast_info
    except Exception as error:
        raise RuntimeError(
            f"{normalized_symbol}: failed to download company fundamentals."
        ) from error

    if info is None:
        info = {}
    if not isinstance(info, dict):
        raise RuntimeError(f"{normalized_symbol}: ticker.info must be a dictionary.")

    return extract_company_fundamentals(normalized_symbol, info, fast_info)


def download_company_fundamentals_with_eps_snapshot(
    symbol: str,
) -> CompanyFundamentalsWithEPSRawSnapshot:
    """Download company fundamentals and EPS source data from one ticker object."""
    normalized_symbol = normalize_symbol(symbol)
    source_timestamp = datetime.now(timezone.utc)

    try:
        ticker = yf.Ticker(normalized_symbol)
        info = ticker.info
        fast_info = ticker.fast_info
    except Exception as error:
        raise RuntimeError(
            f"{normalized_symbol}: failed to download company fundamentals."
        ) from error

    if info is None:
        info = {}
    if not isinstance(info, dict):
        raise RuntimeError(f"{normalized_symbol}: ticker.info must be a dictionary.")

    estimate_warnings: list[str] = []
    earnings_estimate = None
    try:
        earnings_estimate = _read_earnings_estimate(ticker)
    except Exception as error:
        estimate_warnings.append(
            f"earnings estimate table unavailable: {type(error).__name__}."
        )

    fundamentals = extract_company_fundamentals(normalized_symbol, info, fast_info)
    snapshot = extract_eps_raw_snapshot(
        normalized_symbol,
        info,
        earnings_estimate,
        source_timestamp,
    )
    if estimate_warnings:
        snapshot = YahooEPSRawSnapshot(
            symbol=snapshot.symbol,
            trailing_eps=snapshot.trailing_eps,
            forward_eps=snapshot.forward_eps,
            trailing_pe=snapshot.trailing_pe,
            forward_pe=snapshot.forward_pe,
            peg_ratio=snapshot.peg_ratio,
            earnings_growth=snapshot.earnings_growth,
            quarterly_earnings_growth=snapshot.quarterly_earnings_growth,
            most_recent_quarter=snapshot.most_recent_quarter,
            last_fiscal_year_end=snapshot.last_fiscal_year_end,
            next_fiscal_year_end=snapshot.next_fiscal_year_end,
            last_split_date=snapshot.last_split_date,
            shares_outstanding=snapshot.shares_outstanding,
            implied_shares_outstanding=snapshot.implied_shares_outstanding,
            price_to_book=snapshot.price_to_book,
            current_quarter_estimate=snapshot.current_quarter_estimate,
            next_quarter_estimate=snapshot.next_quarter_estimate,
            current_year_estimate=snapshot.current_year_estimate,
            next_year_estimate=snapshot.next_year_estimate,
            source_timestamp=snapshot.source_timestamp,
            raw_field_sources=snapshot.raw_field_sources,
            warnings=snapshot.warnings + tuple(estimate_warnings),
        )
    return CompanyFundamentalsWithEPSRawSnapshot(
        fundamentals=fundamentals,
        eps_snapshot=snapshot,
    )


def _first_present(info: dict, fast_info: object | None, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = info.get(key)
        if not _is_missing(value):
            return value

    for key in keys:
        value = _read_fast_info(fast_info, key)
        if not _is_missing(value):
            return value

    return None


def _read_fast_info(fast_info: object | None, key: str) -> Any:
    if fast_info is None:
        return None
    if isinstance(fast_info, Mapping):
        return fast_info.get(key)
    return getattr(fast_info, key, None)


def _non_negative(value: float | None, field_name: str) -> float | None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _non_negative_int(value: object, field_name: str) -> int | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be an integer.")
    count = int(value)
    if count < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return count


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if type(value).__name__ in {"NAType", "NaTType"}:
        return True
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def normalize_optional_date(
    value: object,
    field_name: str,
    warnings: list[str] | None = None,
) -> date | datetime | None:
    """Normalize optional Yahoo date-like values."""
    if _is_missing(value):
        return None
    try:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value), timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text[:10]).date()
    except (TypeError, ValueError, OSError):
        if warnings is not None:
            warnings.append(f"{field_name} date value is invalid.")
        return None


def _read_earnings_estimate(ticker: object) -> object | None:
    if hasattr(ticker, "earnings_estimate"):
        value = getattr(ticker, "earnings_estimate")
        if value is not None:
            return value
    if hasattr(ticker, "get_earnings_estimate"):
        return ticker.get_earnings_estimate()
    return None


def _row_value(row: object, column: str) -> object:
    if isinstance(row, Mapping):
        return row.get(column)
    try:
        return row[column]
    except Exception:
        return None


def _row_optional_float(row: object, column: str, field_name: str) -> float | None:
    return normalize_optional_float(_row_value(row, column), field_name)


def _row_optional_int(row: object, column: str, field_name: str) -> int | None:
    value = _row_value(row, column)
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be an integer.")
    count = int(value)
    if count < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return count


def _estimate_name(label: str) -> str:
    return {
        "0q": "current_quarter_estimate",
        "+1q": "next_quarter_estimate",
        "0y": "current_year_estimate",
        "+1y": "next_year_estimate",
    }[label]


def _require_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _validate_optional_number(field_name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number or None.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _validate_optional_analyst_count(value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("analyst_count must be an integer or None.")
    if value < 0:
        raise ValueError("analyst_count must be non-negative.")


def _validate_optional_date(field_name: str, value: date | datetime | None) -> None:
    if value is None:
        return
    if not isinstance(value, (date, datetime)):
        raise ValueError(f"{field_name} must be a date, datetime, or None.")


def _require_aware_datetime(field_name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
