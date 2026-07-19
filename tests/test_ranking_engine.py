from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.analysis.agreement_engine import AgreementLevel
from src.analysis.fair_value_range import FairValueRangeStatus
from src.analysis.ranking_engine import (
    MomentumSentimentPosition,
    RankingCategory,
    StockRankingStatus,
    classify_momentum_sentiment_position,
    momentum_reference_interpretation,
    rank_stocks,
)
from src.analysis.momentum_reference import (
    MomentumPricePosition,
    MomentumReferenceStatus,
    PriceField,
    RsiCrossDirection,
    RsiMomentumReference,
)
from src.analysis.recommendation_v2 import (
    EvidenceQuality,
    MomentumCondition,
    RecommendationAlignment,
    RecommendationV2Decision,
    RecommendationV2Result,
    RecommendationV2Status,
    ValuationCondition,
)
from src.analysis.valuation_decision import ValuationRecommendation
from src.config.ranking_engine import RankingEngineConfiguration, RankingWeights
from src.services.batch_analysis import StockAnalysisFailure


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def config() -> RankingEngineConfiguration:
    return RankingEngineConfiguration(True, RankingWeights(45, 20, 15, 10, 10))


def recommendation(
    symbol: str = "LITE",
    decision: RecommendationV2Decision = RecommendationV2Decision.BUY,
    valuation: ValuationCondition = ValuationCondition.UNDERVALUED,
    evidence: EvidenceQuality = EvidenceQuality.HIGH,
    agreement: AgreementLevel = AgreementLevel.STRONG,
    momentum: MomentumCondition = MomentumCondition.POSITIVE,
    current_vs_base_pct: float = -20.0,
    status: RecommendationV2Status = RecommendationV2Status.COMPLETE,
    intrinsic_model_count: int = 2,
    base_value: float | None = 100.0,
) -> RecommendationV2Result:
    return RecommendationV2Result(
        symbol=symbol,
        status=status,
        decision=decision,
        valuation_condition=valuation,
        momentum_condition=momentum,
        evidence_quality=evidence,
        current_price=80.0,
        conservative_value=90.0,
        base_value=base_value,
        optimistic_intrinsic_value=120.0,
        current_vs_base_pct=current_vs_base_pct,
        core_agreement=agreement,
        extended_agreement=agreement,
        intrinsic_model_count=intrinsic_model_count,
        reference_model_count=1,
        current_rsi=55.0,
        rsi_reference_price=76.0,
        current_vs_rsi_reference_pct=5.0,
        analyst_expectation=110.0,
        analyst_outlier_status=None,
        analyst_confidence=None,
        legacy_recommendation=ValuationRecommendation.BUY,
        alignment=RecommendationAlignment.ALIGNED,
        rationale=("reused recommendation",),
        warnings=(),
        calculation_steps=(),
        generated_at=NOW,
    )


def analysis_result(
    rec: RecommendationV2Result,
    range_status=FairValueRangeStatus.COMPLETE,
    analysis_status="COMPLETE",
    momentum_reference: RsiMomentumReference | None = None,
):
    return SimpleNamespace(
        recommendation_v2=rec,
        momentum_reference=momentum_reference,
        fair_value_range=SimpleNamespace(status=range_status),
        company=SimpleNamespace(company_name=f"{rec.symbol} Corp"),
        valuation=SimpleNamespace(symbol=rec.symbol, status=analysis_status),
    )


