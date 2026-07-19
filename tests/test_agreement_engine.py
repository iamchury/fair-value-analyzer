from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.analysis.agreement_engine import (
    AgreementLevel,
    MarketExpectationDirection,
    ModelRelationship,
    OutlierStatus,
    analyze_agreement,
    classify_pairwise_relationship,
    symmetric_percentage_difference,
)
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.config.agreement_engine import AgreementEngineConfiguration
from tests.test_valuation_snapshot import snapshot


GENERATED_AT = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def config(**overrides: object) -> AgreementEngineConfiguration:
    values = {
        "enabled": True,
        "strong_threshold_pct": 10.0,
        "moderate_threshold_pct": 20.0,
        "weak_threshold_pct": 35.0,
        "outlier_threshold_pct": 50.0,
        "extreme_outlier_threshold_pct": 80.0,
        "minimum_primary_models": 2,
        "include_reference_in_intrinsic_cluster": True,
        "market_expectation_affects_overall_agreement": False,
    }
    values.update(overrides)
    return AgreementEngineConfiguration(**values)


def agreement_collection(*items):
    return ValuationSnapshotCollection("MU", tuple(items), GENERATED_AT)


def valuation_snapshot(model, value, value_type, confidence=ValuationConfidenceLevel.MEDIUM):
    return snapshot(
        symbol="MU",
        model_type=model,
        value_type=value_type,
        confidence=confidence,
        raw_fair_value=value,
        adjusted_fair_value=value,
        selected_fair_value=value,
        currency="USD",
        generated_at=GENERATED_AT,
        warnings=(
            ("Analyst target dispersion is extreme.",)
            if model == ValuationModelType.ANALYST_CONSENSUS
            else ()
        ),
    )


def mu_collection() -> ValuationSnapshotCollection:
    return agreement_collection(
        valuation_snapshot(
            ValuationModelType.AUTOMATIC_PER,
            691.27,
            ValuationValueType.INTRINSIC_VALUE,
            ValuationConfidenceLevel.LOW,
        ),
        valuation_snapshot(
            ValuationModelType.RESEARCH_PER,
            691.27,
            ValuationValueType.INTRINSIC_VALUE,
            ValuationConfidenceLevel.HIGH,
        ),
        valuation_snapshot(
            ValuationModelType.DCF_REFERENCE,
            618.10,
            ValuationValueType.REFERENCE_VALUE,
            ValuationConfidenceLevel.MEDIUM,
        ),
        valuation_snapshot(
            ValuationModelType.ANALYST_CONSENSUS,
            1428.52,
            ValuationValueType.MARKET_EXPECTATION,
            ValuationConfidenceLevel.LOW,
        ),
    )


def test_symmetric_percentage_difference_is_order_independent() -> None:
    assert symmetric_percentage_difference(691.27, 618.10) == pytest.approx(11.176, abs=0.001)
    assert symmetric_percentage_difference(618.10, 691.27) == pytest.approx(11.176, abs=0.001)
    assert symmetric_percentage_difference(None, 691.27) is None
    assert symmetric_percentage_difference(0, 691.27) is None
    assert symmetric_percentage_difference(-1, 691.27) is None


@pytest.mark.parametrize(
    ("difference", "expected"),
    [
        (10.0, ModelRelationship.STRONG_AGREEMENT),
        (20.0, ModelRelationship.MODERATE_AGREEMENT),
        (35.0, ModelRelationship.WEAK_AGREEMENT),
        (35.01, ModelRelationship.DIVERGENT),
        (None, ModelRelationship.UNAVAILABLE),
    ],
)
def test_pairwise_classification_boundaries(difference, expected) -> None:
    assert classify_pairwise_relationship(difference, config()) == expected


