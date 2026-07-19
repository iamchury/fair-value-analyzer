from __future__ import annotations

from enum import Enum
from typing import Any

import pandas as pd
import streamlit as streamlit_module

from src.services.batch_analysis import analyze_symbol_list_with_profiles_from_config_files
from src.web.presentation import (
    DEFAULT_SYMBOL_TEXT,
    DEFAULT_WEB_CONFIG,
    WebConfigPaths,
    build_chart_dataframe,
    build_ranking_dataframe,
    filter_ranking_dataframe,
    format_number,
    format_percent,
    format_price,
    format_text,
    get_ranking_entry,
    get_successful_result,
    parse_ticker_symbols,
    ranking_csv_download,
    ranking_json_download,
    ranking_summary,
    rsi_reference_details,
    rsi_reference_interpretation,
)


def analyze_symbols(
    symbols: tuple[str, ...],
    config: WebConfigPaths = DEFAULT_WEB_CONFIG,
) -> Any:
    return analyze_symbol_list_with_profiles_from_config_files(
        symbols,
        valuation_config_path=config.valuation_config_path,
        profiles_path=config.profiles_path,
        eps_selection_path=config.eps_selection_path,
        industry_policies_path=config.industry_policies_path,
        analyst_consensus_path=config.analyst_consensus_path,
        agreement_config_path=config.agreement_config_path,
        momentum_config_path=config.momentum_config_path,
        range_config_path=config.range_config_path,
        recommendation_v2_config_path=config.recommendation_v2_config_path,
        ranking_config_path=config.ranking_config_path,
    )


@streamlit_module.cache_data(ttl=900, show_spinner=False)
def cached_analyze_symbols(symbols: tuple[str, ...]) -> Any:
    return analyze_symbols(symbols)


def run() -> None:
    st = streamlit_module

    st.set_page_config(page_title="Fair Value Analyzer", layout="wide")
    st.title("Fair Value Analyzer")
    st.caption("Valuation, Recommendation V2, ranking, and RSI 50 momentum reference dashboard.")

    with st.sidebar:
        st.header("Analysis")
        raw_symbols = st.text_area("Tickers", value=DEFAULT_SYMBOL_TEXT, height=130)
        analyze = st.button("Analyze", type="primary", use_container_width=True)
        st.caption("Maximum 20 tickers. Input accepts commas, spaces, or new lines.")

    if analyze:
        _run_analysis(st, raw_symbols)

    result = st.session_state.get("latest_result")
    if result is None:
        st.info("Enter tickers and click Analyze.")
        _disclaimer(st)
        return

    _render_dashboard(st, result)
    _disclaimer(st)


def _run_analysis(st: Any, raw_symbols: str) -> None:
    try:
        symbols = parse_ticker_symbols(raw_symbols)
    except ValueError as exc:
        st.sidebar.error(str(exc))
        return
    progress = st.progress(0, text="Loading configuration")
    try:
        progress.progress(20, text="Downloading Yahoo and Treasury data")
        result = cached_analyze_symbols(symbols)
        progress.progress(75, text="Building ranking and RSI 50 reference views")
        st.session_state["latest_result"] = result
        st.session_state["latest_symbols"] = symbols
        progress.progress(100, text="Analysis complete")
    except Exception as exc:
        st.error("Analysis failed. Expand technical details for more information.")
        with st.expander("Technical details"):
            st.exception(exc)
    finally:
        progress.empty()


def _render_dashboard(st: Any, result: Any) -> None:
    _summary_metrics(st, result)
    _failure_expander(st, result)
    table = build_ranking_dataframe(result)
    filtered = _filters(st, table)
    st.subheader("Multi-Stock Ranking")
    st.dataframe(filtered, hide_index=True, use_container_width=True)
    _downloads(st, result)
    symbols = [row["Symbol"] for row in table.to_dict("records")]
    if not symbols:
        st.warning("No ranked symbols are available.")
        return
    selected = st.selectbox("Selected Symbol", symbols)
    entry = get_ranking_entry(result, selected)
    analysis = get_successful_result(result, selected)
    _valuation_chart(st, result, selected)
    if entry is not None:
        _rsi_section(st, entry)
    _detail_tabs(st, entry, analysis)


def _summary_metrics(st: Any, result: Any) -> None:
    summary = ranking_summary(result)
    cells = st.columns(6)
    cells[0].metric("Top Eligible Symbol", format_text(summary["top_symbol"]))
    cells[1].metric("Top Score", format_number(summary["top_score"]))
    cells[2].metric("Eligible Symbols", summary["eligible_count"])
    cells[3].metric("Insufficient Symbols", summary["insufficient_count"])
    cells[4].metric("Above/Near/Below RSI50", f"{summary['above_rsi50']} / {summary['near_rsi50']} / {summary['below_rsi50']}")
    cells[5].metric("Successful / Failed", f"{result.success_count} / {result.failure_count}")


