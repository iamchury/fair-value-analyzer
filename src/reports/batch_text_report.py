from __future__ import annotations

from enum import Enum
from typing import Any

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
) -> str:
    """Format a deterministic plain-text batch stock analysis report."""
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
            f"{'Dispersion':>12} {'Quality':<12} {'Status':<12}"
        )
        for item in analyst_results:
            lines.append(_analyst_row(item))

    if show_snapshots:
        _extend_snapshot_table(lines, result.successful_results)

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
    return (
        f"{analyst.symbol:<8} "
        f"{_format_number(analyst.target_mean):>12} "
        f"{_format_number(analyst.adjusted_analyst_fair_value):>12} "
        f"{_format_percent(analyst.dispersion_percent):>12} "
        f"{_format_optional_text(analyst.consensus_quality):<12} "
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


def _row(label: str, value: Any) -> str:
    return f"{label:<{_LABEL_WIDTH}}: {_format_optional_text(value)}"


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
