from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import yaml


class MomentumReferenceConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MomentumReferenceConfiguration:
    enabled: bool
    rsi_period: int
    neutral_level: float
    history_period: str
    history_interval: str
    minimum_observations: int
    fallback_to_nearest: bool
    prefer_adjusted_close: bool


def load_momentum_reference_configuration(
    path: str | Path = "config/momentum_reference.yaml",
) -> MomentumReferenceConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise MomentumReferenceConfigurationError(
            f"{config_path}: failed to read momentum reference configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise MomentumReferenceConfigurationError(
            f"{config_path}: invalid YAML in momentum reference configuration."
        ) from exc
    if document is None:
        raise MomentumReferenceConfigurationError(f"{config_path}: YAML document must not be empty.")
    try:
        return parse_momentum_reference_configuration(document)
    except MomentumReferenceConfigurationError as exc:
        raise MomentumReferenceConfigurationError(f"{config_path}: {exc}") from exc


def parse_momentum_reference_configuration(document: Mapping[str, object]) -> MomentumReferenceConfiguration:
    if not isinstance(document, Mapping):
        raise MomentumReferenceConfigurationError("document must be a mapping.")
    _validate_keys(document, {"defaults"}, "document")
    defaults = _mapping(document["defaults"], "defaults")
    _validate_keys(defaults, _KEYS, "defaults")
    config = MomentumReferenceConfiguration(
        enabled=_bool(defaults, "enabled", "defaults"),
        rsi_period=_int(defaults, "rsi_period", "defaults"),
        neutral_level=_number(defaults, "neutral_level", "defaults"),
        history_period=_string(defaults, "history_period", "defaults"),
        history_interval=_string(defaults, "history_interval", "defaults"),
        minimum_observations=_int(defaults, "minimum_observations", "defaults"),
        fallback_to_nearest=_bool(defaults, "fallback_to_nearest", "defaults"),
        prefer_adjusted_close=_bool(defaults, "prefer_adjusted_close", "defaults"),
    )
    if config.rsi_period < 2:
        raise MomentumReferenceConfigurationError("defaults.rsi_period must be at least 2.")
    if config.neutral_level <= 0 or config.neutral_level >= 100:
        raise MomentumReferenceConfigurationError("defaults.neutral_level must be between 0 and 100.")
    if config.minimum_observations < config.rsi_period + 1:
        raise MomentumReferenceConfigurationError("defaults.minimum_observations is below the RSI requirement.")
    if config.history_period not in {"1mo", "3mo", "6mo", "1y", "2y", "5y"}:
        raise MomentumReferenceConfigurationError("defaults.history_period is not supported.")
    if config.history_interval not in {"1d"}:
        raise MomentumReferenceConfigurationError("defaults.history_interval is not supported.")
    return config


_KEYS = {
    "enabled",
    "rsi_period",
    "neutral_level",
    "history_period",
    "history_interval",
    "minimum_observations",
    "fallback_to_nearest",
    "prefer_adjusted_close",
}


def _validate_keys(mapping: Mapping[str, object], required: set[str], path: str) -> None:
    missing = required - set(mapping)
    unexpected = set(mapping) - required
    if missing:
        raise MomentumReferenceConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise MomentumReferenceConfigurationError(f"{path}.{sorted(unexpected)[0]} is not supported.")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MomentumReferenceConfigurationError(f"{path} must be a mapping.")
    return value


def _bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise MomentumReferenceConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _int(mapping: Mapping[str, object], key: str, path: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise MomentumReferenceConfigurationError(f"{path}.{key} must be an integer.")
    return value


def _number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise MomentumReferenceConfigurationError(f"{path}.{key} must be a finite number.")
    return float(value)


def _string(mapping: Mapping[str, object], key: str, path: str) -> str:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise MomentumReferenceConfigurationError(f"{path}.{key} must be a non-empty string.")
    return value.strip()
