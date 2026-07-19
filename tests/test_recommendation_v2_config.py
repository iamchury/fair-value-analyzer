import pytest

from src.config.recommendation_v2 import (
    RecommendationV2ConfigurationError,
    load_recommendation_v2_configuration,
    parse_recommendation_v2_configuration,
)


def document(**overrides):
    defaults = {
        "enabled": True,
        "minimum_intrinsic_models": 2,
        "valuation_thresholds": {
            "deeply_undervalued_pct": -30,
            "undervalued_pct": -15,
            "slightly_undervalued_pct": -10,
            "near_fair_upper_pct": 10,
            "moderately_overvalued_pct": 20,
            "significantly_overvalued_pct": 30,
        },
        "momentum_thresholds": {
            "strong_positive_rsi": 60,
            "positive_rsi": 50,
            "weak_rsi": 45,
            "strong_negative_rsi": 35,
            "positive_reference_pct": 5,
            "negative_reference_pct": -5,
            "severe_negative_reference_pct": -15,
        },
        "require_agreement_for_strong_buy": True,
        "require_agreement_for_sell": True,
    }
    defaults.update(overrides)
    return {"defaults": defaults}


def test_parse_defaults() -> None:
    config = parse_recommendation_v2_configuration(document())

    assert config.enabled is True
    assert config.minimum_intrinsic_models == 2
    assert config.valuation_thresholds.deeply_undervalued_pct == -30
    assert config.momentum_thresholds.strong_positive_rsi == 60


def test_load_yaml(tmp_path) -> None:
    path = tmp_path / "recommendation_v2.yaml"
    path.write_text(
        """
defaults:
  enabled: true
  minimum_intrinsic_models: 2
  valuation_thresholds:
    deeply_undervalued_pct: -30
    undervalued_pct: -15
    slightly_undervalued_pct: -10
    near_fair_upper_pct: 10
    moderately_overvalued_pct: 20
    significantly_overvalued_pct: 30
  momentum_thresholds:
    strong_positive_rsi: 60
    positive_rsi: 50
    weak_rsi: 45
    strong_negative_rsi: 35
    positive_reference_pct: 5
    negative_reference_pct: -5
    severe_negative_reference_pct: -15
  require_agreement_for_strong_buy: true
  require_agreement_for_sell: true
""",
        encoding="utf-8",
    )

    assert load_recommendation_v2_configuration(path).enabled is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"enabled": "true"}, "enabled"),
        ({"minimum_intrinsic_models": 0}, "minimum_intrinsic_models"),
        (
            {
                "valuation_thresholds": {
                    "deeply_undervalued_pct": -30,
                    "undervalued_pct": -15,
                    "slightly_undervalued_pct": -20,
                    "near_fair_upper_pct": 10,
                    "moderately_overvalued_pct": 20,
                    "significantly_overvalued_pct": 30,
                }
            },
            "valuation_thresholds",
        ),
        (
            {
                "momentum_thresholds": {
                    "strong_positive_rsi": 60,
                    "positive_rsi": 50,
                    "weak_rsi": 45,
                    "strong_negative_rsi": 35,
                    "positive_reference_pct": -10,
                    "negative_reference_pct": -5,
                    "severe_negative_reference_pct": -15,
                }
            },
            "reference percentages",
        ),
    ],
)
def test_validation_errors(overrides, message) -> None:
    with pytest.raises(RecommendationV2ConfigurationError, match=message):
        parse_recommendation_v2_configuration(document(**overrides))
