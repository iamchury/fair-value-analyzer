from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from typing import Any

import yfinance as yf

from src.yahoo.company import normalize_symbol


@dataclass(frozen=True)
class HistoricalPriceRow:
    date: date
    close: float | None
    adjusted_close: float | None


@dataclass(frozen=True)
class HistoricalPriceSeries:
    symbol: str
    rows: tuple[HistoricalPriceRow, ...]


def download_daily_price_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> HistoricalPriceSeries:
    normalized = normalize_symbol(symbol)
    try:
        history = yf.Ticker(normalized).history(period=period, interval=interval)
    except Exception as exc:
        raise RuntimeError(f"{normalized}: failed to download price history.") from exc
    if getattr(history, "empty", False):
        raise RuntimeError(f"{normalized}: no price history returned.")
    return extract_price_history(normalized, history)


def extract_price_history(symbol: str, history: Any) -> HistoricalPriceSeries:
    normalized = normalize_symbol(symbol)
    try:
        raw_dates = list(history.index)
        raw_close = list(history["Close"])
    except Exception as exc:
        raise ValueError("history must contain date index and Close column.") from exc
    try:
        raw_adjusted = list(history["Adj Close"])
    except Exception:
        raw_adjusted = [None] * len(raw_close)
    rows_by_date: dict[date, HistoricalPriceRow] = {}
    for raw_date, close, adjusted in zip(raw_dates, raw_close, raw_adjusted):
        row_date = _normalize_date(raw_date)
        if row_date is None:
            continue
        rows_by_date[row_date] = HistoricalPriceRow(
            date=row_date,
            close=_optional_positive_float(close),
            adjusted_close=_optional_positive_float(adjusted),
        )
    return HistoricalPriceSeries(
        symbol=normalized,
        rows=tuple(rows_by_date[key] for key in sorted(rows_by_date)),
    )


def _normalize_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _optional_positive_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(result) or result <= 0:
        return None
    return result