def momentum_reference(
    symbol: str = "LITE",
    direction: RsiCrossDirection = RsiCrossDirection.CROSS_ABOVE,
    pct: float | None = 12.0,
    current_rsi: float | None = 61.0,
    status: MomentumReferenceStatus = MomentumReferenceStatus.COMPLETE,
) -> RsiMomentumReference:
    reference_price = 100.0 if pct is not None else None
    current_price = None if pct is None else 100.0 * (1.0 + pct / 100.0)
    return RsiMomentumReference(
        symbol=symbol,
        status=status,
        rsi_period=14,
        neutral_level=50.0,
        reference_date=date(2026, 7, 2) if reference_price is not None else None,
        reference_price=reference_price,
        reference_rsi=48.47 if reference_price is not None else None,
        cross_direction=direction,
        current_date=date(2026, 7, 16) if current_price is not None else None,
        current_price=current_price,
        current_rsi=current_rsi,
        price_field=PriceField.CLOSE if reference_price is not None else None,
        trading_days_since_reference=10 if reference_price is not None else None,
        price_change_since_reference=None if current_price is None else current_price - reference_price,
        price_change_since_reference_pct=pct,
        price_position=MomentumPricePosition.UNKNOWN,
        lookback_start=None,
        lookback_end=None,
        observation_count=30,
        methodology="test",
        rationale=None,
        warnings=(),
        calculation_steps=(),
        generated_at=NOW,
    )


def test_undervalued_strong_buy_scores_above_overvalued_sell() -> None:
    buy = analysis_result(
        recommendation(
            "BUY",
            RecommendationV2Decision.STRONG_BUY,
            ValuationCondition.DEEPLY_UNDERVALUED,
            EvidenceQuality.HIGH,
            AgreementLevel.STRONG,
            MomentumCondition.STRONG_POSITIVE,
            -35.0,
        )
    )
    sell = analysis_result(
        recommendation(
            "SELL",
            RecommendationV2Decision.SELL,
            ValuationCondition.SIGNIFICANTLY_OVERVALUED,
            EvidenceQuality.HIGH,
            AgreementLevel.STRONG,
            MomentumCondition.WEAK,
            25.0,
        )
    )

    result = rank_stocks((sell, buy), (), config(), NOW)

    assert result.status == StockRankingStatus.COMPLETE
    assert result.top_symbol == "BUY"
    assert result.entries[0].category == RankingCategory.TOP_OPPORTUNITY
    assert result.entries[1].category == RankingCategory.CAUTION
    assert all(entry.eligible for entry in result.entries)


def test_hold_and_weak_momentum_are_component_scored() -> None:
    result = rank_stocks(
        (
            analysis_result(
                recommendation(
                    decision=RecommendationV2Decision.HOLD,
                    valuation=ValuationCondition.NEAR_FAIR_VALUE,
                    evidence=EvidenceQuality.MEDIUM,
                    agreement=AgreementLevel.MODERATE,
                    momentum=MomentumCondition.WEAK,
                    current_vs_base_pct=0.0,
                )
            ),
        ),
        (),
        config(),
        NOW,
    )

    entry = result.entries[0]
    assert entry.recommendation_score == 10
    assert entry.momentum_score == -30
    assert entry.category == RankingCategory.WATCHLIST


def test_positive_momentum_scores_higher_than_weak_momentum() -> None:
    positive = analysis_result(recommendation("POS", momentum=MomentumCondition.POSITIVE))
    weak = analysis_result(recommendation("WEAK", momentum=MomentumCondition.WEAK))

    result = rank_stocks((weak, positive), (), config(), NOW)

    assert result.entries[0].symbol == "POS"


def test_failed_symbol_marks_partial_result_without_blocking_success() -> None:
    result = rank_stocks(
        (analysis_result(recommendation()),),
        (StockAnalysisFailure("MU", "RuntimeError", "failed"),),
        config(),
        NOW,
    )

    assert result.status == StockRankingStatus.PARTIAL
    assert result.failed_symbols == ("MU",)
    assert result.entries[0].rank == 1


def test_tie_score_uses_component_sort_then_symbol() -> None:
    amat = analysis_result(recommendation("AMAT"))
    lite = analysis_result(recommendation("LITE"))

    result = rank_stocks((lite, amat), (), config(), NOW)

    assert [entry.symbol for entry in result.entries] == ["AMAT", "LITE"]


