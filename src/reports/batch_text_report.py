from __future__ import annotations

import csv
import json
from io import StringIO
from enum import Enum
from typing import Any

from src.analysis.ranking_engine import momentum_reference_interpretation
from src.services.batch_analysis import BatchStockAnalysisResult


_LINE = "=" * 60
_SECTION_LINE = "-" * 60
_LABEL_WIDTH = 24
_HEADER = (
    f"{'Symbol':<8} {'Price':>12} {'Fair Value':>12} {'Buy Price':>12} "
    f"{'Sell Price':>12} {'Decision':<10} {'Status':<22}"
)


def format_batch_stock_analysis_report(
    result: BatchStockAnalysisResult,
    show_snapshots: bool = False,
    show_agreement: bool = False,
    show_momentum: bool = False,
    show_range: bool = False,
    show_recommendation_v2: bool = False,
    show_ranking: bool = False,
    show_ranking_details: bool = False,
    ranking_only: bool = False,
    ranking_format: str = "text",
) -> str:
    """Format a deterministic plain-text batch stock analysis report."""
    if ranking_format not in {"text", "csv", "json"}:
        raise ValueError("ranking_format must be text, csv, or json.")
    if ranking_format == "csv":
        return _format_ranking_csv(getattr(result, "ranking_result", None))
    if ranking_format == "json":
        return _format_ranking_json(getattr(result, "ranking_result", None))
    if ranking_only:
        return _format_ranking_text(
            getattr(result, "ranking_result", None),
            show_details=show_ranking_details,
        )
    lines = [
        _LINE,
        "BATCH STOCK VALUATION REPORT",
        _LINE,
        _row("Requested", result.total_count),
        _row("Successful", result.success_count),
        _row("Failed", result.failure_count),
        "",
        "SUMMARY",
        _SECTION_LINE,
        _HEADER,
    ]

    success_by_symbol = {
        item.valuation.symbol: item for item in result.successful_results
    }
    failure_by_symbol = {failure.symbol: failure for failure in result.failures}
    for symbol in result.requested_symbols:
        success = success_by_symbol.get(symbol)
        if success is not None:
            lines.append(_success_row(success))
            continue
        if symbol in failure_by_symbol:
            lines.append(_failure_row(symbol))

    profiled_results = [
        item for item in result.successful_results if getattr(item, "profile", None)
    ]
    if profiled_results:
        lines.extend(["", "RESEARCH COMPARISON", _SECTION_LINE])
        lines.append(
            f"{'Symbol':<8} {'Auto FV':>12} {'Research FV':>12} {'DCF Ref':>12} "
            f"{'Style':<16} {'PEG Adj':<7}"
        )
        for item in profiled_results:
            lines.append(_research_row(item))

    eps_selection_results = [
        item for item in result.successful_results if getattr(item, "eps_selection", None)
    ]
    if eps_selection_results:
        lines.extend(["", "EPS SELECTION", _SECTION_LINE])
        lines.append(
            f"{'Symbol':<8} {'Requested':<18} {'Applied':<18} "
            f"{'Selected EPS':>12} {'Period':<10} {'Status':<14}"
        )
        for item in eps_selection_results:
            lines.append(_eps_selection_row(item))

    industry_policy_results = [
        item for item in result.successful_results if getattr(item, "industry_policy", None)
    ]
    if industry_policy_results:
        lines.extend(["", "INDUSTRY POLICY", _SECTION_LINE])
        lines.append(
            f"{'Symbol':<8} {'Policy':<16} {'Mode':<12} "
            f"{'Original PE':>12} {'Policy PE':>10} {'Style':<16}"
        )
        for item in industry_policy_results:
            lines.append(_industry_policy_row(item))

    analyst_results = [
        item for item in result.successful_results if getattr(item, "analyst_consensus", None)
    ]
    if analyst_results:
        lines.extend(["", "ANALYST CONSENSUS", _SECTION_LINE])
        lines.append(
            f"{'Symbol':<8} {'Mean Target':>12} {'Analyst FV':>12} "
            f"{'Dispersion':>12} {'Confidence':<12} {'Status':<12}"
        )
        for item in analyst_results:
            lines.append(_analyst_row(item))

    if show_snapshots:
        _extend_snapshot_table(lines, result.successful_results)

    if show_agreement:
        _extend_agreement_table(lines, result.successful_results)

    if show_momentum:
        _extend_momentum_table(lines, result.successful_results)

    if show_range:
        _extend_range_table(lines, result.successful_results)

    if show_recommendation_v2:
        _extend_recommendation_v2_table(lines, result.successful_results)

    if show_ranking:
        _extend_ranking_table(
            lines,
            getattr(result, "ranking_result", None),
            show_details=show_ranking_details,
        )

    if result.failures:
        lines.extend(["", "FAILURES", _SECTION_LINE])
        for failure in result.failures:
            lines.append(failure.symbol)
            lines.append(f"{failure.error_type}: {failure.message}")

    lines.extend(["", _LINE])
    return "\n".join(lines)


