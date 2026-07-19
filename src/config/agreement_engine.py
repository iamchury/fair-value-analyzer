from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import yaml


class AgreementEngineConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class AgreementEngineConfiguration:
    enabled: bool
    strong_threshold_pct: float
    moderate_threshold_pct: float
    weak_threshold_pct: float
    outlier_threshold_pct: float
    extreme_outlier_threshold_pct: float
    minimum_primary_models: int
    include_reference_in_intrinsic_cluster: bool
    market_expectation_affects_overall_agreement: bool


def load_agreement_engine_configuration(
    path: str | Path = "config/agreement_engine.yaml",
) -> AgreementEngineConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise AgreementEngineConfigurationError(
            f"{config_path}: failed to read agreement engine configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise AgreementEngineConfigurationError(
            f"{config_path}: invalid YAML in agreement engine configuration."
        ) from exc
    if document is None:
        raise AgreementEngineConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_agreement_engine_configuration(document)
    except AgreementEngineConfigurationError as exc:
        raise AgreementEngineConfigurationError(f"{config_path}: {exc}") from exc


def parse_agreement_engine_configuration(
    document: Mapping[str, object],
) -> AgreementEngineConfiguration:
    if not isinstance(document, Mapping):
        raise AgreementEngineConfigurationError("document must be a mapping.")
    _validate_allowed_keys(document, {"defaults"}, set(), "document")
    defaults = _require_mapping(document["defaults"], "defaults")
    _validate_allowed_keys(defaults, _REQUIRED_KEYS, set(), "defaults")

    config = AgreementEngineConfiguration(
        enabled=_require_bool(defaults, "enabled", "defaults"),
        strong_threshold_pct=_require_non_negative_number(
            defaults, "strong_threshold_pct", "defaults"
        ),
        moderate_threshold_pct=_require_non_negative_number(
            defaults, "moderate_threshold_pct", "defaults"
        ),
        weak_threshold_pct=_require_non_negative_number(
            defaults, "weak_threshold_pct", "defaults"
        ),
        outlier_threshold_pct=_require_non_negative_number(
            defaults, "outlier_threshold_pct", "defaults"
        ),
        extreme_outlier_threshold_pct=_require_non_negative_number(
            defaults, "extreme_outlier_threshold_pct", "defaults"
        ),
        minimum_primary_models=_require_positive_integer(
            defaults, "minimum_primary_models", "defaults"
        ),
        include_reference_in_intrinsic_cluster=_require_bool(
            defaults, "include_reference_in_intrinsic_cluster", "defaults"
        ),
        market_expectation_affects_overall_agreement=_require_bool(
            defaults, "market_expectation_affects_overall_agreement", "defaults"
        ),
    )
    _validate_threshold_order(config)
    return config


_REQUIRED_KEYS = {
    "enabled",
    "strong_threshold_pct",
    "moderate_threshold_pct",
    "weak_threshold_pct",
    "outlier_threshold_pct",
    "extreme_outlier_threshold_pct",
    "minimum_primary_models",
    "include_reference_in_intrinsic_cluster",
    "market_expectation_affects_overall_agreement",
}


def _validate_allowed_keys(mapping, required, optional, path) -> None:
    actual = set(mapping)
    missing = required - actual
    unexpected = actual - required - optional
    if missing:
        raise AgreementEngineConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise AgreementEngineConfigurationError(
            f"{path}.{sorted(unexpected)[0]} is not supported."
        )


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AgreementEngineConfigurationError(f"{path} must be a mapping.")
    return value


def _require_bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise AgreementEngineConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _require_non_negative_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgreementEngineConfigurationError(f"{path}.{key} must be a finite number.")
    if not isfinite(value) or value < 0:
        raise AgreementEngineConfigurationError(
            f"{path}.{key} must be a finite non-negative number."
        )
    return float(value)


def _require_positive_integer(mapping: Mapping[str, object], key: str, path: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgreementEngineConfigurationError(f"{path}.{key} must be an integer.")
    if value < 1:
        raise AgreementEngineConfigurationError(f"{path}.{key} must be at least 1.")
    return value


def _validate_threshold_order(config: AgreementEngineConfiguration) -> None:
    if not (
        config.strong_threshold_pct
        < config.moderate_threshold_pct
        < config.weak_threshold_pct
    ):
        raise AgreementEngineConfigurationError(
            "defaults agreement thresholds must be strictly increasing."
        )
    if not config.outlier_threshold_pct < config.extreme_outlier_threshold_pct:
        raise AgreementEngineConfigurationError(
            "defaults outlier thresholds must be strictly increasing."
        )