def test_reliability_penalties_cover_partial_missing_momentum_conflict_and_models() -> None:
    rec = recommendation(
        status=RecommendationV2Status.PARTIAL,
        agreement=AgreementLevel.CONFLICTED,
        momentum=MomentumCondition.UNAVAILABLE,
        intrinsic_model_count=1,
    )
    result = rank_stocks(
        (analysis_result(rec, FairValueRangeStatus.PARTIAL),),
        (),
        config(),
        NOW,
    )

    entry = result.entries[0]
    assert entry.penalty == 48.0
    assert entry.category == RankingCategory.INSUFFICIENT_DATA
    assert entry.eligible is False
    assert "Momentum is missing." in entry.warnings


def test_insufficient_entry_with_higher_score_stays_below_eligible_entry() -> None:
    ineligible = analysis_result(
        recommendation(
            "NVDA",
            RecommendationV2Decision.INSUFFICIENT_DATA,
            ValuationCondition.DEEPLY_UNDERVALUED,
            EvidenceQuality.INSUFFICIENT,
            AgreementLevel.STRONG,
            MomentumCondition.STRONG_POSITIVE,
            -60.0,
            intrinsic_model_count=1,
        )
    )
    eligible = analysis_result(
        recommendation(
            "MU",
            RecommendationV2Decision.SELL,
            ValuationCondition.SIGNIFICANTLY_OVERVALUED,
            EvidenceQuality.HIGH,
            AgreementLevel.STRONG,
            MomentumCondition.WEAK,
            25.0,
        )
    )

    result = rank_stocks((ineligible, eligible), (), config(), NOW)

    assert result.entries[0].symbol == "MU"
    assert result.entries[0].eligible is True
    assert result.entries[1].symbol == "NVDA"
    assert result.entries[1].normalized_score > result.entries[0].normalized_score
    assert result.entries[1].category == RankingCategory.INSUFFICIENT_DATA


def test_evidence_insufficient_forces_insufficient_category() -> None:
    result = rank_stocks(
        (
            analysis_result(
                recommendation(evidence=EvidenceQuality.INSUFFICIENT)
            ),
        ),
        (),
        config(),
        NOW,
    )

    assert result.entries[0].category == RankingCategory.INSUFFICIENT_DATA


def test_recommendation_insufficient_forces_insufficient_category() -> None:
    result = rank_stocks(
        (
            analysis_result(
                recommendation(decision=RecommendationV2Decision.INSUFFICIENT_DATA)
            ),
        ),
        (),
        config(),
        NOW,
    )

    assert result.entries[0].category == RankingCategory.INSUFFICIENT_DATA


def test_error_status_forces_insufficient_category() -> None:
    result = rank_stocks(
        (analysis_result(recommendation(), analysis_status="ERROR"),),
        (),
        config(),
        NOW,
    )

    assert result.entries[0].category == RankingCategory.INSUFFICIENT_DATA


def test_missing_base_value_forces_insufficient_category() -> None:
    result = rank_stocks(
        (analysis_result(recommendation(base_value=None)),),
        (),
        config(),
        NOW,
    )

    assert result.entries[0].category == RankingCategory.INSUFFICIENT_DATA


def test_top_symbol_is_chosen_only_from_eligible_entries() -> None:
    eligible = analysis_result(
        recommendation(
            "MU",
            RecommendationV2Decision.SELL,
            ValuationCondition.SIGNIFICANTLY_OVERVALUED,
            EvidenceQuality.HIGH,
            AgreementLevel.STRONG,
            MomentumCondition.WEAK,
            25.0,
        )
    )
    ineligible = analysis_result(
        recommendation(
            "NVDA",
            RecommendationV2Decision.INSUFFICIENT_DATA,
            ValuationCondition.DEEPLY_UNDERVALUED,
            EvidenceQuality.INSUFFICIENT,
            current_vs_base_pct=-80.0,
            intrinsic_model_count=1,
        )
    )

    result = rank_stocks((ineligible, eligible), (), config(), NOW)

    assert result.top_symbol == "MU"
    assert result.top_score == result.entries[0].normalized_score