def _success_row(result: Any) -> str:
    company = result.company
    valuation = result.valuation
    fair_value = valuation.fair_value
    decision = valuation.valuation_decision
    return (
        f"{valuation.symbol:<8} "
        f"{_format_currency(company.current_price, company.currency):>12} "
        f"{_format_currency(_getattr_or_none(fair_value, 'adjusted_fair_value'), company.currency):>12} "
        f"{_format_currency(_getattr_or_none(decision, 'buy_price'), company.currency):>12} "
        f"{_format_currency(_getattr_or_none(decision, 'sell_price'), company.currency):>12} "
        f"{_format_optional_text(_getattr_or_none(decision, 'recommendation')):<10} "
        f"{_format_optional_text(valuation.status):<22}"
    )


def _failure_row(symbol: str) -> str:
    return (
        f"{symbol:<8} {'N/A':>12} {'N/A':>12} {'N/A':>12} "
        f"{'N/A':>12} {'N/A':<10} {'ERROR':<22}"
    )


def _research_row(result: Any) -> str:
    profile = result.profile
    comparison = result.valuation_comparison
    company = result.company
    return (
        f"{profile.symbol:<8} "
        f"{_format_currency(_getattr_or_none(comparison, 'automatic_fair_value'), company.currency):>12} "
        f"{_format_currency(_getattr_or_none(comparison, 'research_fair_value'), company.currency):>12} "
        f"{_format_currency(_getattr_or_none(comparison, 'dcf_fair_value'), company.currency):>12} "
        f"{_format_optional_text(profile.valuation_style):<16} "
        f"{_format_yes_no(profile.use_peg_adjustment):<7}"
    )


def _eps_selection_row(result: Any) -> str:
    selection = result.eps_selection
    return (
        f"{selection.symbol:<8} "
        f"{_format_optional_text(selection.requested_method):<18} "
        f"{_format_optional_text(selection.applied_method):<18} "
        f"{_format_number(selection.selected_eps):>12} "
        f"{_format_optional_text(selection.selected_period_label):<10} "
        f"{_format_optional_text(selection.status):<14}"
    )


def _industry_policy_row(result: Any) -> str:
    policy = result.industry_policy
    return (
        f"{policy.symbol:<8} "
        f"{_format_optional_text(policy.policy_name):<16} "
        f"{_format_optional_text(policy.target_pe_mode):<12} "
        f"{_format_number(policy.original_target_pe):>12} "
        f"{_format_number(policy.policy_target_pe):>10} "
        f"{_format_optional_text(policy.valuation_style):<16}"
    )


