from datetime import datetime, timedelta, timezone

import pytest

from src.analysis.analyst_consensus import (
    AnalystConsensusInputs,
    AnalystConsensusQuality,
    AnalystConsensusStatus,
    AnalystDispersionLevel,
    StaleStatus,
    calculate_analyst_consensus,
)
from src.config.analyst_consensus import AnalystConsensusRule, AnalystFairValueMethod


def rule(**overrides) -> AnalystConsensusRule:
    values = {
        "enabled": True,
        "fair_value_method": AnalystFairValueMethod.WEIGHTED_MEAN_MIDPOINT,
        "mean_weight": 0.7,
        "midpoint_weight": 0.3,
        "apply_treasury_multiplier": False,
        "low_dispersion_threshold_percent": 25.0,
        "medium_dispersion_threshold_percent": 60.0,
        "extreme_dispersion_threshold_percent": 100.0,
        "stale_after_days": 180,
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
        "analyst_count": None,
        "source_timestamp": datetime(2026, 7, 18, tzinfo=timezone.utc),
        "treasury_multiplier": 0.9419,
        "rule": rule(),
    }
    values.update(overrides)
    return AnalystConsensusInputs(**values)


def test_weighted_mu_like_extreme_unreliable_result() -> None:
    result = calculate_analyst_consensus(inputs())

    assert result.status == AnalystConsensusStatus.PARTIAL
    assert result.target_midpoint == 1280.5
    assert result.raw_analyst_fair_value == pytest.approx(1426.849)
    assert result.adjusted_analyst_fair_value == pytest.approx(1426.849)
    assert result.dispersion_percent == pytest.approx(123.46, abs=0.01)
    assert result.dispersion_level == AnalystDispersionLevel.EXTREME
    assert result.consensus_quality == AnalystConsensusQuality.UNRELIABLE
    assert result.stale_status == StaleStatus.UNKNOWN
    assert result.warnings


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        (AnalystFairValueMethod.MEAN, 1489.57),
        (AnalystFairValueMethod.MIDPOINT, 1280.5),
        (AnalystFairValueMethod.WEIGHTED_MEAN_MIDPOINT, 1426.849),
    ],
)
def test_fair_value_methods(method, expected) -> None:
    result = calculate_analyst_consensus(inputs(rule=rule(fair_value_method=method)))
    assert result.raw_analyst_fair_value == pytest.approx(expected)


def test_treasury_enabled_applies_multiplier() -> None:
    result = calculate_analyst_consensus(
        inputs(rule=rule(apply_treasury_multiplier=True))
    )
    assert result.treasury_applied is True
    assert result.adjusted_analyst_fair_value == pytest.approx(1426.849 * 0.9419)


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_low": 100.0, "target_high": 90.0},
        {"target_mean": 50.0, "target_low": 100.0},
        {"target_mean": 300.0, "target_high": 200.0},
    ],
)
def test_invalid_ordering_unavailable(overrides) -> None:
    result = calculate_analyst_consensus(inputs(**overrides))
    assert result.status == AnalystConsensusStatus.UNAVAILABLE
    assert result.consensus_quality == AnalystConsensusQuality.UNRELIABLE
    assert result.adjusted_analyst_fair_value is None


def test_quality_strong_and_stale_weak() -> None:
    fresh = datetime(2026, 7, 1, tzinfo=timezone.utc)
    strong = calculate_analyst_consensus(
        inputs(
            target_mean=100,
            target_low=90,
            target_high=110,
            analyst_count=12,
            analyst_target_as_of=fresh,
        )
    )
    assert strong.consensus_quality == AnalystConsensusQuality.STRONG
    stale = calculate_analyst_consensus(
        inputs(
            target_mean=100,
            target_low=90,
            target_high=110,
            analyst_count=12,
            analyst_target_as_of=fresh - timedelta(days=181),
        )
    )
    assert stale.stale_status == StaleStatus.STALE
    assert stale.consensus_quality == AnalystConsensusQuality.WEAK


def test_invalid_numbers_become_warnings_not_exceptions() -> None:
    result = calculate_analyst_consensus(inputs(target_mean=float("nan")))
    assert result.status == AnalystConsensusStatus.UNAVAILABLE
    assert any("target_mean is invalid" in warning for warning in result.warnings)
