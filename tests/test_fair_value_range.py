from datetime import datetime, timezone

import pytest

from src.analysis.agreement_engine import analyze_agreement
from src.analysis.fair_value_range import (
    MarketPosition,
    calculate_fair_value_range,
    confidence_weight,
)
from src.analysis.valuation_snapshot import ValuationConfidenceLevel, ValuationModelType
from src.config.fair_value_range import FairValueRangeConfiguration
from tests.test_agreement_engine import config as agreement_config
from tests.test_agreement_engine import mu_collection


GENERATED_AT = datetime(2026, 7, 18, tzinfo=timezone.utc)


def config(**overrides):
    values = {
        "enabled": True,
        "include_reference_values": True,
        "include_low_confidence_intrinsic": True,
        "exclude_outliers": True,
        "base_method": "CONFIDENCE_WEIGHTED_MEDIAN",
        "conservative_method": "LOWER_SUPPORT",
        "optimistic_method": "UPPER_INTRINSIC_SUPPORT",
        "high_confidence_weight": 1.0,
        "medium_confidence_weight": 0.75,
        "low_confidence_weight": 0.5,
        "unknown_confidence_weight": 0.25,
        "minimum_intrinsic_models": 2,
        "reference_value_weight": 0.5,
        "market_expectation_in_intrinsic_range": False,
        "show_market_expectation_separately": True,
        "show_momentum_reference_separately": True,
        "deep_undervalued_pct": -30.0,
        "undervalued_pct": -10.0,
        "near_fair_upper_pct": 10.0,
        "above_fair_pct": 20.0,
    }
    values.update(overrides)
    from src.config.fair_value_range import (
        ConservativeRangeMethod,
        OptimisticRangeMethod,
        RangeBaseMethod,
    )

    values["base_method"] = RangeBaseMethod(values["base_method"])
    values["conservative_method"] = ConservativeRangeMethod(values["conservative_method"])
    values["optimistic_method"] = OptimisticRangeMethod(values["optimistic_method"])
    return FairValueRangeConfiguration(**values)


def test_mu_fair_value_range_keeps_analyst_separate() -> None:
    collection = mu_collection()
    agreement = analyze_agreement(collection, agreement_config(), GENERATED_AT)

    result = calculate_fair_value_range(
        collection,
        agreement,
        848.95,
        config(),
        generated_at=GENERATED_AT,
    )

    assert result.conservative_value == pytest.approx(618.10)
    assert result.base_value == pytest.approx(691.27)
    assert result.optimistic_intrinsic_value == pytest.approx(691.27)
    assert result.intrinsic_floor == pytest.approx(618.10)
    assert result.intrinsic_ceiling == pytest.approx(691.27)
    assert result.intrinsic_range_width == pytest.approx(73.17)
    assert result.intrinsic_range_width_pct == pytest.approx(10.59, abs=0.01)
    assert result.current_vs_base_pct == pytest.approx(22.81, abs=0.01)
    assert result.market_position == MarketPosition.SIGNIFICANTLY_OVERVALUED
    assert result.market_expectation_value == pytest.approx(1428.52)
    assert result.market_expectation_outlier_status.value == "OUTLIER"
    assert ValuationModelType.ANALYST_CONSENSUS not in [item.model_type for item in result.included_models]


def test_confidence_weights_and_unknown_policy() -> None:
    cfg = config()

    assert confidence_weight(ValuationConfidenceLevel.HIGH, cfg) == 1.0
    assert confidence_weight(ValuationConfidenceLevel.MEDIUM, cfg) == 0.75
    assert confidence_weight(ValuationConfidenceLevel.LOW, cfg) == 0.5
    assert confidence_weight(ValuationConfidenceLevel.UNKNOWN, cfg) == 0.25


@pytest.mark.parametrize(
    ("pct", "position"),
    [
        (-30.0, MarketPosition.DEEPLY_UNDERVALUED),
        (-10.01, MarketPosition.UNDERVALUED),
        (-10.0, MarketPosition.NEAR_FAIR_VALUE),
        (10.0, MarketPosition.NEAR_FAIR_VALUE),
        (20.0, MarketPosition.ABOVE_FAIR_VALUE),
        (20.01, MarketPosition.SIGNIFICANTLY_OVERVALUED),
    ],
)
def test_market_position_boundaries(pct, position) -> None:
    current = 691.27 * (1 + pct / 100)
    collection = mu_collection()
    agreement = analyze_agreement(collection, agreement_config(), GENERATED_AT)
    result = calculate_fair_value_range(
        collection,
        agreement,
        current,
        config(),
        generated_at=GENERATED_AT,
    )

    assert result.market_position == position