def test_all_ineligible_batch_has_no_top_symbol() -> None:
    result = rank_stocks(
        (
            analysis_result(
                recommendation("NVDA", decision=RecommendationV2Decision.INSUFFICIENT_DATA)
            ),
            analysis_result(
                recommendation("AMAT", evidence=EvidenceQuality.INSUFFICIENT)
            ),
        ),
        (),
        config(),
        NOW,
    )

    assert result.status == StockRankingStatus.INSUFFICIENT
    assert result.top_symbol is None
    assert result.top_score is None


def test_existing_component_score_calculations_are_unchanged() -> None:
    result = rank_stocks(
        (
            analysis_result(
                recommendation(
                    decision=RecommendationV2Decision.HOLD,
                    valuation=ValuationCondition.NEAR_FAIR_VALUE,
                    evidence=EvidenceQuality.MEDIUM,
                    agreement=AgreementLevel.MODERATE,
                    momentum=MomentumCondition.WEAK,
                    current_vs_base_pct=0.0,
                )
            ),
        ),
        (),
        config(),
        NOW,
    )

    entry = result.entries[0]
    assert entry.valuation_score == 20
    assert entry.recommendation_score == 10
    assert entry.evidence_score == 55
    assert entry.agreement_score == 50
    assert entry.momentum_score == -30


def test_eligible_lite_ranks_above_eligible_mu_fixture() -> None:
    lite = analysis_result(
        recommendation(
            "LITE",
            RecommendationV2Decision.REDUCE,
            ValuationCondition.NEAR_FAIR_VALUE,
            EvidenceQuality.MEDIUM,
            AgreementLevel.MODERATE,
            MomentumCondition.STRONG_NEGATIVE,
            -5.0,
        )
    )
    mu = analysis_result(
        recommendation(
            "MU",
            RecommendationV2Decision.SELL,
            ValuationCondition.SIGNIFICANTLY_OVERVALUED,
            EvidenceQuality.HIGH,
            AgreementLevel.STRONG,
            MomentumCondition.WEAK,
            22.81,
        )
    )

    result = rank_stocks((mu, lite), (), config(), NOW)

    assert [entry.symbol for entry in result.entries] == ["LITE", "MU"]


def test_nvda_amat_cohr_like_insufficient_fixtures_appear_below_eligible_entries() -> None:
    lite = analysis_result(recommendation("LITE", RecommendationV2Decision.REDUCE, ValuationCondition.NEAR_FAIR_VALUE, EvidenceQuality.MEDIUM))
    mu = analysis_result(recommendation("MU", RecommendationV2Decision.SELL, ValuationCondition.SIGNIFICANTLY_OVERVALUED, EvidenceQuality.HIGH, current_vs_base_pct=22.81))
    nvda = analysis_result(recommendation("NVDA", RecommendationV2Decision.INSUFFICIENT_DATA, ValuationCondition.DEEPLY_UNDERVALUED, EvidenceQuality.INSUFFICIENT, intrinsic_model_count=1))
    amat = analysis_result(recommendation("AMAT", RecommendationV2Decision.INSUFFICIENT_DATA, ValuationCondition.UNDERVALUED, EvidenceQuality.INSUFFICIENT, intrinsic_model_count=1))
    cohr = analysis_result(recommendation("COHR", RecommendationV2Decision.INSUFFICIENT_DATA, ValuationCondition.UNDERVALUED, EvidenceQuality.INSUFFICIENT, intrinsic_model_count=1))

    result = rank_stocks((nvda, amat, lite, cohr, mu), (), config(), NOW)

    assert [entry.symbol for entry in result.entries[:2]] == ["LITE", "MU"]
    assert {entry.symbol for entry in result.entries[2:]} == {"NVDA", "AMAT", "COHR"}
    assert all(entry.category == RankingCategory.INSUFFICIENT_DATA for entry in result.entries[2:])


