from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as streamlit_module

from src.services.batch_analysis import analyze_symbol_list_with_profiles_from_config_files
from src.services.soxx_timing import analyze_soxx_timing_from_config_file
from src.config.recommendation_v2 import load_recommendation_v2_configuration
from src.web.presentation import (
    DEFAULT_SYMBOL_TEXT,
    DEFAULT_WEB_CONFIG,
    FULL_SUMMARY_METRIC_LABELS,
    WebConfigPaths,
    build_chart_dataframe,
    build_ranking_dataframe,
    collect_warnings,
    default_selected_symbol,
    filter_ranking_dataframe,
    format_number,
    format_percent,
    format_price,
    format_text,
    model_evidence_rows,
    outliers_dataframe,
    overview_interpretation,
    overview_rows,
    pairwise_agreement_dataframe,
    get_ranking_entry,
    get_successful_result,
    parse_ticker_symbols,
    ranking_csv_download,
    ranking_json_download,
    ranking_summary,
    rsi_reference_details,
    rsi_reference_interpretation,
    style_ranking_dataframe,
    successful_symbols,
    top_opportunity_summary,
    valuation_models_dataframe,
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


def analyze_symbols_for_dashboard(symbols: tuple[str, ...]) -> Any:
    return analyze_symbols(symbols, get_dashboard_config())


@streamlit_module.cache_resource(show_spinner=False)
def get_dashboard_config() -> WebConfigPaths:
    return DEFAULT_WEB_CONFIG


@streamlit_module.cache_resource(show_spinner=False)
def get_required_minimum_intrinsic_models() -> int | None:
    try:
        return load_recommendation_v2_configuration(
            get_dashboard_config().recommendation_v2_config_path
        ).minimum_intrinsic_models
    except Exception:
        return None


def run() -> None:
    st = streamlit_module

    st.set_page_config(page_title="Fair Value Analyzer", layout="wide")
    st.title("Fair Value Analyzer")
    st.caption("Valuation, Recommendation V2, ranking, and RSI50 momentum reference dashboard.")

    with st.sidebar:
        st.header("Analysis")
        raw_symbols = st.text_area("Tickers", value=DEFAULT_SYMBOL_TEXT, height=130)
        analyze = st.button("Analyze", type="primary", width="stretch")
        st.caption("Maximum 20 tickers. Input accepts commas, spaces, or new lines.")

    if analyze:
        _run_analysis(st, raw_symbols)

    result = st.session_state.get("analysis_result")
    if result is None:
        _soxx_market_timing(st)
        if st.session_state.get("analysis_error"):
            st.error("Analysis failed.")
            with st.expander("Technical details"):
                st.write(st.session_state["analysis_error"])
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
        result = analyze_symbols_for_dashboard(symbols)
        progress.progress(75, text="Building ranking and RSI 50 reference views")
        st.session_state["analysis_result"] = result
        st.session_state["analysis_symbols"] = symbols
        st.session_state["analysis_error"] = None
    except Exception as exc:
        st.session_state["analysis_error"] = str(exc)
        st.error("Analysis failed. Expand technical details for more information.")
        with st.expander("Technical details"):
            st.exception(exc)
    try:
        progress.progress(85, text="Analyzing SOXX market timing")
        st.session_state["soxx_timing_result"] = analyze_soxx_timing_from_config_file(
            get_dashboard_config().soxx_timing_config_path
        )
        st.session_state["soxx_timing_error"] = None
    except Exception as exc:
        st.session_state["soxx_timing_error"] = str(exc)
    finally:
        st.session_state["analysis_generated_at"] = datetime.now(timezone.utc)
        progress.progress(100, text="Analysis complete")
        progress.empty()


def _render_dashboard(st: Any, result: Any) -> None:
    _summary_metrics(st, result)
    _macro_status(st, result)
    _failure_expander(st, result)
    table = build_ranking_dataframe(result)
    _top_opportunity(st, result)
    filtered = _filters(st, table)
    _soxx_market_timing(st)
    st.subheader("Multi-Stock Ranking")
    st.dataframe(style_ranking_dataframe(filtered), hide_index=True, width="stretch")
    _downloads(st, result)
    symbols = list(successful_symbols(result))
    if not symbols:
        st.warning("No successfully analyzed symbols are available.")
        return
    default_symbol = default_selected_symbol(result)
    default_index = symbols.index(default_symbol) if default_symbol in symbols else 0
    st.subheader("Stock Detail")
    selected = st.selectbox("Selected Symbol", symbols, index=default_index)
    entry = get_ranking_entry(result, selected)
    analysis = get_successful_result(result, selected)
    _valuation_chart(st, result, selected)
    _detail_tabs(st, result, entry, analysis)


def _soxx_market_timing(st: Any) -> None:
    result = st.session_state.get("soxx_timing_result")
    error = st.session_state.get("soxx_timing_error")
    if result is None and not error:
        return
    st.subheader("SOXX Market Timing")
    if error and result is None:
        st.warning(f"SOXX timing unavailable: {error}")
        return
    if error:
        st.warning(f"SOXX timing warning: {error}")
    signal = format_text(getattr(result, "primary_signal", None))
    color_key = getattr(result, "signal_color_key", "NEUTRAL_GRAY")
    st.caption(f"Signal color key: {color_key}")
    first = st.columns(2)
    first[0].metric("Primary Signal", signal)
    first[1].metric("Signal Strength", format_text(getattr(result, "signal_strength", None)))
    metrics = [
        ("Current SOXX Price", format_price(getattr(result, "current_price", None))),
        ("Prior High", format_price(getattr(result, "prior_high_price", None))),
        ("Drawdown", format_percent(getattr(result, "drawdown_pct", None), signed=True)),
        ("Signal Date", format_text(getattr(result, "as_of_date", None))),
        ("MA5", format_number(getattr(result, "ma5", None))),
        ("MA10", format_number(getattr(result, "ma10", None))),
        ("MA15", format_number(getattr(result, "ma15", None))),
        ("MA20", format_number(getattr(result, "ma20", None))),
        ("MA50", format_number(getattr(result, "ma50", None))),
        ("MA5 vs MA10", _cross_or_position(result, "ma5_ma10_cross", "ma5", "ma10")),
        ("MA5 vs MA15", _cross_or_position(result, "ma5_ma15_cross", "ma5", "ma15")),
        ("MA5 vs MA20", _cross_or_position(result, "ma5_ma20_cross", "ma5", "ma20")),
        ("Short-MA Convergence", "Converged" if getattr(result, "short_ma_converged", False) else "Not Converged"),
        ("MA Cluster vs MA50", _cluster_position(result)),
        ("Status", format_text(getattr(result, "status", None))),
    ]
    for offset in range(0, len(metrics), 2):
        cols = st.columns(2)
        for index, (label, value) in enumerate(metrics[offset : offset + 2]):
            cols[index].metric(label, value)
    active = ", ".join(format_text(item) for item in tuple(getattr(result, "active_conditions", ()) or ())) or "None"
    st.info(f"Active Conditions: {active}")
    for line in tuple(getattr(result, "rationale", ()) or ()):
        st.caption(line)
    chart = _soxx_chart_dataframe(result)
    if not chart.empty:
        st.line_chart(chart, x="Date", y=[column for column in chart.columns if column != "Date"], use_container_width=True)
    events = _soxx_event_dataframe(result)
    if not events.empty:
        st.dataframe(events, hide_index=True, width="stretch")


def _cross_or_position(result: Any, cross_name: str, fast_name: str, slow_name: str) -> str:
    cross = getattr(getattr(result, cross_name, None), "direction", None)
    cross_text = format_text(cross)
    if cross_text not in {"None", "Unavailable", "N/A"}:
        return cross_text
    fast = getattr(result, fast_name, None)
    slow = getattr(result, slow_name, None)
    if fast is None or slow is None:
        return "No New Cross"
    position = "Above" if fast > slow else "Below" if fast < slow else "Equal"
    return f"No New Cross / MA5 {position}"


def _cluster_position(result: Any) -> str:
    if getattr(result, "short_cluster_above_ma50", False):
        return "Short Cluster Above MA50"
    if getattr(result, "short_cluster_below_ma50", False):
        return "Short Cluster Below MA50"
    return "Mixed"


def _soxx_chart_dataframe(result: Any) -> pd.DataFrame:
    rows = []
    for point in tuple(getattr(result, "daily_points", ()) or ())[-126:]:
        rows.append(
            {
                "Date": point.date,
                "SOXX Price": point.close,
                "MA5": point.ma5,
                "MA10": point.ma10,
                "MA15": point.ma15,
                "MA20": point.ma20,
                "MA50": point.ma50,
                "Prior High": point.prior_high_price,
            }
        )
    return pd.DataFrame(rows)


def _soxx_event_dataframe(result: Any) -> pd.DataFrame:
    rows = []
    for event in tuple(getattr(result, "events", ()) or ()):
        rows.append(
            {
                "Date": event.date,
                "Signal": format_text(event.signal),
                "Close": format_price(event.close),
                "Drawdown": format_percent(event.drawdown_pct, signed=True),
                "Cross": format_text(event.cross_direction),
            }
        )
    return pd.DataFrame(rows)


def _summary_metrics(st: Any, result: Any) -> None:
    summary = ranking_summary(result)
    first = st.columns(4)
    first[0].metric(FULL_SUMMARY_METRIC_LABELS[0], format_text(summary["top_symbol"]))
    first[1].metric(FULL_SUMMARY_METRIC_LABELS[1], format_number(summary["top_score"]))
    first[2].metric(FULL_SUMMARY_METRIC_LABELS[2], summary["eligible_count"])
    first[3].metric(FULL_SUMMARY_METRIC_LABELS[3], summary["insufficient_count"])
    second = st.columns(4)
    second[0].metric(FULL_SUMMARY_METRIC_LABELS[4], summary["above_rsi50"])
    second[1].metric(FULL_SUMMARY_METRIC_LABELS[5], summary["near_rsi50"])
    second[2].metric(FULL_SUMMARY_METRIC_LABELS[6], summary["below_rsi50"])
    second[3].metric(FULL_SUMMARY_METRIC_LABELS[7], f"{result.success_count} / {result.failure_count}")


def _top_opportunity(st: Any, result: Any) -> None:
    st.subheader("Top Eligible Opportunity")
    summary = top_opportunity_summary(result)
    st.caption(
        "Top Eligible Opportunity identifies the highest-ranked eligible stock in the current comparison set. It does not override the stock's Recommendation V2 decision."
    )
    if summary is None:
        st.info("No eligible opportunity")
        return
    items = list(summary.items())
    for offset in range(0, len(items), 4):
        cols = st.columns(4)
        for index, (label, value) in enumerate(items[offset : offset + 4]):
            cols[index].metric(label, value)


def _macro_status(st: Any, result: Any) -> None:
    if getattr(result, "treasury_status", None) is None:
        return
    st.subheader("Macro Data Status")
    cols = st.columns(6)
    cols[0].metric("US 10Y Yield", format_percent(getattr(result, "treasury_yield_percent", None)))
    cols[1].metric("Source", format_text(getattr(result, "treasury_source_name", None)))
    cols[2].metric("Source Date", format_text(getattr(result, "treasury_source_date", None)))
    cols[3].metric("Trend", format_text(getattr(result, "treasury_trend", None)))
    cols[4].metric("Data Status", format_text(getattr(result, "treasury_status", None)))
    fallback = "Yes" if getattr(result, "treasury_used_fallback", False) else "No"
    cols[5].metric("Fallback Used", fallback)
    warning = getattr(result, "treasury_warning", None)
    if warning:
        st.warning(warning)
    message = getattr(result, "treasury_message", None)
    if message:
        st.info(message)
    diagnostics = tuple(getattr(result, "treasury_provider_diagnostics", ()) or ())
    if diagnostics:
        with st.expander("Treasury Provider Diagnostics"):
            for diagnostic in diagnostics:
                st.caption(diagnostic)


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
        width="stretch",
    )
    right.download_button(
        "Download Ranking JSON",
        ranking_json_download(result),
        file_name="ranking.json",
        mime="application/json",
        width="stretch",
    )


