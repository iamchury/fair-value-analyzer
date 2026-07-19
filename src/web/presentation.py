from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from math import isfinite
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
    "RSI50 Reference",
    "Current vs RSI50 %",
    "RSI50 Sentiment",
]
_SYMBOL_RE = re.compile(r"^[A-Z0-9.^=\-]+$")
_DISPLAY_LABELS = {
    "STRONG_BUY": "Strong Buy",
    "BUY": "Buy",
    "ACCUMULATE": "Accumulate",
    "HOLD": "Hold",
    "REDUCE": "Reduce",
    "SELL": "Sell",
    "AVOID": "Avoid",
    "INSUFFICIENT_DATA": "Insufficient Data",
    "TOP_OPPORTUNITY": "Top Opportunity",
    "ATTRACTIVE": "Attractive",
    "WATCHLIST": "Watchlist",
    "NEUTRAL": "Neutral",
    "CAUTION": "Caution",
    "INSUFFICIENT": "Insufficient",
    "DEEPLY_UNDERVALUED": "Deeply Undervalued",
    "UNDERVALUED": "Undervalued",
    "SLIGHTLY_UNDERVALUED": "Slightly Undervalued",
    "NEAR_FAIR_VALUE": "Near Fair Value",
    "MODERATELY_OVERVALUED": "Moderately Overvalued",
    "SIGNIFICANTLY_OVERVALUED": "Significantly Overvalued",
    "EXTREMELY_OVERVALUED": "Extremely Overvalued",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
    "STRONG": "Strong",
    "MODERATE": "Moderate",
    "WEAK": "Weak",
    "CONFLICTED": "Conflicted",
    "STRONG_POSITIVE": "Strong Positive",
    "POSITIVE": "Positive",
    "STRONG_NEGATIVE": "Strong Negative",
    "UNAVAILABLE": "Unavailable",
    "WELL_ABOVE_NEUTRAL_REFERENCE": "Well Above",
    "ABOVE_NEUTRAL_REFERENCE": "Above",
    "NEAR_NEUTRAL_REFERENCE": "Near",
    "BELOW_NEUTRAL_REFERENCE": "Below",
    "WELL_BELOW_NEUTRAL_REFERENCE": "Well Below",
    "AUTOMATIC_PER": "Automatic PER",
    "RESEARCH_PER": "Research PER",
    "DCF_REFERENCE": "DCF Reference",
    "ANALYST_CONSENSUS": "Analyst Consensus",
    "INTRINSIC_VALUE": "Intrinsic Value",
    "MARKET_EXPECTATION": "Market Expectation",
    "REFERENCE_VALUE": "Reference Value",
    "COMPLETE": "Complete",
    "PARTIAL": "Partial",
    "NOT_OUTLIER": "Not Outlier",
    "POSSIBLE_OUTLIER": "Possible Outlier",
    "OUTLIER": "Outlier",
    "NOT_EVALUATED": "Not Evaluated",
    "CROSS_ABOVE": "Cross Above",
    "CROSS_BELOW": "Cross Below",
    "NEAREST_TO_50": "Nearest To 50",
    "CLOSE": "Close",
    "ADJUSTED_CLOSE": "Adjusted Close",
    "ALIGNED": "Aligned",
    "V2_MORE_BULLISH": "V2 More Bullish",
    "V2_MORE_BEARISH": "V2 More Bearish",
    "NOT_COMPARABLE": "Not Comparable",
}
FULL_SUMMARY_METRIC_LABELS = (
    "Top Eligible Symbol",
    "Top Ranking Score",
    "Eligible Symbols",
    "Insufficient Symbols",
    "Above RSI50",
    "Near RSI50",
    "Below RSI50",
    "Successful / Failed",
)


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


def style_ranking_dataframe(dataframe: pd.DataFrame) -> Any:
    return dataframe.style.map(_cell_style)


def cell_emphasis(value: Any) -> str:
    text = str(value)
    positive = {"Strong Buy", "Buy", "Accumulate", "Eligible", "Deeply Undervalued", "Undervalued", "Slightly Undervalued", "Well Above", "Above", "Strong Positive", "Positive"}
    neutral = {"Hold", "Near Fair Value", "Near", "Neutral", "Watchlist"}
    negative = {"Reduce", "Sell", "Avoid", "Moderately Overvalued", "Significantly Overvalued", "Extremely Overvalued", "Below", "Well Below", "Weak", "Strong Negative"}
    muted = {"Insufficient Data", "Ineligible", "Unavailable", "N/A", "Insufficient"}
    if text in positive:
        return "positive"
    if text in neutral:
        return "neutral"
    if text in negative:
        return "negative"
    if text in muted:
        return "muted"
    return ""


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


