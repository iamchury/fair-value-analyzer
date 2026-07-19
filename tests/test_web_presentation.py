from datetime import date, datetime, timezone
from types import SimpleNamespace

import json

from src.analysis.agreement_engine import AgreementLevel
from src.analysis.momentum_reference import (
    MomentumReferenceStatus,
    PriceField,
    RsiCrossDirection,
)
from src.analysis.ranking_engine import MomentumSentimentPosition, RankingCategory
from src.analysis.recommendation_v2 import (
    EvidenceQuality,
    MomentumCondition,
    RecommendationAlignment,
    RecommendationV2Decision,
    ValuationCondition,
)
from src.analysis.valuation_decision import ValuationRecommendation
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.web.presentation import (
    FULL_SUMMARY_METRIC_LABELS,
    RANKING_COLUMNS,
    build_chart_dataframe,
    build_ranking_dataframe,
    cell_emphasis,
    collect_warnings,
    default_selected_symbol,
    display_label,
    filter_ranking_dataframe,
    format_percent,
    format_price,
    format_text,
    get_ranking_entry,
    model_evidence_rows,
    overview_rows,
    parse_ticker_symbols,
    ranking_csv_download,
    ranking_json_download,
    ranking_summary,
    rsi_reference_details,
    rsi_reference_interpretation,
    top_opportunity_summary,
    valuation_models_dataframe,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def entry(
    symbol: str,
    rank: int,
    score: float,
    eligible: bool = True,
    sentiment: MomentumSentimentPosition = MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE,
    pct: float | None = 0.0,
):
    return SimpleNamespace(
        rank=rank,
        symbol=symbol,
        company_name=f"{symbol} Corp",
        total_score=score,
        normalized_score=score,
        category=RankingCategory.ATTRACTIVE if eligible else RankingCategory.INSUFFICIENT_DATA,
        eligible=eligible,
        recommendation_v2=RecommendationV2Decision.BUY if eligible else RecommendationV2Decision.INSUFFICIENT_DATA,
        valuation_condition=ValuationCondition.UNDERVALUED,
        evidence_quality=EvidenceQuality.HIGH if eligible else EvidenceQuality.INSUFFICIENT,
        agreement=AgreementLevel.STRONG,
        momentum=MomentumCondition.POSITIVE,
        current_price=80.0,
        base_value=100.0,
        current_vs_base_pct=-20.0,
        current_rsi=55.0,
        rsi_reference_date=date(2026, 7, 1),
        rsi_reference_price=76.0,
        rsi_reference_rsi=49.8,
        rsi_cross_direction=RsiCrossDirection.CROSS_BELOW,
        current_vs_rsi_reference_amount=4.0,
        current_vs_rsi_reference_pct=pct,
        momentum_reference_status=MomentumReferenceStatus.COMPLETE,
        momentum_reference_price_field=PriceField.CLOSE,
        momentum_reference_trading_days=10,
        momentum_sentiment_position=sentiment,
        valuation_score=75.0,
        recommendation_score=80.0,
        agreement_score=100.0,
        evidence_score=100.0,
        momentum_score=60.0,
        penalty=0.0,
        warnings=(),
        rationale=("ranking rationale",),
    )


def result(entries):
    return SimpleNamespace(
        success_count=len(entries),
        failure_count=0,
        failures=(),
        ranking_result=SimpleNamespace(
            entries=tuple(entries),
            top_symbol=entries[0].symbol if entries and entries[0].eligible else None,
            top_score=entries[0].normalized_score if entries and entries[0].eligible else None,
            successful_symbols=tuple(item.symbol for item in entries),
            failed_symbols=(),
            status="COMPLETE",
        ),
        successful_results=tuple(analysis(item) for item in entries),
    )


def analysis(item):
    recommendation = SimpleNamespace(
        decision=item.recommendation_v2,
        valuation_condition=item.valuation_condition,
        evidence_quality=item.evidence_quality,
        momentum_condition=item.momentum,
        current_vs_base_pct=item.current_vs_base_pct,
        conservative_value=90.0,
        base_value=item.base_value,
        optimistic_intrinsic_value=120.0,
        analyst_expectation=110.0,
        intrinsic_model_count=2,
        legacy_recommendation=ValuationRecommendation.HOLD,
        alignment=RecommendationAlignment.V2_MORE_BULLISH,
        rationale=("recommendation rationale",),
        warnings=(),
    )
    snapshot = ValuationSnapshot(
        symbol=item.symbol,
        model_type=ValuationModelType.AUTOMATIC_PER,
        model_name="Automatic PER",
        value_type=ValuationValueType.INTRINSIC_VALUE,
        status=ValuationSnapshotStatus.COMPLETE,
        confidence=ValuationConfidenceLevel.MEDIUM,
        raw_fair_value=item.base_value,
        adjusted_fair_value=item.base_value,
        selected_fair_value=item.base_value,
        currency="USD",
        valuation_date=None,
        source_as_of=None,
        generated_at=NOW,
        methodology="test",
        rationale=None,
        assumptions={},
        metrics={},
        warnings=(),
        calculation_steps=(),
    )
    return SimpleNamespace(
        company=SimpleNamespace(symbol=item.symbol, company_name=item.company_name, currency="USD"),
        recommendation_v2=recommendation,
        valuation_snapshots=ValuationSnapshotCollection(item.symbol, (snapshot,), NOW),
        agreement_result=SimpleNamespace(
            core_intrinsic_agreement=AgreementLevel.STRONG,
            extended_intrinsic_agreement=AgreementLevel.MODERATE,
            overall_agreement=AgreementLevel.MODERATE,
        ),
        fair_value_range=SimpleNamespace(
            conservative_value=90.0,
            base_value=item.base_value,
            optimistic_intrinsic_value=120.0,
        ),
    )


def test_parse_tickers_accepts_commas_spaces_newlines_and_dedupes() -> None:
    assert parse_ticker_symbols("mu, nvda\nAMAT MU  lite") == ("MU", "NVDA", "AMAT", "LITE")


def test_parse_tickers_rejects_empty_invalid_and_too_many() -> None:
    for text in ("", "MU, bad/ticker", " ".join(f"T{i}" for i in range(21))):
        try:
            parse_ticker_symbols(text)
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid ticker input")


def test_ranking_dataframe_columns_and_engine_order_are_preserved() -> None:
    batch = result([entry("LITE", 1, 70), entry("MU", 2, 45)])
    dataframe = build_ranking_dataframe(batch)

    assert list(dataframe.columns) == RANKING_COLUMNS
    assert list(dataframe["Symbol"]) == ["LITE", "MU"]


def test_formatting_and_unavailable_values() -> None:
    assert format_price(1234.5, "USD") == "1,234.50 USD"
    assert format_price(None) == "N/A"
    assert format_percent(-3.0, signed=True) == "-3.00%"
    assert format_percent(3.0, signed=True) == "+3.00%"
    assert format_text(None) == "N/A"
    assert format_text("MU") == "MU"


def test_display_label_conversion_keeps_domain_values_out_of_ui() -> None:
    assert display_label(RecommendationV2Decision.INSUFFICIENT_DATA) == "Insufficient Data"
    assert display_label(ValuationCondition.NEAR_FAIR_VALUE) == "Near Fair Value"
    assert display_label(ValuationCondition.SIGNIFICANTLY_OVERVALUED) == "Significantly Overvalued"
    assert display_label("MU") == "MU"


def test_filters_are_display_only_and_preserve_remaining_order() -> None:
    batch = result([
        entry("LITE", 1, 70),
        entry("NVDA", 2, 65, eligible=False),
        entry("MU", 3, 45),
    ])
    dataframe = build_ranking_dataframe(batch)

    filtered = filter_ranking_dataframe(dataframe, eligibility="Eligible")

    assert list(filtered["Symbol"]) == ["LITE", "MU"]


def test_rsi50_mapping_and_existing_interpretation_are_exposed() -> None:
    item = entry("NVDA", 1, 50, sentiment=MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE)

    details = rsi_reference_details(item)
    interpretation = rsi_reference_interpretation(item)

    assert details["RSI50 Reference Price"] == "76.00"
    assert details["Current vs RSI50 %"] == "+0.00%"
    assert details["Current vs Reference Amount"] == "+4.00"
    assert "neutral-reference price" in interpretation[0]


def test_summary_counts_eligible_ineligible_and_rsi_sentiment() -> None:
    batch = result([
        entry("A", 1, 70, sentiment=MomentumSentimentPosition.ABOVE_NEUTRAL_REFERENCE),
        entry("B", 2, 10, False, MomentumSentimentPosition.BELOW_NEUTRAL_REFERENCE),
        entry("C", 3, 5, True, MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE),
    ])

    summary = ranking_summary(batch)

    assert summary["eligible_count"] == 2
    assert summary["insufficient_count"] == 1
    assert summary["above_rsi50"] == 1
    assert summary["near_rsi50"] == 1
    assert summary["below_rsi50"] == 1


def test_chart_dataframe_contains_distinct_value_concepts() -> None:
    chart = build_chart_dataframe(result([entry("MU", 1, 70)]), "MU")

    assert set(chart["Measure"]) == {
        "Current Price",
        "Conservative Intrinsic Value",
        "Base Intrinsic Value",
        "Optimistic Intrinsic Value",
        "Analyst Market Expectation",
        "RSI50 Momentum Reference",
    }
    assert {"Intrinsic", "Market Expectation", "Technical Reference"} <= set(chart["Category"])


def test_csv_and_json_download_generation_include_rsi50_fields() -> None:
    batch = result([entry("MU", 1, 70)])

    csv_text = ranking_csv_download(batch)
    payload = json.loads(ranking_json_download(batch))

    assert "current_vs_rsi_reference_pct" in csv_text
    assert "momentum_sentiment_position" in csv_text
    assert payload["entries"][0]["symbol"] == "MU"
    assert payload["entries"][0]["momentum_reference"]["reference_price"] == 76.0


def test_get_ranking_entry_returns_selected_symbol() -> None:
    batch = result([entry("LITE", 1, 70), entry("MU", 2, 50)])

    assert get_ranking_entry(batch, "mu").symbol == "MU"


def test_top_eligible_opportunity_presentation_mapping() -> None:
    batch = result([entry("LITE", 1, 70)])

    summary = top_opportunity_summary(batch)

    assert summary["Symbol"] == "LITE"
    assert summary["Recommendation V2"] == "Buy"
    assert summary["Ranking Category"] == "Attractive"
    assert summary["Ranking Score"] == "70.00"
    assert summary["Current vs RSI50 Reference %"] == "+0.00%"


def test_no_eligible_opportunity_state() -> None:
    batch = result([entry("NVDA", 1, 65, eligible=False)])

    assert top_opportunity_summary(batch) is None
    assert default_selected_symbol(batch) == "NVDA"


def test_full_metric_labels_are_explicit() -> None:
    assert FULL_SUMMARY_METRIC_LABELS == (
        "Top Eligible Symbol",
        "Top Ranking Score",
        "Eligible Symbols",
        "Insufficient Symbols",
        "Above RSI50",
        "Near RSI50",
        "Below RSI50",
        "Successful / Failed",
    )


def test_conditional_style_classification() -> None:
    assert cell_emphasis("Buy") == "positive"
    assert cell_emphasis("Hold") == "neutral"
    assert cell_emphasis("Sell") == "negative"
    assert cell_emphasis("Insufficient Data") == "muted"


def test_selected_symbol_default_uses_top_then_first_successful() -> None:
    assert default_selected_symbol(result([entry("LITE", 1, 70), entry("MU", 2, 50)])) == "LITE"
    assert default_selected_symbol(result([entry("NVDA", 1, 20, eligible=False)])) == "NVDA"


def test_overview_rows_include_required_detail_fields() -> None:
    batch = result([entry("MU", 1, 70)])

    rows = overview_rows(get_ranking_entry(batch, "MU"), batch.successful_results[0])

    assert rows["Company Name"] == "MU Corp"
    assert rows["Recommendation V2"] == "Buy"
    assert rows["RSI50 Reference Price"] == "76.00"


def test_valuation_table_keeps_analyst_consensus_as_market_expectation() -> None:
    item = entry("MU", 1, 70)
    stock = analysis(item)
    automatic = stock.valuation_snapshots.snapshots[0]
    analyst = ValuationSnapshot(
        symbol="MU",
        model_type=ValuationModelType.ANALYST_CONSENSUS,
        model_name="Analyst Consensus",
        value_type=ValuationValueType.MARKET_EXPECTATION,
        status=ValuationSnapshotStatus.COMPLETE,
        confidence=ValuationConfidenceLevel.LOW,
        raw_fair_value=110.0,
        adjusted_fair_value=110.0,
        selected_fair_value=110.0,
        currency="USD",
        valuation_date=None,
        source_as_of=None,
        generated_at=NOW,
        methodology="Weighted Mean / Midpoint",
        rationale=None,
        assumptions={},
        metrics={},
        warnings=("Analyst target dispersion is extreme.",),
        calculation_steps=(),
    )
    stock.valuation_snapshots = ValuationSnapshotCollection("MU", (automatic, analyst), NOW)

    dataframe = valuation_models_dataframe(stock)
    row = dataframe[dataframe["Model"] == "Analyst Consensus"].iloc[0]

    assert row["Value Type"] == "Market Expectation"
    assert row["Included in Intrinsic Range"] == "No - Market Expectation"
    assert "Market expectation" in row["Notes"]


def test_model_evidence_rows_show_required_minimum_and_counts() -> None:
    rows = model_evidence_rows(analysis(entry("MU", 1, 70)), required_minimum=2)

    assert rows["Intrinsic Model Count"] == "2"
    assert rows["Required Minimum Model Count"] == "2"


def test_warning_deduplication_preserves_first_occurrence() -> None:
    batch = result([entry("MU", 1, 70)])
    item = get_ranking_entry(batch, "MU")
    item.warnings = ("Momentum is missing.", "Momentum is missing.")
    stock = batch.successful_results[0]
    stock.recommendation_v2.warnings = ("Momentum is missing.", "Fair value range is partial.")

    assert collect_warnings(batch, item, stock)[:2] == (
        "Momentum is missing.",
        "Fair value range is partial.",
    )