def _analyst_row(result: Any) -> str:
    analyst = result.analyst_consensus
    metrics = getattr(analyst, "metrics", {})
    return (
        f"{analyst.symbol:<8} "
        f"{_format_number(_mapping_get(metrics, 'target_mean')):>12} "
        f"{_format_number(analyst.selected_fair_value):>12} "
        f"{_format_percent(_mapping_get(metrics, 'dispersion_percent')):>12} "
        f"{_format_optional_text(analyst.confidence):<12} "
        f"{_format_optional_text(analyst.status):<12}"
    )


def _extend_snapshot_table(lines: list[str], results: tuple[Any, ...]) -> None:
    rows = []
    for result in results:
        collection = getattr(result, "valuation_snapshots", None)
        for snapshot in getattr(collection, "snapshots", ()) or ():
            rows.append((result, snapshot))

    lines.extend(["", "VALUATION SNAPSHOTS", _SECTION_LINE])
    lines.append(
        f"{'Symbol':<8} {'Model':<18} {'Selected Value':>16} "
        f"{'Status':<10} {'Confidence':<12}"
    )
    for result, snapshot in rows:
        currency = snapshot.currency or getattr(result.company, "currency", None)
        lines.append(
            f"{snapshot.symbol:<8} "
            f"{_format_optional_text(snapshot.model_type):<18} "
            f"{_format_currency(snapshot.selected_fair_value, currency):>16} "
            f"{_format_optional_text(snapshot.status):<10} "
            f"{_format_optional_text(snapshot.confidence):<12}"
        )


def _extend_agreement_table(lines: list[str], results: tuple[Any, ...]) -> None:
    rows = [
        (result, getattr(result, "agreement_result", None))
        for result in results
        if getattr(result, "agreement_result", None) is not None
    ]
    lines.extend(["", "MODEL AGREEMENT ANALYSIS", _SECTION_LINE])
    if not rows:
        lines.append("No agreement analysis available.")
        return
    lines.append(
        f"{'Symbol':<8} {'Core':<12} {'Extended':<12} {'Overall':<12} "
        f"{'Median':>12} {'Analyst Outlier':<18}"
    )
    for result, agreement in rows:
        cluster = agreement.intrinsic_cluster
        lines.append(
            f"{result.valuation.symbol:<8} "
            f"{_format_optional_text(agreement.core_intrinsic_agreement):<12} "
            f"{_format_optional_text(agreement.extended_intrinsic_agreement):<12} "
            f"{_format_optional_text(agreement.overall_agreement):<12} "
            f"{_format_currency(cluster.median_value, result.company.currency):>12} "
            f"{_first_market_outlier_status(agreement):<18}"
        )


def _first_market_outlier_status(agreement: Any) -> str:
    analyses = tuple(getattr(agreement, "market_expectation_analyses", ()) or ())
    if not analyses:
        return "N/A"
    return _format_optional_text(analyses[0].outlier_status)


def _extend_momentum_table(lines: list[str], results: tuple[Any, ...]) -> None:
    rows = [(result, getattr(result, "momentum_reference", None)) for result in results if getattr(result, "momentum_reference", None)]
    lines.extend(["", "MARKET MOMENTUM REFERENCE", _SECTION_LINE])
    if not rows:
        lines.append("No market momentum references available.")
        return
    lines.append(f"{'Symbol':<8} {'Current RSI':>12} {'Reference':>12} {'Direction':<14} {'Change':>10}")
    for result, momentum in rows:
        lines.append(
            f"{result.valuation.symbol:<8} "
            f"{_format_number(momentum.current_rsi):>12} "
            f"{_format_currency(momentum.reference_price, result.company.currency):>12} "
            f"{_format_optional_text(momentum.cross_direction):<14} "
            f"{_format_signed_percent(momentum.price_change_since_reference_pct):>10}"
        )