def top_opportunity_summary(result: Any) -> dict[str, str] | None:
    ranking = getattr(result, "ranking_result", None)
    top_symbol = getattr(ranking, "top_symbol", None)
    if top_symbol is None:
        return None
    entry = get_ranking_entry(result, top_symbol)
    if entry is None or not getattr(entry, "eligible", False):
        return None
    return {
        "Symbol": format_text(getattr(entry, "symbol", None)),
        "Current Price": format_price(getattr(entry, "current_price", None)),
        "Base Intrinsic Value": format_price(getattr(entry, "base_value", None)),
        "Current vs Base Intrinsic Value %": format_percent(
            getattr(entry, "current_vs_base_pct", None), signed=True
        ),
        "Recommendation V2": format_text(getattr(entry, "recommendation_v2", None)),
        "Ranking Category": format_text(getattr(entry, "category", None)),
        "Ranking Score": format_number(getattr(entry, "normalized_score", None)),
        "Current RSI": format_number(getattr(entry, "current_rsi", None)),
        "RSI50 Reference Price": format_price(getattr(entry, "rsi_reference_price", None)),
        "Current vs RSI50 Reference %": format_percent(
            getattr(entry, "current_vs_rsi_reference_pct", None), signed=True
        ),
        "Evidence Quality": format_text(getattr(entry, "evidence_quality", None)),
    }


