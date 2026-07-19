import pytest

from src.config.ranking_engine import (
    RankingEngineConfigurationError,
    load_ranking_engine_configuration,
    parse_ranking_engine_configuration,
)


def document(**overrides):
    values = {
        "enabled": True,
        "weights": {
            "valuation": 45,
            "recommendation": 20,
            "evidence": 15,
            "agreement": 10,
            "momentum": 10,
        },
        "momentum_reference_display": {
            "enabled": True,
            "near_reference_pct": 3,
            "well_above_reference_pct": 10,
            "well_below_reference_pct": -10,
            "show_reference_date": True,
            "show_cross_direction": True,
            "show_current_rsi": True,
            "show_price_difference": True,
            "affect_ranking_score": False,
        },
    }
    values.update(overrides)
    return values


def test_parse_default_ranking_configuration() -> None:
    config = parse_ranking_engine_configuration(document())

    assert config.enabled is True
    assert config.weights.valuation == 45.0
    assert config.weights.total == 100.0
    assert config.momentum_reference_display.affect_ranking_score is False


def test_load_ranking_configuration_from_yaml(tmp_path) -> None:
    path = tmp_path / "ranking.yaml"
    path.write_text(
        "enabled: true\nweights:\n  valuation: 45\n  recommendation: 20\n  evidence: 15\n  agreement: 10\n  momentum: 10\nmomentum_reference_display:\n  enabled: true\n  near_reference_pct: 3\n  well_above_reference_pct: 10\n  well_below_reference_pct: -10\n  show_reference_date: true\n  show_cross_direction: true\n  show_current_rsi: true\n  show_price_difference: true\n  affect_ranking_score: false\n",
        encoding="utf-8",
    )

    assert load_ranking_engine_configuration(path).weights.momentum == 10.0


@pytest.mark.parametrize(
    "bad_document, message",
    [
        ({}, "enabled"),
        (document(weights={"valuation": 1}), "agreement"),
        (document(extra=True), "extra"),
        (document(enabled="yes"), "boolean"),
        (document(weights={"valuation": 0, "recommendation": 1, "evidence": 1, "agreement": 1, "momentum": 1}), "positive"),
        (document(momentum_reference_display={"enabled": True}), "affect_ranking_score"),
        (
            document(
                momentum_reference_display={
                    "enabled": True,
                    "near_reference_pct": 3,
                    "well_above_reference_pct": 10,
                    "well_below_reference_pct": -10,
                    "show_reference_date": True,
                    "show_cross_direction": True,
                    "show_current_rsi": True,
                    "show_price_difference": True,
                    "affect_ranking_score": True,
                }
            ),
            "must remain false",
        ),
    ],
)
def test_invalid_ranking_configuration_raises(bad_document, message: str) -> None:
    with pytest.raises(RankingEngineConfigurationError, match=message):
        parse_ranking_engine_configuration(bad_document)