def _extend_range_table(lines: list[str], results: tuple[Any, ...]) -> None:
    rows = [(result, getattr(result, "fair_value_range", None)) for result in results if getattr(result, "fair_value_range", None)]
    lines.extend(["", "FAIR VALUE RANGE", _SECTION_LINE])
    if not rows:
        lines.append("No fair value ranges available.")
        return
    lines.append(
        f"{'Symbol':<8} {'Conservative':>12} {'Base':>12} {'Optimistic':>12} "
        f"{'Position':<26}"
    )
    for result, fair_range in rows:
        lines.append(
            f"{result.valuation.symbol:<8} "
            f"{_format_currency(fair_range.conservative_value, result.company.currency):>12} "
            f"{_format_currency(fair_range.base_value, result.company.currency):>12} "
            f"{_format_currency(fair_range.optimistic_intrinsic_value, result.company.currency):>12} "
            f"{_format_optional_text(fair_range.market_position):<26}"
        )


def _extend_recommendation_v2_table(lines: list[str], results: tuple[Any, ...]) -> None:
    rows = [(result, getattr(result, "recommendation_v2", None)) for result in results if getattr(result, "recommendation_v2", None)]
    lines.extend(["", "RECOMMENDATION V2", _SECTION_LINE])
    if not rows:
        lines.append("No Recommendation V2 results available.")
        return
    lines.append(
        f"{'Symbol':<8} {'Decision':<18} {'Valuation':<26} "
        f"{'Evidence':<12} {'Momentum':<16} {'Alignment':<16}"
    )
    for result, recommendation in rows:
        lines.append(
            f"{result.valuation.symbol:<8} "
            f"{_format_optional_text(recommendation.decision):<18} "
            f"{_format_optional_text(recommendation.valuation_condition):<26} "
            f"{_format_optional_text(recommendation.evidence_quality):<12} "
            f"{_format_optional_text(recommendation.momentum_condition):<16} "
            f"{_format_optional_text(recommendation.alignment):<16}"
        )


def _format_ranking_text(ranking: Any, show_details: bool = False) -> str:
    lines: list[str] = []
    _extend_ranking_table(lines, ranking, show_details=show_details)
    return "\n".join(lines)