def _valuation_chart(st: Any, result: Any, symbol: str) -> None:
    st.subheader("Valuation Comparison")
    chart = build_chart_dataframe(result, symbol)
    if chart.empty:
        st.info("No comparable values are available for this symbol.")
        return
    st.bar_chart(chart.set_index("Measure")["Value"])
    st.caption(
        "Analyst consensus is a market-expectation measure. RSI50 reference is a technical momentum level. Neither is included as an intrinsic-value average."
    )
    st.dataframe(chart, hide_index=True, width="stretch")


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


def _detail_tabs(st: Any, result: Any, entry: Any, analysis: Any) -> None:
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
            st.caption(
                "The RSI50 reference price is the price associated with the latest neutral-line transition or configured fallback. It is a technical momentum and sentiment reference, not intrinsic value, guaranteed support, or investor average cost."
            )
            st.table(pd.DataFrame(rsi_reference_details(entry).items(), columns=["Field", "Value"]))
            for line in rsi_reference_interpretation(entry):
                st.write(line)
    with evidence:
        _evidence_tab(st, analysis)
    with warnings:
        _warnings_tab(st, result, entry, analysis)


def _overview_tab(st: Any, entry: Any, analysis: Any) -> None:
    rows = overview_rows(entry, analysis)
    st.table(pd.DataFrame(rows.items(), columns=["Field", "Value"]))
    for line in overview_interpretation(entry, analysis):
        st.write(line)


