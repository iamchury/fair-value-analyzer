from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from src.analysis.ranking_engine import (
    MomentumSentimentPosition,
    momentum_reference_interpretation,
)
from src.reports.batch_text_report import format_batch_stock_analysis_report


DEFAULT_SYMBOL_TEXT = "MU, NVDA, AMAT, LITE, COHR"
MAX_SYMBOLS = 20
RANKING_COLUMNS = [
    "Rank",
    "Symbol",
    "Score",
    "Category",
    "Eligibility",
    "Recommendation V2",
    "Valuation",
    "Evidence",
    "Agreement",
    "Momentum",
    "Current Price",
    "Base Intrinsic Value",
    "Current vs Base %",
    "Current RSI",
    "RSI50 Reference Price",
    "Current vs RSI50 %",
    "RSI50 Sentiment",
]
_SYMBOL_RE = re.compile(r"^[A-Z0-9.^=\-]+$")


@dataclass(frozen=True)
class WebConfigPaths:
    valuation_config_path: str = "config/valuation.yaml"
    profiles_path: str = "config/valuation_profiles.yaml"
    eps_selection_path: str = "config/eps_selection.yaml"
    industry_policies_path: str = "config/industry_policies.yaml"
    analyst_consensus_path: str = "config/analyst_consensus.yaml"
    agreement_config_path: str = "config/agreement_engine.yaml"
    momentum_config_path: str = "config/momentum_reference.yaml"
    range_config_path: str = "config/fair_value_range.yaml"
    recommendation_v2_config_path: str = "config/recommendation_v2.yaml"
    ranking_config_path: str = "config/ranking_engine.yaml"


DEFAULT_WEB_CONFIG = WebConfigPaths()


def parse_ticker_symbols(text: str, max_symbols: int = MAX_SYMBOLS) -> tuple[str, ...]:
    if not isinstance(text, str):
        raise ValueError("Ticker input must be text.")
    symbols: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for raw in re.split(r"[,\s]+", text):
        symbol = raw.strip().upper()
        if not symbol:
            continue
        if not _SYMBOL_RE.fullmatch(symbol):
            invalid.append(raw.strip())
            continue
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if invalid:
        raise ValueError(f"Invalid ticker symbol: {invalid[0]}.")
    if not symbols:
        raise ValueError("Enter at least one ticker symbol.")
    if len(symbols) > max_symbols:
        raise ValueError(f"Enter no more than {max_symbols} ticker symbols.")
    return tuple(symbols)


def build_ranking_dataframe(result: Any) -> pd.DataFrame:
    rows = [_ranking_row(entry) for entry in _ranking_entries(result)]
    return pd.DataFrame(rows, columns=RANKING_COLUMNS)


def filter_ranking_dataframe(
    dataframe: pd.DataFrame,
    eligibility: str = "All",
    category: str = "All",
    recommendation: str = "All",
    sentiment: str = "All",
) -> pd.DataFrame:
    filtered = dataframe
    choices = {
        "Eligibility": eligibility,
        "Category": category,
        "Recommendation V2": recommendation,
        "RSI50 Sentiment": sentiment,
    }
    for column, selected in choices.items():
        if selected != "All" and column in filtered:
            filtered = filtered[filtered[column] == selected]
    return filtered


def ranking_summary(result: Any) -> dict[str, Any]:
    entries = _ranking_entries(result)
    eligible = [entry for entry in entries if getattr(entry, "eligible", False)]
    insufficient = [entry for entry in entries if not getattr(entry, "eligible", False)]
    sentiments = [_plain(getattr(entry, "momentum_sentiment_position", None)) for entry in entries]
    return {
        "top_symbol": getattr(getattr(result, "ranking_result", None), "top_symbol", None),
        "top_score": getattr(getattr(result, "ranking_result", None), "top_score", None),
        "eligible_count": len(eligible),
        "insufficient_count": len(insufficient) + len(getattr(result, "failures", ()) or ()),
        "above_rsi50": sum(1 for value in sentiments if "ABOVE" in value),
        "near_rsi50": sum(1 for value in sentiments if value == "NEAR_NEUTRAL_REFERENCE"),
        "below_rsi50": sum(1 for value in sentiments if "BELOW" in value),
    }


def build_chart_dataframe(result: Any, symbol: str) -> pd.DataFrame:
    entry = get_ranking_entry(result, symbol)
    analysis = get_successful_result(result, symbol)
    recommendation = getattr(analysis, "recommendation_v2", None)
    rows = [
        ("Current Price", getattr(entry, "current_price", None), "Market"),
        ("Conservative Intrinsic Value", getattr(recommendation, "conservative_value", None), "Intrinsic"),
        ("Base Intrinsic Value", getattr(entry, "base_value", None), "Intrinsic"),
        ("Optimistic Intrinsic Value", getattr(recommendation, "optimistic_intrinsic_value", None), "Intrinsic"),
        ("Analyst Market Expectation", getattr(recommendation, "analyst_expectation", None), "Market Expectation"),
        ("RSI50 Reference Price", getattr(entry, "rsi_reference_price", None), "Momentum Reference"),
    ]
    return pd.DataFrame(
        [{"Measure": label, "Value": value, "Category": group} for label, value, group in rows if value is not None]
    )