def test_cross_above_well_above_reference_fields_and_interpretation() -> None:
    result = rank_stocks(
        (analysis_result(recommendation(), momentum_reference=momentum_reference(pct=12.0)),),
        (),
        config(),
        NOW,
    )

    entry = result.entries[0]
    assert entry.momentum_sentiment_position == MomentumSentimentPosition.WELL_ABOVE_NEUTRAL_REFERENCE
    assert entry.rsi_cross_direction == RsiCrossDirection.CROSS_ABOVE
    assert entry.rsi_reference_price == 100.0
    assert "crossed above" in momentum_reference_interpretation(entry)[0]


def test_cross_above_below_reference_interpretation() -> None:
    entry = rank_stocks(
        (analysis_result(recommendation(), momentum_reference=momentum_reference(pct=-4.0)),),
        (),
        config(),
        NOW,
    ).entries[0]

    assert entry.momentum_sentiment_position == MomentumSentimentPosition.BELOW_NEUTRAL_REFERENCE
    assert "prior positive RSI transition has failed" in momentum_reference_interpretation(entry)[0]


def test_cross_below_well_below_reference_matches_mu_shape() -> None:
    entry = rank_stocks(
        (
            analysis_result(
                recommendation("MU"),
                momentum_reference=momentum_reference(
                    "MU",
                    RsiCrossDirection.CROSS_BELOW,
                    -12.96,
                    41.01,
                ),
            ),
        ),
        (),
        config(),
        NOW,
    ).entries[0]

    assert entry.momentum_sentiment_position == MomentumSentimentPosition.WELL_BELOW_NEUTRAL_REFERENCE
    assert entry.current_rsi == 41.01
    assert entry.rsi_reference_rsi == 48.47
    assert entry.current_vs_rsi_reference_pct == -12.96
    assert "crossed below" in momentum_reference_interpretation(entry)[0]


def test_cross_below_above_reference_interpretation() -> None:
    entry = rank_stocks(
        (
            analysis_result(
                recommendation(),
                momentum_reference=momentum_reference(direction=RsiCrossDirection.CROSS_BELOW, pct=4.0),
            ),
        ),
        (),
        config(),
        NOW,
    ).entries[0]

    assert entry.momentum_sentiment_position == MomentumSentimentPosition.ABOVE_NEUTRAL_REFERENCE
    assert "recovered" in momentum_reference_interpretation(entry)[0]


def test_nearest_to_50_fallback_interpretation() -> None:
    entry = rank_stocks(
        (
            analysis_result(
                recommendation(),
                momentum_reference=momentum_reference(
                    direction=RsiCrossDirection.NEAREST_TO_50,
                    pct=0.0,
                    status=MomentumReferenceStatus.FALLBACK,
                ),
            ),
        ),
        (),
        config(),
        NOW,
    ).entries[0]

    assert entry.momentum_sentiment_position == MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE
    assert "neutral-reference price" in momentum_reference_interpretation(entry)[0]


def test_unavailable_reference_and_missing_current_rsi() -> None:
    entry = rank_stocks(
        (
            analysis_result(
                recommendation(),
                momentum_reference=momentum_reference(pct=None, current_rsi=None, status=MomentumReferenceStatus.UNAVAILABLE),
            ),
        ),
        (),
        config(),
        NOW,
    ).entries[0]

    assert entry.current_rsi is None
    assert entry.momentum_sentiment_position == MomentumSentimentPosition.UNAVAILABLE
    assert "does not have a usable" in momentum_reference_interpretation(entry)[0]


def test_momentum_sentiment_boundaries_and_non_finite_values() -> None:
    cfg = config()

    assert classify_momentum_sentiment_position(10.0, cfg) == MomentumSentimentPosition.WELL_ABOVE_NEUTRAL_REFERENCE
    assert classify_momentum_sentiment_position(3.0, cfg) == MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE
    assert classify_momentum_sentiment_position(-3.0, cfg) == MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE
    assert classify_momentum_sentiment_position(-10.0, cfg) == MomentumSentimentPosition.WELL_BELOW_NEUTRAL_REFERENCE
    assert classify_momentum_sentiment_position(float("nan"), cfg) == MomentumSentimentPosition.UNAVAILABLE