def _valuation_tab(st: Any, analysis: Any) -> None:
    dataframe = valuation_models_dataframe(analysis)
    if dataframe.empty:
        st.info("No valuation snapshots are available.")
        return
    st.dataframe(dataframe, hide_index=True, width="stretch")


def _recommendation_tab(st: Any, analysis: Any) -> None:
    recommendation = getattr(analysis, "recommendation_v2", None)
    if recommendation is None:
        st.info("Recommendation V2 is unavailable.")
        return
    metrics = {
        "Recommendation V2 Decision": format_text(recommendation.decision),
        "Valuation Condition": format_text(recommendation.valuation_condition),
        "Momentum Condition": format_text(recommendation.momentum_condition),
        "Evidence Quality": format_text(recommendation.evidence_quality),
        "Legacy Recommendation": format_text(getattr(recommendation, "legacy_recommendation", None)),
        "Alignment Status": format_text(getattr(recommendation, "alignment", None)),
        "Current vs Base": format_percent(recommendation.current_vs_base_pct, signed=True),
    }
    st.table(pd.DataFrame(metrics.items(), columns=["Field", "Value"]))
    if format_text(getattr(recommendation, "alignment", None)) in {"V2 More Bullish", "V2 More Bearish"}:
        st.warning("Legacy recommendation and Recommendation V2 diverge.")
    for line in recommendation.rationale:
        st.write(line)
    for warning in getattr(recommendation, "warnings", ()) or ():
        st.warning(warning)


def _evidence_tab(st: Any, analysis: Any) -> None:
    rows = model_evidence_rows(analysis, get_required_minimum_intrinsic_models())
    st.table(pd.DataFrame(rows.items(), columns=["Field", "Value"]))
    pairwise = pairwise_agreement_dataframe(analysis)
    if not pairwise.empty:
        st.write("Pairwise Agreement")
        st.dataframe(pairwise, hide_index=True, width="stretch")
    outliers = outliers_dataframe(analysis)
    if not outliers.empty:
        st.write("Identified Outliers")
        st.dataframe(outliers, hide_index=True, width="stretch")
    snapshots = valuation_models_dataframe(analysis)
    if not snapshots.empty:
        st.write("Included / Excluded Evidence")
        st.dataframe(snapshots, hide_index=True, width="stretch")


def _warnings_tab(st: Any, result: Any, entry: Any, analysis: Any) -> None:
    warnings = collect_warnings(result, entry, analysis)
    if not warnings:
        st.success("No material analysis warnings.")
        return
    for warning in warnings:
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
