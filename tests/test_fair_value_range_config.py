import pytest

from src.config.fair_value_range import (
    FairValueRangeConfigurationError,
    load_fair_value_range_configuration,
    parse_fair_value_range_configuration,
)


def document(**overrides):
    defaults = {
        "enabled": True,
        "include_reference_values": True,
        "include_low_confidence_intrinsic": True,
        "exclude_outliers": True,
        "base_method": "confidence_weighted_median",
        "conservative_method": "lower_support",
        "optimistic_method": "upper_intrinsic_support",
        "high_confidence_weight": 1.0,
        "medium_confidence_weight": 0.75,
        "low_confidence_weight": 0.5,
        "unknown_confidence_weight": 0.25,
        "minimum_intrinsic_models": 2,
        "reference_value_weight": 0.5,
        "market_expectation_in_intrinsic_range": False,
        "show_market_expectation_separately": True,
        "show_momentum_reference_separately": True,
        "deep_undervalued_pct": -30,
        "undervalued_pct": -10,
        "near_fair_upper_pct": 10,
        "above_fair_pct": 20,
    }
    defaults.update(overrides)
    return {"defaults": defaults}


def test_parse_defaults() -> None:
    result = parse_fair_value_range_configuration(document())

    assert result.enabled is True
    assert result.high_confidence_weight == 1.0
    assert result.base_method.value == "CONFIDENCE_WEIGHTED_MEDIAN"


def test_load_yaml(tmp_path) -> None:
    path = tmp_path / "range.yaml"
    path.write_text(
        """
defaults:
  enabled: true
  include_reference_values: true
  include_low_confidence_intrinsic: true
  exclude_outliers: true
  base_method: confidence_weighted_median
  conservative_method: lower_support
  optimistic_method: upper_intrinsic_support
  high_confidence_weight: 1.0
  medium_confidence_weight: 0.75
  low_confidence_weight: 0.5
  unknown_confidence_weight: 0.25
  minimum_intrinsic_models: 2
  reference_value_weight: 0.5
  market_expectation_in_intrinsic_range: false
  show_market_expectation_separately: true
  show_momentum_reference_separately: true
  deep_undervalued_pct: -30
  undervalued_pct: -10
  near_fair_upper_pct: 10
  above_fair_pct: 20
""",
        encoding="utf-8",
    )

    assert load_fair_value_range_configuration(path).enabled is True


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"enabled": "true"}, "enabled"),
        ({"base_method": "mean"}, "base_method"),
        ({"high_confidence_weight": 0}, "high_confidence_weight"),
        ({"minimum_intrinsic_models": 0}, "minimum_intrinsic_models"),
        ({"undervalued_pct": -40}, "thresholds"),
    ],
)
def test_validation_errors(overrides, match) -> None:
    with pytest.raises(FairValueRangeConfigurationError, match=match):
        parse_fair_value_range_configuration(document(**overrides))