def _extend_ranking_table(lines: list[str], ranking: Any, show_details: bool = False) -> None:
    lines.extend(["", "MULTI STOCK RANKING", _SECTION_LINE])
    if ranking is None:
        lines.append("No multi-stock ranking available.")
        return
    lines.append(_row("Status", getattr(ranking, "status", None)))
    lines.append(_row("Top Symbol", getattr(ranking, "top_symbol", None)))
    lines.append(_row("Top Score", _format_number(getattr(ranking, "top_score", None))))
    entries = tuple(getattr(ranking, "entries", ()) or ())
    _extend_ranking_momentum_summary(lines, entries)
    lines.append("")
    lines.append(
        f"{'Rank':>4} {'Symbol':<8} {'Score':>8} {'Category':<18} {'Eligibility':<10} "
        f"{'Rec V2':<18} {'Valuation':<26} {'Current':>12} {'RSI':>7} "
        f"{'RSI50 Ref':>12} {'vs RSI50':>10} {'Sentiment':<12}"
    )
    if not entries:
        lines.append("No ranked entries available.")
        return
    for entry in entries:
        lines.append(
            f"{entry.rank:>4} "
            f"{entry.symbol:<8} "
            f"{_format_number(entry.normalized_score):>8} "
            f"{_format_optional_text(entry.category):<18} "
            f"{_format_eligibility(entry):<10} "
            f"{_format_optional_text(entry.recommendation_v2):<18} "
            f"{_format_optional_text(entry.valuation_condition):<26} "
            f"{_format_number(entry.current_price):>12} "
            f"{_format_number(entry.current_rsi):>7} "
            f"{_format_number(entry.rsi_reference_price):>12} "
            f"{_format_signed_percent(entry.current_vs_rsi_reference_pct):>10} "
            f"{_format_sentiment_short(entry.momentum_sentiment_position):<12}"
        )
    _extend_rsi50_reference_table(lines, entries, getattr(ranking, "failed_symbols", ()) or ())
    if show_details:
        lines.extend(["", "RANKING DETAILS", _SECTION_LINE])
        for entry in entries:
            lines.append(f"{entry.rank}. {entry.symbol}")
            lines.append(_row("Valuation Score", _format_number(entry.valuation_score)))
            lines.append(_row("Recommendation Score", _format_number(entry.recommendation_score)))
            lines.append(_row("Agreement Score", _format_number(entry.agreement_score)))
            lines.append(_row("Evidence Score", _format_number(entry.evidence_score)))
            lines.append(_row("Momentum Score", _format_number(entry.momentum_score)))
            lines.append(_row("Penalty", _format_number(entry.penalty)))
            lines.extend(["", "RSI 50 MOMENTUM REFERENCE", _SECTION_LINE])
            lines.append(_row("Current Price", _format_number(entry.current_price)))
            lines.append(_row("Current RSI", _format_number(entry.current_rsi)))
            lines.append(_row("Reference Date", _format_date(entry.rsi_reference_date)))
            lines.append(_row("RSI at Reference", _format_number(entry.rsi_reference_rsi)))
            lines.append(_row("RSI 50 Reference Price", _format_number(entry.rsi_reference_price)))
            lines.append(_row("Reference Direction", entry.rsi_cross_direction))
            lines.append(_row("Current vs Reference", _format_number(entry.current_vs_rsi_reference_amount)))
            lines.append(_row("Current vs Reference", _format_signed_percent(entry.current_vs_rsi_reference_pct)))
            lines.append(_row("Trading Days Since Reference", entry.momentum_reference_trading_days))
            lines.append(_row("Sentiment Position", entry.momentum_sentiment_position))
            lines.append(_row("Reference Status", entry.momentum_reference_status))
            lines.append(_row("Price Field", entry.momentum_reference_price_field))
            lines.extend(["", "INTERPRETATION", _SECTION_LINE])
            for line in momentum_reference_interpretation(entry):
                lines.append(line)
            for line in entry.rationale:
                lines.append(f"- {line}")
            for warning in entry.warnings:
                lines.append(f"Warning: {warning}")


def _extend_ranking_momentum_summary(lines: list[str], entries: tuple[Any, ...]) -> None:
    usable = [
        entry
        for entry in entries
        if _format_sentiment_short(getattr(entry, "momentum_sentiment_position", None)) != "N/A"
    ]
    above = sum(1 for entry in usable if "ABOVE" in _format_sentiment_short(entry.momentum_sentiment_position))
    near = sum(1 for entry in usable if _format_sentiment_short(entry.momentum_sentiment_position) == "NEAR")
    below = sum(1 for entry in usable if "BELOW" in _format_sentiment_short(entry.momentum_sentiment_position))
    lines.append(_row("Symbols Above RSI50 Reference", above))
    lines.append(_row("Symbols Near RSI50 Reference", near))
    lines.append(_row("Symbols Below RSI50 Reference", below))
    lines.append(_row("Symbols Without RSI50 Reference", len(entries) - len(usable)))
    above_entries = [
        entry
        for entry in usable
        if getattr(entry, "current_vs_rsi_reference_pct", None) is not None
        and entry.current_vs_rsi_reference_pct > 0
    ]
    below_entries = [
        entry
        for entry in usable
        if getattr(entry, "current_vs_rsi_reference_pct", None) is not None
        and entry.current_vs_rsi_reference_pct < 0
    ]
    if above_entries:
        strongest = max(above_entries, key=lambda entry: entry.current_vs_rsi_reference_pct)
        lines.append(_row("Strongest Above Reference", f"{strongest.symbol} / {_format_signed_percent(strongest.current_vs_rsi_reference_pct)}"))
    if below_entries:
        weakest = min(below_entries, key=lambda entry: entry.current_vs_rsi_reference_pct)
        lines.append(_row("Weakest Below Reference", f"{weakest.symbol} / {_format_signed_percent(weakest.current_vs_rsi_reference_pct)}"))


