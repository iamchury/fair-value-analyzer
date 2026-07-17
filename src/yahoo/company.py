from dataclasses import dataclass
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
    )


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