def test_mu_agreement_snapshot_collection() -> None:
    result = analyze_agreement(mu_collection(), config(), GENERATED_AT)

    assert result.core_intrinsic_agreement == AgreementLevel.STRONG
    assert result.extended_intrinsic_agreement == AgreementLevel.MODERATE
    assert result.overall_agreement == AgreementLevel.STRONG
    assert result.intrinsic_cluster.minimum_value == pytest.approx(618.10)
    assert result.intrinsic_cluster.maximum_value == pytest.approx(691.27)
    assert result.intrinsic_cluster.mean_value == pytest.approx(666.88, abs=0.01)
    assert result.intrinsic_cluster.median_value == pytest.approx(691.27)
    assert result.intrinsic_cluster.spread_percentage == pytest.approx(10.97, abs=0.01)
    analyst = next(
        item
        for item in result.market_expectation_analyses
        if item.model_type == ValuationModelType.ANALYST_CONSENSUS
    )
    assert analyst.direction == MarketExpectationDirection.ABOVE_INTRINSIC
    assert analyst.percentage_difference == pytest.approx(106.65, abs=0.01)
    assert analyst.outlier_status == OutlierStatus.OUTLIER
    dcf = next(item for item in result.model_outliers if item.model_type == ValuationModelType.DCF_REFERENCE)
    assert dcf.status == OutlierStatus.NOT_OUTLIER
    assert dcf.difference_percentage == pytest.approx(10.59, abs=0.01)
    assert "Analyst Consensus is approximately 106.65%" in "\n".join(result.rationale)


def test_missing_reference_and_analyst_still_analyzes_core() -> None:
    result = analyze_agreement(
        agreement_collection(
            valuation_snapshot(
                ValuationModelType.AUTOMATIC_PER,
                100.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
            valuation_snapshot(
                ValuationModelType.RESEARCH_PER,
                108.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
        ),
        config(),
        GENERATED_AT,
    )

    assert result.core_intrinsic_agreement == AgreementLevel.STRONG
    assert result.extended_intrinsic_agreement == AgreementLevel.STRONG
    assert result.market_expectation_analyses == ()


def test_conflicting_intrinsic_snapshots_are_conflicted() -> None:
    result = analyze_agreement(
        agreement_collection(
            valuation_snapshot(
                ValuationModelType.AUTOMATIC_PER,
                100.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
            valuation_snapshot(
                ValuationModelType.RESEARCH_PER,
                200.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
        ),
        config(),
        GENERATED_AT,
    )

    assert result.core_intrinsic_agreement == AgreementLevel.CONFLICTED
    assert result.overall_agreement == AgreementLevel.CONFLICTED


def test_incomplete_models_are_ignored_without_crashing() -> None:
    unavailable = valuation_snapshot(
        ValuationModelType.AUTOMATIC_PER,
        100.0,
        ValuationValueType.INTRINSIC_VALUE,
    )
    unavailable = replace(
        unavailable,
        status=ValuationSnapshotStatus.ERROR,
        selected_fair_value=None,
        raw_fair_value=None,
        adjusted_fair_value=None,
    )
    result = analyze_agreement(
        agreement_collection(
            unavailable,
            valuation_snapshot(
                ValuationModelType.ANALYST_CONSENSUS,
                120.0,
                ValuationValueType.MARKET_EXPECTATION,
            ),
        ),
        config(),
        GENERATED_AT,
    )

    assert result.status.name == "INSUFFICIENT"
    assert result.overall_agreement == AgreementLevel.INSUFFICIENT
    assert result.model_outliers[0].status == OutlierStatus.NOT_EVALUATED


def test_analyst_below_intrinsic_cluster() -> None:
    result = analyze_agreement(
        agreement_collection(
            valuation_snapshot(
                ValuationModelType.AUTOMATIC_PER,
                100.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
            valuation_snapshot(
                ValuationModelType.RESEARCH_PER,
                102.0,
                ValuationValueType.INTRINSIC_VALUE,
            ),
            valuation_snapshot(
                ValuationModelType.ANALYST_CONSENSUS,
                10.0,
                ValuationValueType.MARKET_EXPECTATION,
            ),
        ),
        config(),
        GENERATED_AT,
    )

    assert result.market_expectation_analyses[0].direction == (
        MarketExpectationDirection.BELOW_INTRINSIC
    )
    assert result.market_expectation_analyses[0].outlier_status == OutlierStatus.OUTLIER
