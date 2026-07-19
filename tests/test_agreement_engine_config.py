import pytest

from src.config.agreement_engine import (
    AgreementEngineConfiguration,
    AgreementEngineConfigurationError,
    load_agreement_engine_configuration,
    parse_agreement_engine_configuration,
)


def document(**overrides: object) -> dict[str, object]:
    defaults = {
        "enabled": True,
        "strong_threshold_pct": 10,
        "moderate_threshold_pct": 20,
        "weak_threshold_pct": 35,
        "outlier_threshold_pct": 50,
        "extreme_outlier_threshold_pct": 80,
        "minimum_primary_models": 2,
        "include_reference_in_intrinsic_cluster": True,
        "market_expectation_affects_overall_agreement": False,
    }
    defaults.update(overrides)
    return {"defaults": defaults}


def test_parse_default_configuration() -> None:
    result = parse_agreement_engine_configuration(document())

    assert result == AgreementEngineConfiguration(
        enabled=True,
        strong_threshold_pct=10.0,
        moderate_threshold_pct=20.0,
        weak_threshold_pct=35.0,
        outlier_threshold_pct=50.0,
        extreme_outlier_threshold_pct=80.0,
        minimum_primary_models=2,
        include_reference_in_intrinsic_cluster=True,
        market_expectation_affects_overall_agreement=False,
    )


def test_load_configuration_from_yaml(tmp_path) -> None:
    path = tmp_path / "agreement.yaml"
    path.write_text(
        """
defaults:
  enabled: true
  strong_threshold_pct: 10
  moderate_threshold_pct: 20
  weak_threshold_pct: 35
  outlier_threshold_pct: 50
  extreme_outlier_threshold_pct: 80
  minimum_primary_models: 2
  include_reference_in_intrinsic_cluster: true
  market_expectation_affects_overall_agreement: false
""",
        encoding="utf-8",
    )

    assert load_agreement_engine_configuration(path).enabled is True


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"enabled": "yes"}, "enabled"),
        ({"strong_threshold_pct": 20}, "strictly increasing"),
        ({"outlier_threshold_pct": 80}, "outlier thresholds"),
        ({"minimum_primary_models": 0}, "at least 1"),
        ({"include_reference_in_intrinsic_cluster": "true"}, "boolean"),
    ],
)
def test_validation_errors(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(AgreementEngineConfigurationError, match=match):
        parse_agreement_engine_configuration(document(**overrides))


def test_rejects_unknown_keys() -> None:
    with pytest.raises(AgreementEngineConfigurationError, match="not supported"):
        parse_agreement_engine_configuration(document(extra=True))
