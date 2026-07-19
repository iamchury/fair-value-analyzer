from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.analysis.agreement_engine import AgreementLevel, OutlierStatus
from src.analysis.fair_value_range import FairValueRangeStatus
from src.analysis.momentum_reference import MomentumReferenceStatus, RsiCrossDirection
from src.analysis.recommendation_v2 import (
    EvidenceQuality,
    MomentumCondition,
    RecommendationAlignment,
    RecommendationV2Decision,
    ValuationCondition,
    calculate_recommendation_v2,
    classify_momentum_condition,
    classify_valuation_condition,
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
from src.config.recommendation_v2 import (
    MomentumConditionThresholds,
    RecommendationV2Configuration,
    ValuationConditionThresholds,
)


GENERATED = datetime(2026, 7, 18, tzinfo=timezone.utc)


def config(minimum_intrinsic_models=2):
    return RecommendationV2Configuration(
        enabled=True,
        minimum_intrinsic_models=minimum_intrinsic_models,
        valuation_thresholds=ValuationConditionThresholds(-30.0, -15.0, -10.0, 10.0, 20.0, 30.0),
        momentum_thresholds=MomentumConditionThresholds(60.0, 50.0, 45.0, 35.0, 5.0, -5.0, -15.0),
        require_agreement_for_strong_buy=True,
        require_agreement_for_sell=True,
    )


def fair_range(current_vs_base, status=FairValueRangeStatus.COMPLETE, core_count=2):
    return SimpleNamespace(
        symbol="MU",
        status=status,
        current_price=848.95,
        conservative_value=618.10,
        base_value=691.27,
        optimistic_intrinsic_value=691.27,
        current_vs_base_pct=current_vs_base,
        core_model_count=core_count,
        supporting_reference_count=1,
    )


def agreement(core=AgreementLevel.STRONG, extended=AgreementLevel.MODERATE, analyst=True):
    return SimpleNamespace(
        core_intrinsic_agreement=core,
        extended_intrinsic_agreement=extended,
        market_expectation_analyses=(
            SimpleNamespace(
                selected_value=1428.52,
                outlier_status=OutlierStatus.OUTLIER,
                confidence=ValuationConfidenceLevel.LOW,
            ),
        )
        if analyst
        else (),
    )


def momentum(rsi=41.01, pct=-12.96, status=MomentumReferenceStatus.COMPLETE):
    return SimpleNamespace(
        status=status,
        current_rsi=rsi,
        reference_price=975.41,
        price_change_since_reference_pct=pct,
        cross_direction=RsiCrossDirection.CROSS_BELOW,
    )


def collection(confidences=(ValuationConfidenceLevel.LOW, ValuationConfidenceLevel.HIGH)):
    snapshots = []
    for index, confidence in enumerate(confidences):
        snapshots.append(
            ValuationSnapshot(
                symbol="MU",
                model_type=(ValuationModelType.AUTOMATIC_PER if index == 0 else ValuationModelType.RESEARCH_PER),
                model_name=f"model-{index}",
                value_type=ValuationValueType.INTRINSIC_VALUE,
                status=ValuationSnapshotStatus.COMPLETE,
                confidence=confidence,
                raw_fair_value=691.27,
                adjusted_fair_value=691.27,
                selected_fair_value=691.27,
                currency="USD",
                valuation_date=None,
                source_as_of=None,
                generated_at=GENERATED,
                methodology="method",
                rationale=None,
                assumptions={},
                metrics={},
                warnings=(),
                calculation_steps=(),
            )
        )
    return ValuationSnapshotCollection("MU", tuple(snapshots), GENERATED)


def result(
    current_vs_base,
    rsi=55.0,
    momentum_pct=0.0,
    core=AgreementLevel.STRONG,
    confidences=(ValuationConfidenceLevel.LOW, ValuationConfidenceLevel.HIGH),
    legacy=ValuationRecommendation.HOLD,
):
    return calculate_recommendation_v2(
        "MU",
        config(),
        fair_range(current_vs_base),
        agreement(core),
        momentum(rsi, momentum_pct),
        collection(confidences),
        legacy,
        generated_at=GENERATED,
    )


@pytest.mark.parametrize(
    ("pct", "condition"),
    [
        (-30.0, ValuationCondition.DEEPLY_UNDERVALUED),
        (-15.0, ValuationCondition.UNDERVALUED),
        (-10.01, ValuationCondition.SLIGHTLY_UNDERVALUED),
        (-10.0, ValuationCondition.NEAR_FAIR_VALUE),
        (10.0, ValuationCondition.NEAR_FAIR_VALUE),
        (20.0, ValuationCondition.MODERATELY_OVERVALUED),
        (30.0, ValuationCondition.SIGNIFICANTLY_OVERVALUED),
        (30.01, ValuationCondition.EXTREMELY_OVERVALUED),
    ],
)
def test_exact_valuation_boundaries(pct, condition) -> None:
    assert classify_valuation_condition(fair_range(pct), config()) == condition


@pytest.mark.parametrize(
    ("rsi", "pct", "condition"),
    [
        (35.0, 0.0, MomentumCondition.STRONG_NEGATIVE),
        (60.0, 5.0, MomentumCondition.STRONG_POSITIVE),
        (50.0, 0.0, MomentumCondition.POSITIVE),
        (49.0, 5.01, MomentumCondition.POSITIVE),
        (44.99, 0.0, MomentumCondition.WEAK),
        (46.0, -5.01, MomentumCondition.WEAK),
        (46.0, 0.0, MomentumCondition.NEUTRAL),
    ],
)
def test_exact_rsi_boundaries(rsi, pct, condition) -> None:
    assert classify_momentum_condition(momentum(rsi, pct), config()) == condition


def test_mu_fixture_recommendation_v2() -> None:
    rec = calculate_recommendation_v2(
        "MU",
        config(),
        fair_range(22.81),
        agreement(),
        momentum(),
        collection(),
        ValuationRecommendation.SELL,
        generated_at=GENERATED,
    )

    assert rec.valuation_condition == ValuationCondition.SIGNIFICANTLY_OVERVALUED
    assert rec.momentum_condition == MomentumCondition.WEAK
    assert rec.evidence_quality == EvidenceQuality.HIGH
    assert rec.decision == RecommendationV2Decision.SELL
    assert rec.alignment == RecommendationAlignment.ALIGNED
    assert "does not override" in " ".join(rec.rationale)


def test_deeply_undervalued_positive_momentum_is_strong_buy() -> None:
    assert result(-35.0, rsi=65.0, momentum_pct=10.0).decision == RecommendationV2Decision.STRONG_BUY


def test_deeply_undervalued_weak_momentum_is_buy() -> None:
    assert result(-35.0, rsi=44.0).decision == RecommendationV2Decision.BUY


def test_deeply_undervalued_strong_negative_momentum_is_accumulate() -> None:
    assert result(-35.0, rsi=30.0).decision == RecommendationV2Decision.ACCUMULATE


def test_undervalued_weak_momentum_is_accumulate() -> None:
    assert result(-20.0, rsi=44.0).decision == RecommendationV2Decision.ACCUMULATE


def test_slightly_undervalued_requires_positive_momentum_for_accumulate() -> None:
    assert result(-12.0, rsi=55.0).decision == RecommendationV2Decision.ACCUMULATE
    assert result(-12.0, rsi=46.0).decision == RecommendationV2Decision.HOLD


def test_near_fair_value_momentum_cases() -> None:
    assert result(0.0, rsi=65.0, momentum_pct=10.0).decision == RecommendationV2Decision.ACCUMULATE
    assert result(0.0, rsi=44.0).decision == RecommendationV2Decision.HOLD
    assert result(0.0, rsi=30.0).decision == RecommendationV2Decision.REDUCE


def test_moderately_overvalued_strong_positive_momentum_is_hold() -> None:
    assert result(15.0, rsi=65.0, momentum_pct=10.0).decision == RecommendationV2Decision.HOLD


def test_significantly_overvalued_weak_momentum_is_sell() -> None:
    assert result(22.81, rsi=41.01, momentum_pct=-12.96).decision == RecommendationV2Decision.SELL


def test_extremely_overvalued_is_sell_with_medium_or_high_evidence() -> None:
    assert result(45.0).decision == RecommendationV2Decision.SELL


def test_conflicted_agreement_caps_bullish_and_bearish_decisions() -> None:
    assert result(-35.0, core=AgreementLevel.CONFLICTED).decision == RecommendationV2Decision.ACCUMULATE
    assert result(45.0, core=AgreementLevel.CONFLICTED).decision == RecommendationV2Decision.REDUCE


def test_insufficient_intrinsic_models_blocks_decision() -> None:
    rec = calculate_recommendation_v2(
        "MU",
        config(),
        fair_range(-35.0, core_count=1),
        agreement(),
        momentum(65.0, 10.0),
        collection((ValuationConfidenceLevel.HIGH,)),
        ValuationRecommendation.BUY,
        generated_at=GENERATED,
    )

    assert rec.decision == RecommendationV2Decision.INSUFFICIENT_DATA
    assert rec.evidence_quality == EvidenceQuality.INSUFFICIENT


def test_momentum_unavailable_does_not_block_valuation_decision() -> None:
    rec = calculate_recommendation_v2(
        "MU",
        config(),
        fair_range(-20.0),
        agreement(),
        None,
        collection(),
        ValuationRecommendation.HOLD,
        generated_at=GENERATED,
    )

    assert rec.momentum_condition == MomentumCondition.UNAVAILABLE
    assert rec.decision == RecommendationV2Decision.ACCUMULATE


def test_analyst_unavailable_warns_but_does_not_block() -> None:
    rec = calculate_recommendation_v2(
        "MU",
        config(),
        fair_range(-20.0),
        agreement(analyst=False),
        momentum(55.0, 0.0),
        collection(),
        ValuationRecommendation.HOLD,
        generated_at=GENERATED,
    )

    assert rec.decision == RecommendationV2Decision.BUY
    assert rec.analyst_expectation is None
    assert "Analyst consensus context is unavailable." in rec.warnings


def test_only_low_confidence_intrinsic_models_reduce_evidence() -> None:
    rec = result(-35.0, confidences=(ValuationConfidenceLevel.LOW, ValuationConfidenceLevel.LOW))

    assert rec.evidence_quality == EvidenceQuality.LOW
    assert rec.decision == RecommendationV2Decision.ACCUMULATE


def test_one_high_and_one_low_intrinsic_model_gives_high_evidence() -> None:
    assert result(0.0).evidence_quality == EvidenceQuality.HIGH


def test_legacy_alignment_cases() -> None:
    assert result(22.81, rsi=41.01, legacy=ValuationRecommendation.SELL).alignment == RecommendationAlignment.ALIGNED
    assert result(-20.0, legacy=ValuationRecommendation.HOLD).alignment == RecommendationAlignment.V2_MORE_BULLISH
    assert result(22.81, rsi=41.01, legacy=ValuationRecommendation.HOLD).alignment == RecommendationAlignment.V2_MORE_BEARISH


def test_deterministic_rationale() -> None:
    first = result(22.81, rsi=41.01, momentum_pct=-12.96, legacy=ValuationRecommendation.SELL)
    second = result(22.81, rsi=41.01, momentum_pct=-12.96, legacy=ValuationRecommendation.SELL)

    assert first.rationale == second.rationale