def build_chart_dataframe(result: Any, symbol: str) -> pd.DataFrame:
    entry = get_ranking_entry(result, symbol)
    analysis = get_successful_result(result, symbol)
    recommendation = getattr(analysis, "recommendation_v2", None)
    rows = [
        ("Current Price", getattr(entry, "current_price", None), "Market Price"),
        ("Conservative Intrinsic Value", getattr(recommendation, "conservative_value", None), "Intrinsic"),
        ("Base Intrinsic Value", getattr(entry, "base_value", None), "Intrinsic"),
        ("Optimistic Intrinsic Value", getattr(recommendation, "optimistic_intrinsic_value", None), "Intrinsic"),
        ("Analyst Market Expectation", getattr(recommendation, "analyst_expectation", None), "Market Expectation"),
        ("RSI50 Momentum Reference", getattr(entry, "rsi_reference_price", None), "Technical Reference"),
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
        "Current vs Reference Amount": format_price(getattr(entry, "current_vs_rsi_reference_amount", None), signed=True),
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


def successful_symbols(result: Any) -> tuple[str, ...]:
    symbols = []
    for item in tuple(getattr(result, "successful_results", ()) or ()):
        symbol = getattr(getattr(item, "company", None), "symbol", None)
        if symbol:
            symbols.append(symbol)
    return tuple(symbols)


def default_selected_symbol(result: Any) -> str | None:
    top_symbol = getattr(getattr(result, "ranking_result", None), "top_symbol", None)
    if top_symbol in successful_symbols(result):
        return top_symbol
    symbols = successful_symbols(result)
    return symbols[0] if symbols else None


def overview_rows(entry: Any, analysis: Any) -> dict[str, str]:
    company = getattr(analysis, "company", None)
    return {
        "Symbol": format_text(getattr(entry, "symbol", getattr(company, "symbol", None))),
        "Company Name": format_text(getattr(company, "company_name", None)),
        "Current Price": format_price(getattr(entry, "current_price", None), getattr(company, "currency", None)),
        "Ranking Rank": format_text(getattr(entry, "rank", None)),
        "Ranking Score": format_number(getattr(entry, "normalized_score", None)),
        "Ranking Category": format_text(getattr(entry, "category", None)),
        "Eligibility": "Eligible" if getattr(entry, "eligible", False) else "Ineligible",
        "Recommendation V2": format_text(getattr(entry, "recommendation_v2", None)),
        "Evidence Quality": format_text(getattr(entry, "evidence_quality", None)),
        "Base Intrinsic Value": format_price(getattr(entry, "base_value", None)),
        "Current vs Base %": format_percent(getattr(entry, "current_vs_base_pct", None), signed=True),
        "Current RSI": format_number(getattr(entry, "current_rsi", None)),
        "RSI50 Reference Price": format_price(getattr(entry, "rsi_reference_price", None)),
        "Current vs RSI50 %": format_percent(getattr(entry, "current_vs_rsi_reference_pct", None), signed=True),
    }


def overview_interpretation(entry: Any, analysis: Any) -> tuple[str, ...]:
    recommendation = getattr(analysis, "recommendation_v2", None)
    return tuple(
        line
        for line in (
            f"{format_text(getattr(entry, 'symbol', None))} is ranked {format_text(getattr(entry, 'rank', None))} in the current comparison set.",
            f"Recommendation V2 is {format_text(getattr(recommendation, 'decision', None))}; this dashboard does not override that decision.",
            f"Current price is {format_percent(getattr(entry, 'current_vs_base_pct', None), signed=True)} versus base intrinsic value.",
        )
        if "N/A" not in line
    )


def valuation_models_dataframe(analysis: Any) -> pd.DataFrame:
    collection = getattr(analysis, "valuation_snapshots", None)
    agreement = getattr(analysis, "agreement_result", None)
    outliers = {
        _plain(getattr(outlier, "model_type", None)): outlier
        for outlier in tuple(getattr(agreement, "model_outliers", ()) or ())
    }
    rows = []
    for snapshot in tuple(getattr(collection, "snapshots", ()) or ()):
        value_type = _plain(snapshot.value_type)
        outlier = outliers.get(_plain(snapshot.model_type))
        notes = _valuation_notes(snapshot, outlier)
        rows.append(
            {
                "Model": format_text(snapshot.model_type),
                "Value": format_price(snapshot.selected_fair_value, snapshot.currency),
                "Status": format_text(snapshot.status),
                "Confidence": format_text(snapshot.confidence),
                "Value Type": format_text(snapshot.value_type),
                "Included in Intrinsic Range": _intrinsic_inclusion_label(value_type),
                "Notes": notes,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Model",
            "Value",
            "Status",
            "Confidence",
            "Value Type",
            "Included in Intrinsic Range",
            "Notes",
        ],
    )


def model_evidence_rows(analysis: Any, required_minimum: int | None = None) -> dict[str, str]:
    recommendation = getattr(analysis, "recommendation_v2", None)
    agreement = getattr(analysis, "agreement_result", None)
    cluster = getattr(agreement, "intrinsic_cluster", None)
    return {
        "Intrinsic Model Count": format_text(getattr(recommendation, "intrinsic_model_count", None)),
        "Required Minimum Model Count": format_text(required_minimum),
        "Agreement Classification": format_text(getattr(agreement, "core_intrinsic_agreement", None)),
        "Intrinsic Median": format_price(getattr(cluster, "median_value", None)),
        "Intrinsic Spread": format_percent(getattr(cluster, "spread_percentage", None)),
        "Snapshot Statuses": _snapshot_status_summary(analysis),
        "Snapshot Confidence": _snapshot_confidence_summary(analysis),
    }


def pairwise_agreement_dataframe(analysis: Any) -> pd.DataFrame:
    agreement = getattr(analysis, "agreement_result", None)
    rows = []
    for comparison in tuple(getattr(agreement, "pairwise_comparisons", ()) or ()):
        rows.append(
            {
                "Model A": format_text(getattr(comparison, "model_a", None)),
                "Model B": format_text(getattr(comparison, "model_b", None)),
                "Difference": format_price(getattr(comparison, "absolute_difference", None)),
                "Difference %": format_percent(getattr(comparison, "percentage_difference", None)),
                "Relationship": format_text(getattr(comparison, "relationship", None)),
            }
        )
    return pd.DataFrame(rows)


def outliers_dataframe(analysis: Any) -> pd.DataFrame:
    agreement = getattr(analysis, "agreement_result", None)
    rows = []
    for outlier in tuple(getattr(agreement, "model_outliers", ()) or ()):
        rows.append(
            {
                "Model": format_text(getattr(outlier, "model_type", None)),
                "Value": format_price(getattr(outlier, "value", None)),
                "Comparison Median": format_price(getattr(outlier, "comparison_median", None)),
                "Difference %": format_percent(getattr(outlier, "difference_percentage", None)),
                "Status": format_text(getattr(outlier, "status", None)),
            }
        )
    return pd.DataFrame(rows)


def collect_warnings(result: Any, entry: Any, analysis: Any) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(str(item) for item in getattr(entry, "warnings", ()) or ())
    recommendation = getattr(analysis, "recommendation_v2", None)
    values.extend(str(item) for item in getattr(recommendation, "warnings", ()) or ())
    for source_name in ("fair_value_range", "agreement_result", "momentum_reference"):
        source = getattr(analysis, source_name, None)
        values.extend(str(item) for item in getattr(source, "warnings", ()) or ())
    collection = getattr(analysis, "valuation_snapshots", None)
    for snapshot in tuple(getattr(collection, "snapshots", ()) or ()):
        values.extend(str(item) for item in getattr(snapshot, "warnings", ()) or ())
    if entry is not None and not getattr(entry, "eligible", False):
        values.append("Ranking status is ineligible.")
    legacy = getattr(recommendation, "legacy_recommendation", None)
    alignment = _plain(getattr(recommendation, "alignment", None))
    if legacy is not None and alignment in {"V2_MORE_BULLISH", "V2_MORE_BEARISH"}:
        values.append("Legacy recommendation and Recommendation V2 diverge.")
    for failure in tuple(getattr(result, "failures", ()) or ()):
        values.append(f"{failure.symbol}: {failure.error_type}: {failure.message}")
    return tuple(dict.fromkeys(value for value in values if value))


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
        return display_label(value.value)
    text = str(value).strip()
    return display_label(text) if text else "N/A"


def display_label(value: Any) -> str:
    text = _plain(value)
    if not text:
        return "N/A"
    if text in _DISPLAY_LABELS:
        return _DISPLAY_LABELS[text]
    if "_" in text:
        return text.replace("_", " ").title()
    return text


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
        "RSI50 Reference": format_price(getattr(entry, "rsi_reference_price", None)),
        "Current vs RSI50 %": format_percent(getattr(entry, "current_vs_rsi_reference_pct", None), signed=True),
        "RSI50 Sentiment": format_text(getattr(entry, "momentum_sentiment_position", None)),
    }


