from datetime import datetime, timezone

import pytest

from src.analysis.analyst_consensus import (
    AnalystConsensusInputs,
    AnalystDispersionClassification,
    calculate_analyst_consensus,
)
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.config.analyst_consensus import AnalystConsensusRule, AnalystValuationMethod


def rule(**overrides) -> AnalystConsensusRule:
    values = {
        "enabled": True,
        "valuation_method": AnalystValuationMethod.WEIGHTED_MEAN_MIDPOINT,
        "mean_weight": 0.7,
        "midpoint_weight": 0.3,
        "apply_treasury": False,
        "low_dispersion": 25.0,
        "medium_dispersion": 60.0,
        "high_dispersion": 100.0,
        "rationale": "rationale",
    }
    values.update(overrides)
    return AnalystConsensusRule(**values)


def inputs(**overrides) -> AnalystConsensusInputs:
    values = {
        "symbol": "MU",
        "current_price": 848.95,
        "target_mean": 1489.57,
        "target_high": 2200.0,
        "target_low": 361.0,
        "currency": "USD",
        "source_timestamp": datetime(2026, 7, 18, tzinfo=timezone.utc),
        "treasury_multiplier": 0.9419,
        "rule": rule(),
    }
    values.update(overrides)
    return AnalystConsensusInputs(**values)


def test_weighted_mu_like_snapshot_is_extreme_low_confidence() -> None:
    snapshot = calculate_analyst_consensus(inputs())

    assert snapshot.model_type == ValuationModelType.ANALYST_CONSENSUS
    assert snapshot.value_type == ValuationValueType.MARKET_EXPECTATION
    assert snapshot.status == ValuationSnapshotStatus.COMPLETE
    assert snapshot.confidence == ValuationConfidenceLevel.LOW
    assert snapshot.raw_fair_value == pytest.approx(1426.849)
    assert snapshot.adjusted_fair_value == pytest.approx(1426.849)
    assert snapshot.selected_fair_value == pytest.approx(1426.849)
    assert snapshot.metrics["target_midpoint"] == 1280.5
    assert snapshot.metrics["dispersion_percent"] == pytest.approx(123.46, abs=0.01)
    assert snapshot.metrics["dispersion_classification"] == "EXTREME"
    assert snapshot.methodology == "Weighted Mean / Midpoint"
    assert snapshot.warnings == ("Analyst target dispersion is extreme.",)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        (AnalystValuationMethod.MEAN, 1489.57),
        (AnalystValuationMethod.MIDPOINT, 1280.5),
        (AnalystValuationMethod.WEIGHTED_MEAN_MIDPOINT, 1426.849),
    ],
)
def test_valuation_methods(method, expected) -> None:
    snapshot = calculate_analyst_consensus(inputs(rule=rule(valuation_method=method)))

    assert snapshot.raw_fair_value == pytest.approx(expected)


def test_treasury_enabled_applies_multiplier() -> None:
    snapshot = calculate_analyst_consensus(
        inputs(rule=rule(apply_treasury=True))
    )

    assert snapshot.metrics["treasury_applied"] is True
    assert snapshot.selected_fair_value == pytest.approx(1426.849 * 0.9419)


@pytest.mark.parametrize(
    ("target_low", "target_high", "target_mean", "classification", "confidence"),
    [
        (90.0, 110.0, 100.0, AnalystDispersionClassification.LOW, ValuationConfidenceLevel.HIGH),
        (75.0, 125.0, 100.0, AnalystDispersionClassification.MEDIUM, ValuationConfidenceLevel.MEDIUM),
        (55.0, 145.0, 100.0, AnalystDispersionClassification.HIGH, ValuationConfidenceLevel.LOW),
        (40.0, 160.0, 100.0, AnalystDispersionClassification.EXTREME, ValuationConfidenceLevel.LOW),
    ],
)
def test_dispersion_classification_and_confidence(
    target_low,
    target_high,
    target_mean,
    classification,
    confidence,
) -> None:
    snapshot = calculate_analyst_consensus(
        inputs(
            target_low=target_low,
            target_high=target_high,
            target_mean=target_mean,
        )
    )

    assert snapshot.metrics["dispersion_classification"] == classification.value
    assert snapshot.confidence == confidence


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_low": 100.0, "target_high": 90.0},
        {"target_mean": 50.0, "target_low": 100.0},
        {"target_mean": 300.0, "target_high": 200.0},
    ],
)
def test_invalid_ordering_returns_partial_snapshot_without_value(overrides) -> None:
    snapshot = calculate_analyst_consensus(inputs(**overrides))

    assert snapshot.status == ValuationSnapshotStatus.PARTIAL
    assert snapshot.selected_fair_value is None
    assert snapshot.confidence == ValuationConfidenceLevel.LOW
    assert snapshot.warnings


def test_incomplete_data_never_gets_high_confidence() -> None:
    snapshot = calculate_analyst_consensus(inputs(target_high=None))

    assert snapshot.status == ValuationSnapshotStatus.PARTIAL
    assert snapshot.confidence == ValuationConfidenceLevel.LOW


def test_disabled_model_is_unavailable_snapshot() -> None:
    snapshot = calculate_analyst_consensus(inputs(rule=rule(enabled=False)))

    assert snapshot.status == ValuationSnapshotStatus.UNAVAILABLE
    assert snapshot.confidence == ValuationConfidenceLevel.UNKNOWN
