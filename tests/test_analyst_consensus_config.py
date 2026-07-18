from math import inf, nan

import pytest

from src.config.analyst_consensus import (
    AnalystConsensusConfigurationError,
    AnalystFairValueMethod,
    load_analyst_consensus_configuration,
    parse_analyst_consensus_configuration,
)


def document(**overrides):
    data = {
        "defaults": {
            "enabled": True,
            "fair_value_method": "weighted_mean_midpoint",
            "mean_weight": 0.7,
            "midpoint_weight": 0.3,
            "apply_treasury_multiplier": False,
            "low_dispersion_threshold_percent": 25.0,
            "medium_dispersion_threshold_percent": 60.0,
            "extreme_dispersion_threshold_percent": 100.0,
            "stale_after_days": 180,
        },
        "symbols": {"mu": {"rationale": " wide "}},
    }
    data.update(overrides)
    return data


def test_repository_yaml_loads_and_symbol_inherits_defaults() -> None:
    config = load_analyst_consensus_configuration()

    assert config.default_rule.fair_value_method == AnalystFairValueMethod.WEIGHTED_MEAN_MIDPOINT
    assert config.symbol_rules["MU"].mean_weight == 0.7
    assert config.symbol_rules["MU"].rationale == "Treat the wide analyst target range conservatively."
    with pytest.raises(TypeError):
        config.symbol_rules["X"] = config.default_rule


@pytest.mark.parametrize("method", ["mean", "midpoint", "weighted_mean_midpoint"])
def test_all_methods_load(method: str) -> None:
    data = document()
    data["defaults"]["fair_value_method"] = method
    assert parse_analyst_consensus_configuration(data).default_rule


@pytest.mark.parametrize(
    "bad",
    [
        {"bad": {}},
        document(extra=True),
        document(symbols={"mu": {}, "MU": {}}),
    ],
)
def test_invalid_documents_raise(bad) -> None:
    with pytest.raises(AnalystConsensusConfigurationError):
        parse_analyst_consensus_configuration(bad)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fair_value_method", "median"),
        ("enabled", 1),
        ("mean_weight", True),
        ("mean_weight", -0.1),
        ("mean_weight", 1.1),
        ("mean_weight", nan),
        ("mean_weight", inf),
        ("low_dispersion_threshold_percent", 0.0),
        ("medium_dispersion_threshold_percent", 10.0),
        ("extreme_dispersion_threshold_percent", 1001.0),
        ("stale_after_days", True),
        ("stale_after_days", 0),
    ],
)
def test_invalid_default_values_raise(key, value) -> None:
    data = document()
    data["defaults"][key] = value
    with pytest.raises(AnalystConsensusConfigurationError):
        parse_analyst_consensus_configuration(data)


def test_weight_sum_rejected_and_zero_one_accepted() -> None:
    data = document()
    data["defaults"]["mean_weight"] = 0.5
    data["defaults"]["midpoint_weight"] = 0.4
    with pytest.raises(AnalystConsensusConfigurationError):
        parse_analyst_consensus_configuration(data)

    data["defaults"]["mean_weight"] = 0.0
    data["defaults"]["midpoint_weight"] = 1.0
    assert parse_analyst_consensus_configuration(data).default_rule.mean_weight == 0.0
