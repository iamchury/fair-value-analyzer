from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path

import yaml


class FairValueRangeConfigurationError(ValueError):
    pass


class RangeBaseMethod(str, Enum):
    CONFIDENCE_WEIGHTED_MEDIAN = "CONFIDENCE_WEIGHTED_MEDIAN"


class ConservativeRangeMethod(str, Enum):
    LOWER_SUPPORT = "LOWER_SUPPORT"


class OptimisticRangeMethod(str, Enum):
    UPPER_INTRINSIC_SUPPORT = "UPPER_INTRINSIC_SUPPORT"


@dataclass(frozen=True)
class FairValueRangeConfiguration:
    enabled: bool
    include_reference_values: bool
    include_low_confidence_intrinsic: bool
    exclude_outliers: bool
    base_method: RangeBaseMethod
    conservative_method: ConservativeRangeMethod
    optimistic_method: OptimisticRangeMethod
    high_confidence_weight: float
    medium_confidence_weight: float
    low_confidence_weight: float
    unknown_confidence_weight: float
    minimum_intrinsic_models: int
    reference_value_weight: float
    market_expectation_in_intrinsic_range: bool
    show_market_expectation_separately: bool
    show_momentum_reference_separately: bool
    deep_undervalued_pct: float
    undervalued_pct: float
    near_fair_upper_pct: float
    above_fair_pct: float


def load_fair_value_range_configuration(
    path: str | Path = "config/fair_value_range.yaml",
) -> FairValueRangeConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise FairValueRangeConfigurationError(
            f"{config_path}: failed to read fair value range configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise FairValueRangeConfigurationError(
            f"{config_path}: invalid YAML in fair value range configuration."
        ) from exc
    if document is None:
        raise FairValueRangeConfigurationError(f"{config_path}: YAML document must not be empty.")
    try:
        return parse_fair_value_range_configuration(document)
    except FairValueRangeConfigurationError as exc:
        raise FairValueRangeConfigurationError(f"{config_path}: {exc}") from exc


def parse_fair_value_range_configuration(document: Mapping[str, object]) -> FairValueRangeConfiguration:
    if not isinstance(document, Mapping):
        raise FairValueRangeConfigurationError("document must be a mapping.")
    _keys(document, {"defaults"}, "document")
    defaults = _mapping(document["defaults"], "defaults")
    _keys(defaults, _KEYS, "defaults")
    config = FairValueRangeConfiguration(
        enabled=_bool(defaults, "enabled", "defaults"),
        include_reference_values=_bool(defaults, "include_reference_values", "defaults"),
        include_low_confidence_intrinsic=_bool(defaults, "include_low_confidence_intrinsic", "defaults"),
        exclude_outliers=_bool(defaults, "exclude_outliers", "defaults"),
        base_method=_enum(defaults, "base_method", "defaults", RangeBaseMethod),
        conservative_method=_enum(defaults, "conservative_method", "defaults", ConservativeRangeMethod),
        optimistic_method=_enum(defaults, "optimistic_method", "defaults", OptimisticRangeMethod),
        high_confidence_weight=_positive(defaults, "high_confidence_weight", "defaults"),
        medium_confidence_weight=_positive(defaults, "medium_confidence_weight", "defaults"),
        low_confidence_weight=_positive(defaults, "low_confidence_weight", "defaults"),
        unknown_confidence_weight=_positive(defaults, "unknown_confidence_weight", "defaults"),
        minimum_intrinsic_models=_positive_int(defaults, "minimum_intrinsic_models", "defaults"),
        reference_value_weight=_positive(defaults, "reference_value_weight", "defaults"),
        market_expectation_in_intrinsic_range=_bool(defaults, "market_expectation_in_intrinsic_range", "defaults"),
        show_market_expectation_separately=_bool(defaults, "show_market_expectation_separately", "defaults"),
        show_momentum_reference_separately=_bool(defaults, "show_momentum_reference_separately", "defaults"),
        deep_undervalued_pct=_number(defaults, "deep_undervalued_pct", "defaults"),
        undervalued_pct=_number(defaults, "undervalued_pct", "defaults"),
        near_fair_upper_pct=_number(defaults, "near_fair_upper_pct", "defaults"),
        above_fair_pct=_number(defaults, "above_fair_pct", "defaults"),
    )
    if not (
        config.deep_undervalued_pct
        < config.undervalued_pct
        < config.near_fair_upper_pct
        < config.above_fair_pct
    ):
        raise FairValueRangeConfigurationError("defaults market-position thresholds must be increasing.")
    return config


_KEYS = {
    "enabled",
    "include_reference_values",
    "include_low_confidence_intrinsic",
    "exclude_outliers",
    "base_method",
    "conservative_method",
    "optimistic_method",
    "high_confidence_weight",
    "medium_confidence_weight",
    "low_confidence_weight",
    "unknown_confidence_weight",
    "minimum_intrinsic_models",
    "reference_value_weight",
    "market_expectation_in_intrinsic_range",
    "show_market_expectation_separately",
    "show_momentum_reference_separately",
    "deep_undervalued_pct",
    "undervalued_pct",
    "near_fair_upper_pct",
    "above_fair_pct",
}


def _keys(mapping: Mapping[str, object], required: set[str], path: str) -> None:
    missing = required - set(mapping)
    unexpected = set(mapping) - required
    if missing:
        raise FairValueRangeConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise FairValueRangeConfigurationError(f"{path}.{sorted(unexpected)[0]} is not supported.")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FairValueRangeConfigurationError(f"{path} must be a mapping.")
    return value


def _bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise FairValueRangeConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise FairValueRangeConfigurationError(f"{path}.{key} must be a finite number.")
    return float(value)


def _positive(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = _number(mapping, key, path)
    if value <= 0:
        raise FairValueRangeConfigurationError(f"{path}.{key} must be greater than 0.")
    return value


def _positive_int(mapping: Mapping[str, object], key: str, path: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FairValueRangeConfigurationError(f"{path}.{key} must be a positive integer.")
    return value


def _enum(mapping: Mapping[str, object], key: str, path: str, enum_type):
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, str):
        raise FairValueRangeConfigurationError(f"{path}.{key} must be a string.")
    try:
        return enum_type(value.strip().upper())
    except ValueError as exc:
        raise FairValueRangeConfigurationError(f"{path}.{key} is not supported.") from exc