def test_momentum_reference_display_does_not_change_score_or_order() -> None:
    lite = analysis_result(recommendation("LITE"), momentum_reference=None)
    mu = analysis_result(
        recommendation(
            "MU",
            RecommendationV2Decision.SELL,
            ValuationCondition.SIGNIFICANTLY_OVERVALUED,
            EvidenceQuality.HIGH,
            current_vs_base_pct=22.81,
        ),
        momentum_reference=None,
    )
    baseline = rank_stocks((lite, mu), (), config(), NOW)
    with_reference = rank_stocks(
        (
            analysis_result(recommendation("LITE"), momentum_reference=momentum_reference("LITE", pct=20.0)),
            analysis_result(
                recommendation(
                    "MU",
                    RecommendationV2Decision.SELL,
                    ValuationCondition.SIGNIFICANTLY_OVERVALUED,
                    EvidenceQuality.HIGH,
                    current_vs_base_pct=22.81,
                ),
                momentum_reference=momentum_reference("MU", RsiCrossDirection.CROSS_BELOW, -12.96, 41.01),
            ),
        ),
        (),
        config(),
        NOW,
    )

    assert [entry.symbol for entry in with_reference.entries] == [entry.symbol for entry in baseline.entries]
    assert [entry.normalized_score for entry in with_reference.entries] == [entry.normalized_score for entry in baseline.entries]


def interpretation_for(direction: RsiCrossDirection, pct: float) -> str:
    entry = rank_stocks(
        (
            analysis_result(
                recommendation("NVDA"),
                momentum_reference=momentum_reference("NVDA", direction, pct),
            ),
        ),
        (),
        config(),
        NOW,
    ).entries[0]
    return momentum_reference_interpretation(entry)[0]


def test_cross_below_zero_uses_neutral_interpretation() -> None:
    text = interpretation_for(RsiCrossDirection.CROSS_BELOW, 0.0)

    assert "neutral-reference price" in text
    assert "recovered" not in text
    assert "above" not in text
    assert "below" not in text


def test_cross_above_zero_uses_neutral_interpretation() -> None:
    text = interpretation_for(RsiCrossDirection.CROSS_ABOVE, 0.0)

    assert "neutral-reference price" in text
    assert "failed" not in text
    assert "above" not in text
    assert "below" not in text


def test_cross_below_plus_three_uses_neutral_interpretation() -> None:
    text = interpretation_for(RsiCrossDirection.CROSS_BELOW, 3.0)

    assert "3.00%" in text
    assert "neutral-reference price" in text
    assert "recovered" not in text


def test_cross_above_minus_three_uses_neutral_interpretation() -> None:
    text = interpretation_for(RsiCrossDirection.CROSS_ABOVE, -3.0)

    assert "3.00%" in text
    assert "neutral-reference price" in text
    assert "failed" not in text


def test_values_just_outside_neutral_band_use_directional_interpretation() -> None:
    cross_below_above = interpretation_for(RsiCrossDirection.CROSS_BELOW, 3.01)
    cross_above_below = interpretation_for(RsiCrossDirection.CROSS_ABOVE, -3.01)

    assert "recovered" in cross_below_above
    assert "above" in cross_below_above
    assert "failed" in cross_above_below
    assert "below" in cross_above_below


def test_boundary_interpretation_change_does_not_change_score_or_order() -> None:
    baseline = rank_stocks(
        (
            analysis_result(recommendation("LITE"), momentum_reference=momentum_reference("LITE", pct=12.0)),
            analysis_result(recommendation("NVDA"), momentum_reference=momentum_reference("NVDA", RsiCrossDirection.CROSS_BELOW, 0.0)),
        ),
        (),
        config(),
        NOW,
    )
    interpreted = [momentum_reference_interpretation(entry) for entry in baseline.entries]

    assert interpreted
    assert [entry.symbol for entry in baseline.entries] == ["LITE", "NVDA"]
    assert [entry.normalized_score for entry in baseline.entries] == [
        baseline.entries[0].normalized_score,
        baseline.entries[1].normalized_score,
    ]