def _extend_rsi50_reference_table(lines: list[str], entries: tuple[Any, ...], failed_symbols: tuple[str, ...]) -> None:
    lines.extend(["", "RSI 50 MOMENTUM REFERENCE", _SECTION_LINE])
    lines.append(
        f"{'Symbol':<8} {'Current Price':>13} {'Current RSI':>11} {'Ref Date':<10} "
        f"{'RSI50 Price':>12} {'Ref RSI':>8} {'Direction':<14} {'vs Ref':>10} "
        f"{'Sentiment':<12} {'Status':<18}"
    )
    symbols = set()
    for entry in entries:
        symbols.add(entry.symbol)
        lines.append(
            f"{entry.symbol:<8} "
            f"{_format_number(entry.current_price):>13} "
            f"{_format_number(entry.current_rsi):>11} "
            f"{_format_date(entry.rsi_reference_date):<10} "
            f"{_format_number(entry.rsi_reference_price):>12} "
            f"{_format_number(entry.rsi_reference_rsi):>8} "
            f"{_format_optional_text(entry.rsi_cross_direction):<14} "
            f"{_format_signed_percent(entry.current_vs_rsi_reference_pct):>10} "
            f"{_format_sentiment_short(entry.momentum_sentiment_position):<12} "
            f"{_format_optional_text(entry.momentum_reference_status):<18}"
        )
    for symbol in failed_symbols:
        if symbol not in symbols:
            lines.append(
                f"{symbol:<8} {'N/A':>13} {'N/A':>11} {'N/A':<10} {'N/A':>12} "
                f"{'N/A':>8} {'N/A':<14} {'N/A':>10} {'N/A':<12} {'ERROR':<18}"
            )


def _format_ranking_csv(ranking: Any) -> str:
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "rank",
            "symbol",
            "score",
            "category",
            "eligibility",
            "recommendation_v2",
            "valuation_condition",
            "evidence_quality",
            "agreement",
            "momentum",
            "current_price",
            "base_value",
            "current_vs_base_pct",
            "current_rsi",
            "rsi_reference_date",
            "rsi_reference_price",
            "rsi_reference_rsi",
            "rsi_cross_direction",
            "current_vs_rsi_reference_amount",
            "current_vs_rsi_reference_pct",
            "momentum_sentiment_position",
            "momentum_reference_status",
            "momentum_reference_price_field",
            "momentum_reference_trading_days",
            "penalty",
        ]
    )
    for entry in tuple(getattr(ranking, "entries", ()) or ()):
        writer.writerow(
            [
                entry.rank,
                entry.symbol,
                _plain(entry.normalized_score),
                _plain(entry.category),
                _format_eligibility(entry),
                _plain(entry.recommendation_v2),
                _plain(entry.valuation_condition),
                _plain(entry.evidence_quality),
                _plain(entry.agreement),
                _plain(entry.momentum),
                _plain(entry.current_price),
                _plain(entry.base_value),
                _plain(entry.current_vs_base_pct),
                _plain(entry.current_rsi),
                _format_date(entry.rsi_reference_date, empty=""),
                _plain(entry.rsi_reference_price),
                _plain(entry.rsi_reference_rsi),
                _plain(entry.rsi_cross_direction),
                _plain(entry.current_vs_rsi_reference_amount),
                _plain(entry.current_vs_rsi_reference_pct),
                _plain(entry.momentum_sentiment_position),
                _plain(entry.momentum_reference_status),
                _plain(entry.momentum_reference_price_field),
                _plain(entry.momentum_reference_trading_days),
                _plain(entry.penalty),
            ]
        )
    return output.getvalue().rstrip("\n")