def _filters(st: Any, dataframe: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Display Filters")
    columns = st.columns(4)
    eligibility = _select_filter(columns[0], "Eligibility", dataframe)
    category = _select_filter(columns[1], "Category", dataframe)
    recommendation = _select_filter(columns[2], "Recommendation V2", dataframe)
    sentiment = _select_filter(columns[3], "RSI50 Sentiment", dataframe)
    return filter_ranking_dataframe(dataframe, eligibility, category, recommendation, sentiment)


def _select_filter(container: Any, column: str, dataframe: pd.DataFrame) -> str:
    values = sorted(value for value in dataframe[column].dropna().unique() if value != "N/A")
    return container.selectbox(column, ["All", *values])


def _downloads(st: Any, result: Any) -> None:
    left, right = st.columns(2)
    left.download_button(
        "Download Ranking CSV",
        ranking_csv_download(result),
        file_name="ranking.csv",
        mime="text/csv",
        use_container_width=True,
    )
    right.download_button(
        "Download Ranking JSON",
        ranking_json_download(result),
        file_name="ranking.json",
        mime="application/json",
        use_container_width=True,
    )


def _valuation_chart(st: Any, result: Any, symbol: str) -> None:
    st.subheader("Selected Symbol Value Comparison")
    chart = build_chart_dataframe(result, symbol)
    if chart.empty:
        st.info("No comparable values are available for this symbol.")
        return
    st.bar_chart(chart.set_index("Measure")["Value"])
    st.dataframe(chart, hide_index=True, use_container_width=True)


def _rsi_section(st: Any, entry: Any) -> None:
    st.subheader("RSI 50 Momentum Reference")
    st.caption(
        "Technical momentum and sentiment benchmark only; not intrinsic value or investor cost basis."
    )
    details = rsi_reference_details(entry)
    cols = st.columns(4)
    for index, (label, value) in enumerate(details.items()):
        cols[index % 4].metric(label, value)
    for line in rsi_reference_interpretation(entry):
        st.write(line)


def _detail_tabs(st: Any, entry: Any, analysis: Any) -> None:
    overview, valuation, recommendation, rsi, evidence, warnings = st.tabs(
        ["Overview", "Valuation", "Recommendation", "RSI50 Momentum", "Model Evidence", "Warnings"]
    )
    with overview:
        _overview_tab(st, entry, analysis)
    with valuation:
        _valuation_tab(st, analysis)
    with recommendation:
        _recommendation_tab(st, analysis)
    with rsi:
        if entry is None:
            st.info("No RSI 50 reference is available.")
        else:
            st.table(pd.DataFrame(rsi_reference_details(entry).items(), columns=["Field", "Value"]))
    with evidence:
        _evidence_tab(st, analysis)
    with warnings:
        _warnings_tab(st, entry, analysis)


def _overview_tab(st: Any, entry: Any, analysis: Any) -> None:
    company = getattr(analysis, "company", None)
    recommendation = getattr(analysis, "recommendation_v2", None)
    rows = {
        "Symbol": format_text(getattr(entry, "symbol", None)),
        "Company": format_text(getattr(company, "company_name", None)),
        "Current Price": format_price(getattr(entry, "current_price", None), getattr(company, "currency", None)),
        "Rank": format_text(getattr(entry, "rank", None)),
        "Category": format_text(getattr(entry, "category", None)),
        "Recommendation V2": format_text(getattr(recommendation, "decision", None)),
    }
    st.table(pd.DataFrame(rows.items(), columns=["Field", "Value"]))


def _valuation_tab(st: Any, analysis: Any) -> None:
    collection = getattr(analysis, "valuation_snapshots", None)
    snapshots = tuple(getattr(collection, "snapshots", ()) or ())
    if not snapshots:
        st.info("No valuation snapshots are available.")
        return
    rows = [
        {
            "Model": format_text(snapshot.model_type),
            "Value Type": format_text(snapshot.value_type),
            "Selected Value": format_price(snapshot.selected_fair_value, snapshot.currency),
            "Status": format_text(snapshot.status),
            "Confidence": format_text(snapshot.confidence),
            "Methodology": format_text(snapshot.methodology),
        }
        for snapshot in snapshots
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _recommendation_tab(st: Any, analysis: Any) -> None:
    recommendation = getattr(analysis, "recommendation_v2", None)
    if recommendation is None:
        st.info("Recommendation V2 is unavailable.")
        return
    metrics = {
        "Decision": format_text(recommendation.decision),
        "Valuation": format_text(recommendation.valuation_condition),
        "Evidence": format_text(recommendation.evidence_quality),
        "Momentum": format_text(recommendation.momentum_condition),
        "Current vs Base": format_percent(recommendation.current_vs_base_pct, signed=True),
    }
    st.table(pd.DataFrame(metrics.items(), columns=["Field", "Value"]))
    for line in recommendation.rationale:
        st.write(line)


def _evidence_tab(st: Any, analysis: Any) -> None:
    agreement = getattr(analysis, "agreement_result", None)
    fair_range = getattr(analysis, "fair_value_range", None)
    rows = {
        "Core Agreement": format_text(getattr(agreement, "core_intrinsic_agreement", None)),
        "Extended Agreement": format_text(getattr(agreement, "extended_intrinsic_agreement", None)),
        "Overall Agreement": format_text(getattr(agreement, "overall_agreement", None)),
        "Conservative Value": format_price(getattr(fair_range, "conservative_value", None)),
        "Base Value": format_price(getattr(fair_range, "base_value", None)),
        "Optimistic Value": format_price(getattr(fair_range, "optimistic_intrinsic_value", None)),
    }
    st.table(pd.DataFrame(rows.items(), columns=["Field", "Value"]))


def _warnings_tab(st: Any, entry: Any, analysis: Any) -> None:
    warnings: list[str] = []
    warnings.extend(str(item) for item in getattr(entry, "warnings", ()) or ())
    recommendation = getattr(analysis, "recommendation_v2", None)
    warnings.extend(str(item) for item in getattr(recommendation, "warnings", ()) or ())
    if not warnings:
        st.success("No warnings for this symbol.")
        return
    for warning in dict.fromkeys(warnings):
        st.warning(warning)


def _failure_expander(st: Any, result: Any) -> None:
    failures = tuple(getattr(result, "failures", ()) or ())
    if not failures:
        return
    with st.expander("Failed Symbols"):
        for failure in failures:
            st.write(f"{failure.symbol}: {failure.error_type}")
            st.caption(failure.message)


def _disclaimer(st: Any) -> None:
    st.caption("For research and education only. This is not investment advice.")


def _text(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)
