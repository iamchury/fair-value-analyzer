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
    RecommendationV2Decision,
    ValuationCondition,
)
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.web.presentation import (
    RANKING_COLUMNS,
    build_chart_dataframe,
    build_ranking_dataframe,
    filter_ranking_dataframe,
    format_percent,
    format_price,
    format_text,
    get_ranking_entry,
    parse_ticker_symbols,
    ranking_csv_download,
    ranking_json_download,
    ranking_summary,
    rsi_reference_details,
    rsi_reference_interpretation,
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
        "RSI50 Reference Price",
    }


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