def _format_ranking_json(ranking: Any) -> str:
    payload = {
        "status": _plain(getattr(ranking, "status", None)),
        "top_symbol": getattr(ranking, "top_symbol", None),
        "top_score": getattr(ranking, "top_score", None),
        "successful_symbols": list(getattr(ranking, "successful_symbols", ()) or ()),
        "failed_symbols": list(getattr(ranking, "failed_symbols", ()) or ()),
        "entries": [_entry_payload(entry) for entry in tuple(getattr(ranking, "entries", ()) or ())],
    }
    return json.dumps(payload, sort_keys=True, indent=2)


def _entry_payload(entry: Any) -> dict[str, Any]:
    return {
        "rank": entry.rank,
        "symbol": entry.symbol,
        "company_name": entry.company_name,
        "total_score": entry.total_score,
        "normalized_score": entry.normalized_score,
        "category": _plain(entry.category),
        "eligibility": _format_eligibility(entry),
        "recommendation_v2": _plain(entry.recommendation_v2),
        "valuation_condition": _plain(entry.valuation_condition),
        "evidence_quality": _plain(entry.evidence_quality),
        "agreement": _plain(entry.agreement),
        "momentum": _plain(entry.momentum),
        "current_price": entry.current_price,
        "base_value": entry.base_value,
        "current_vs_base_pct": entry.current_vs_base_pct,
        "current_rsi": entry.current_rsi,
        "current_vs_rsi_reference_pct": entry.current_vs_rsi_reference_pct,
        "momentum_reference": {
            "current_rsi": entry.current_rsi,
            "reference_date": _format_date(entry.rsi_reference_date, empty=None),
            "reference_price": entry.rsi_reference_price,
            "reference_rsi": entry.rsi_reference_rsi,
            "cross_direction": _plain(entry.rsi_cross_direction),
            "current_vs_reference_amount": entry.current_vs_rsi_reference_amount,
            "current_vs_reference_pct": entry.current_vs_rsi_reference_pct,
            "sentiment_position": _plain(entry.momentum_sentiment_position),
            "status": _plain(entry.momentum_reference_status),
            "price_field": _plain(entry.momentum_reference_price_field),
            "trading_days_since": entry.momentum_reference_trading_days,
        },
        "valuation_score": entry.valuation_score,
        "recommendation_score": entry.recommendation_score,
        "agreement_score": entry.agreement_score,
        "evidence_score": entry.evidence_score,
        "momentum_score": entry.momentum_score,
        "penalty": entry.penalty,
        "warnings": list(entry.warnings),
        "rationale": list(entry.rationale),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _format_eligibility(entry: Any) -> str:
    return "ELIGIBLE" if getattr(entry, "eligible", False) else "INELIGIBLE"


def _format_date(value: Any, empty: Any = "N/A") -> Any:
    if value is None:
        return empty
    return value.isoformat()


def _format_sentiment_short(value: Any) -> str:
    text = _format_optional_text(value)
    return {
        "WELL_ABOVE_NEUTRAL_REFERENCE": "WELL_ABOVE",
        "ABOVE_NEUTRAL_REFERENCE": "ABOVE",
        "NEAR_NEUTRAL_REFERENCE": "NEAR",
        "BELOW_NEUTRAL_REFERENCE": "BELOW",
        "WELL_BELOW_NEUTRAL_REFERENCE": "WELL_BELOW",
        "UNAVAILABLE": "N/A",
    }.get(text, text)


def _row(label: str, value: Any) -> str:
    return f"{label:<{_LABEL_WIDTH}}: {_format_optional_text(value)}"


def _mapping_get(mapping: Any, key: str) -> Any:
    if mapping is None:
        return None
    return mapping.get(key)


def _format_currency(value: Any, currency: str | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f} {_format_optional_text(currency)}"


def _format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _format_signed_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _format_optional_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value).strip()
    return text or "N/A"


def _format_yes_no(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "YES" if value else "NO"


def _getattr_or_none(value: Any, attribute_name: str) -> Any:
    if value is None:
        return None
    return getattr(value, attribute_name)