def _ranking_entries(result: Any) -> tuple[Any, ...]:
    return tuple(getattr(getattr(result, "ranking_result", None), "entries", ()) or ())


def _plain(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    return "" if value is None else str(value)


def _cell_style(value: Any) -> str:
    emphasis = cell_emphasis(value)
    if emphasis == "positive":
        return "background-color: #eaf6ef; color: #14532d"
    if emphasis == "neutral":
        return "background-color: #f6f4ea; color: #4a3f16"
    if emphasis == "negative":
        return "background-color: #fbeeee; color: #7f1d1d"
    if emphasis == "muted":
        return "background-color: #f1f3f5; color: #495057"
    return ""


def _intrinsic_inclusion_label(value_type: str) -> str:
    if value_type == "INTRINSIC_VALUE":
        return "Yes"
    if value_type == "REFERENCE_VALUE":
        return "Supporting Reference"
    if value_type == "MARKET_EXPECTATION":
        return "No - Market Expectation"
    return "No"


def _valuation_notes(snapshot: Any, outlier: Any) -> str:
    notes = []
    if _plain(getattr(snapshot, "value_type", None)) == "MARKET_EXPECTATION":
        notes.append("Market expectation, not intrinsic value.")
    if _plain(getattr(snapshot, "model_type", None)) == "DCF_REFERENCE":
        notes.append("External reference value.")
    status = _plain(getattr(outlier, "status", None))
    if status and status not in {"NOT_OUTLIER", "NOT_EVALUATED"}:
        notes.append(f"Outlier status: {format_text(status)}.")
    warnings = tuple(getattr(snapshot, "warnings", ()) or ())
    if warnings:
        notes.append(" ".join(str(item) for item in warnings))
    return " ".join(notes) if notes else "N/A"


def _snapshot_status_summary(analysis: Any) -> str:
    collection = getattr(analysis, "valuation_snapshots", None)
    parts = [
        f"{format_text(snapshot.model_type)}: {format_text(snapshot.status)}"
        for snapshot in tuple(getattr(collection, "snapshots", ()) or ())
    ]
    return "; ".join(parts) if parts else "N/A"


def _snapshot_confidence_summary(analysis: Any) -> str:
    collection = getattr(analysis, "valuation_snapshots", None)
    parts = [
        f"{format_text(snapshot.model_type)}: {format_text(snapshot.confidence)}"
        for snapshot in tuple(getattr(collection, "snapshots", ()) or ())
    ]
    return "; ".join(parts) if parts else "N/A"


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
