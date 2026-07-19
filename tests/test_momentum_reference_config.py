import pytest

from src.config.momentum_reference import (
    MomentumReferenceConfigurationError,
    load_momentum_reference_configuration,
    parse_momentum_reference_configuration,
)


def document(**overrides):
    defaults = {
        "enabled": True,
        "rsi_period": 14,
        "neutral_level": 50,
        "history_period": "1y",
        "history_interval": "1d",
        "minimum_observations": 30,
        "fallback_to_nearest": True,
        "prefer_adjusted_close": True,
    }
    defaults.update(overrides)
    return {"defaults": defaults}


def test_parse_defaults() -> None:
    result = parse_momentum_reference_configuration(document())

    assert result.rsi_period == 14
    assert result.neutral_level == 50.0
    assert result.minimum_observations == 30


def test_load_yaml(tmp_path) -> None:
    path = tmp_path / "momentum.yaml"
    path.write_text(
        """
defaults:
  enabled: true
  rsi_period: 14
  neutral_level: 50
  history_period: 1y
  history_interval: 1d
  minimum_observations: 30
  fallback_to_nearest: true
  prefer_adjusted_close: true
""",
        encoding="utf-8",
    )

    assert load_momentum_reference_configuration(path).enabled is True


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"rsi_period": 1}, "rsi_period"),
        ({"neutral_level": 100}, "neutral_level"),
        ({"minimum_observations": 10}, "minimum_observations"),
        ({"history_period": "10y"}, "history_period"),
        ({"history_interval": "1h"}, "history_interval"),
        ({"enabled": "yes"}, "enabled"),
    ],
)
def test_validation_errors(overrides, match) -> None:
    with pytest.raises(MomentumReferenceConfigurationError, match=match):
        parse_momentum_reference_configuration(document(**overrides))