def rsi_reference_details(entry: Any) -> dict[str, str]:
    return {
        "Current Price": format_price(getattr(entry, "current_price", None)),
        "Current RSI": format_number(getattr(entry, "current_rsi", None)),
        "Reference Date": format_text(_date_text(getattr(entry, "rsi_reference_date", None))),
        "RSI50 Reference Price": format_price(getattr(entry, "rsi_reference_price", None)),
        "RSI at Reference": format_number(getattr(entry, "rsi_reference_rsi", None)),
        "Cross Direction": format_text(getattr(entry, "rsi_cross_direction", None)),
        "Current vs Reference": format_price(getattr(entry, "current_vs_rsi_reference_amount", None), signed=True),
        "Current vs RSI50 %": format_percent(getattr(entry, "current_vs_rsi_reference_pct", None), signed=True),
        "Sentiment Position": format_text(getattr(entry, "momentum_sentiment_position", None)),
        "Reference Status": format_text(getattr(entry, "momentum_reference_status", None)),
        "Price Field": format_text(getattr(entry, "momentum_reference_price_field", None)),
        "Trading Days Since": format_text(getattr(entry, "momentum_reference_trading_days", None)),
    }


def rsi_reference_interpretation(entry: Any) -> tuple[str, ...]:
    return momentum_reference_interpretation(entry)


def ranking_csv_download(result: Any) -> str:
    return format_batch_stock_analysis_report(result, ranking_only=True, ranking_format="csv")


def ranking_json_download(result: Any) -> str:
    return format_batch_stock_analysis_report(result, ranking_only=True, ranking_format="json")


def get_ranking_entry(result: Any, symbol: str) -> Any | None:
    target = symbol.upper()
    for entry in _ranking_entries(result):
        if getattr(entry, "symbol", None) == target:
            return entry
    return None


def get_successful_result(result: Any, symbol: str) -> Any | None:
    target = symbol.upper()
    for item in tuple(getattr(result, "successful_results", ()) or ()):
        item_symbol = getattr(getattr(item, "company", None), "symbol", None)
        if item_symbol == target:
            return item
    return None


def format_price(value: Any, currency: str | None = None, signed: bool = False) -> str:
    if not _number(value):
        return "N/A"
    sign = "+" if signed and float(value) >= 0 else ""
    suffix = "" if currency is None else f" {currency}"
    return f"{sign}{float(value):,.2f}{suffix}"


def format_percent(value: Any, signed: bool = False) -> str:
    if not _number(value):
        return "N/A"
    sign = "+" if signed and float(value) >= 0 else ""
    return f"{sign}{float(value):.2f}%"


def format_number(value: Any) -> str:
    if not _number(value):
        return "N/A"
    return f"{float(value):,.2f}"


def format_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return value.value
    text = str(value).strip()
    return text or "N/A"


def _ranking_row(entry: Any) -> dict[str, str]:
    return {
        "Rank": format_text(getattr(entry, "rank", None)),
        "Symbol": format_text(getattr(entry, "symbol", None)),
        "Score": format_number(getattr(entry, "normalized_score", None)),
        "Category": format_text(getattr(entry, "category", None)),
        "Eligibility": "Eligible" if getattr(entry, "eligible", False) else "Ineligible",
        "Recommendation V2": format_text(getattr(entry, "recommendation_v2", None)),
        "Valuation": format_text(getattr(entry, "valuation_condition", None)),
        "Evidence": format_text(getattr(entry, "evidence_quality", None)),
        "Agreement": format_text(getattr(entry, "agreement", None)),
        "Momentum": format_text(getattr(entry, "momentum", None)),
        "Current Price": format_price(getattr(entry, "current_price", None)),
        "Base Intrinsic Value": format_price(getattr(entry, "base_value", None)),
        "Current vs Base %": format_percent(getattr(entry, "current_vs_base_pct", None), signed=True),
        "Current RSI": format_number(getattr(entry, "current_rsi", None)),
        "RSI50 Reference Price": format_price(getattr(entry, "rsi_reference_price", None)),
        "Current vs RSI50 %": format_percent(getattr(entry, "current_vs_rsi_reference_pct", None), signed=True),
        "RSI50 Sentiment": format_text(getattr(entry, "momentum_sentiment_position", None)),
    }


def _ranking_entries(result: Any) -> tuple[Any, ...]:
    return tuple(getattr(getattr(result, "ranking_result", None), "entries", ()) or ())


def _plain(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    return "" if value is None else str(value)


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)

