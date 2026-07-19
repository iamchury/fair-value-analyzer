from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import yaml


class RecommendationV2ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ValuationConditionThresholds:
    deeply_undervalued_pct: float
    undervalued_pct: float
    slightly_undervalued_pct: float
    near_fair_upper_pct: float
    moderately_overvalued_pct: float
    significantly_overvalued_pct: float


@dataclass(frozen=True)
class MomentumConditionThresholds:
    strong_positive_rsi: float
    positive_rsi: float
    weak_rsi: float
    strong_negative_rsi: float
    positive_reference_pct: float
    negative_reference_pct: float
    severe_negative_reference_pct: float


@dataclass(frozen=True)
class RecommendationV2Configuration:
    enabled: bool
    minimum_intrinsic_models: int
    valuation_thresholds: ValuationConditionThresholds
    momentum_thresholds: MomentumConditionThresholds
    require_agreement_for_strong_buy: bool
    require_agreement_for_sell: bool


def load_recommendation_v2_configuration(
    path: str | Path = "config/recommendation_v2.yaml",
) -> RecommendationV2Configuration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise RecommendationV2ConfigurationError(
            f"{config_path}: failed to read Recommendation V2 configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise RecommendationV2ConfigurationError(
            f"{config_path}: invalid YAML in Recommendation V2 configuration."
        ) from exc
    if document is None:
        raise RecommendationV2ConfigurationError(f"{config_path}: YAML document must not be empty.")
    try:
        return parse_recommendation_v2_configuration(document)
    except RecommendationV2ConfigurationError as exc:
        raise RecommendationV2ConfigurationError(f"{config_path}: {exc}") from exc


def parse_recommendation_v2_configuration(document: Mapping[str, object]) -> RecommendationV2Configuration:
    if not isinstance(document, Mapping):
        raise RecommendationV2ConfigurationError("document must be a mapping.")
    _keys(document, {"defaults"}, "document")
    defaults = _mapping(document["defaults"], "defaults")
    _keys(defaults, _DEFAULT_KEYS, "defaults")
    valuation = _valuation_thresholds(_mapping(defaults["valuation_thresholds"], "defaults.valuation_thresholds"))
    momentum = _momentum_thresholds(_mapping(defaults["momentum_thresholds"], "defaults.momentum_thresholds"))
    return RecommendationV2Configuration(
        enabled=_bool(defaults, "enabled", "defaults"),
        minimum_intrinsic_models=_positive_int(defaults, "minimum_intrinsic_models", "defaults"),
        valuation_thresholds=valuation,
        momentum_thresholds=momentum,
        require_agreement_for_strong_buy=_bool(defaults, "require_agreement_for_strong_buy", "defaults"),
        require_agreement_for_sell=_bool(defaults, "require_agreement_for_sell", "defaults"),
    )


_DEFAULT_KEYS = {
    "enabled",
    "minimum_intrinsic_models",
    "valuation_thresholds",
    "momentum_thresholds",
    "require_agreement_for_strong_buy",
    "require_agreement_for_sell",
}

_VALUATION_KEYS = {
    "deeply_undervalued_pct",
    "undervalued_pct",
    "slightly_undervalued_pct",
    "near_fair_upper_pct",
    "moderately_overvalued_pct",
    "significantly_overvalued_pct",
}

_MOMENTUM_KEYS = {
    "strong_positive_rsi",
    "positive_rsi",
    "weak_rsi",
    "strong_negative_rsi",
    "positive_reference_pct",
    "negative_reference_pct",
    "severe_negative_reference_pct",
}


def _valuation_thresholds(mapping: Mapping[str, object]) -> ValuationConditionThresholds:
    _keys(mapping, _VALUATION_KEYS, "defaults.valuation_thresholds")
    thresholds = ValuationConditionThresholds(
        deeply_undervalued_pct=_number(mapping, "deeply_undervalued_pct", "defaults.valuation_thresholds"),
        undervalued_pct=_number(mapping, "undervalued_pct", "defaults.valuation_thresholds"),
        slightly_undervalued_pct=_number(mapping, "slightly_undervalued_pct", "defaults.valuation_thresholds"),
        near_fair_upper_pct=_number(mapping, "near_fair_upper_pct", "defaults.valuation_thresholds"),
        moderately_overvalued_pct=_number(mapping, "moderately_overvalued_pct", "defaults.valuation_thresholds"),
        significantly_overvalued_pct=_number(mapping, "significantly_overvalued_pct", "defaults.valuation_thresholds"),
    )
    if not (
        thresholds.deeply_undervalued_pct
        < thresholds.undervalued_pct
        < thresholds.slightly_undervalued_pct
        < thresholds.near_fair_upper_pct
        < thresholds.moderately_overvalued_pct
        < thresholds.significantly_overvalued_pct
    ):
        raise RecommendationV2ConfigurationError("defaults.valuation_thresholds must be strictly ascending.")
    return thresholds


def _momentum_thresholds(mapping: Mapping[str, object]) -> MomentumConditionThresholds:
    _keys(mapping, _MOMENTUM_KEYS, "defaults.momentum_thresholds")
    thresholds = MomentumConditionThresholds(
        strong_positive_rsi=_number(mapping, "strong_positive_rsi", "defaults.momentum_thresholds"),
        positive_rsi=_number(mapping, "positive_rsi", "defaults.momentum_thresholds"),
        weak_rsi=_number(mapping, "weak_rsi", "defaults.momentum_thresholds"),
        strong_negative_rsi=_number(mapping, "strong_negative_rsi", "defaults.momentum_thresholds"),
        positive_reference_pct=_number(mapping, "positive_reference_pct", "defaults.momentum_thresholds"),
        negative_reference_pct=_number(mapping, "negative_reference_pct", "defaults.momentum_thresholds"),
        severe_negative_reference_pct=_number(mapping, "severe_negative_reference_pct", "defaults.momentum_thresholds"),
    )
    rsi_values = (
        thresholds.strong_negative_rsi,
        thresholds.weak_rsi,
        thresholds.positive_rsi,
        thresholds.strong_positive_rsi,
    )
    if not all(0 <= value <= 100 for value in rsi_values) or not (
        thresholds.strong_negative_rsi
        < thresholds.weak_rsi
        < thresholds.positive_rsi
        < thresholds.strong_positive_rsi
    ):
        raise RecommendationV2ConfigurationError("defaults.momentum_thresholds RSI values must be strictly ascending within 0..100.")
    if not (
        thresholds.severe_negative_reference_pct
        < thresholds.negative_reference_pct
        < thresholds.positive_reference_pct
    ):
        raise RecommendationV2ConfigurationError("defaults.momentum_thresholds reference percentages must be strictly ascending.")
    return thresholds


def _keys(mapping: Mapping[str, object], required: set[str], path: str) -> None:
    missing = required - set(mapping)
    unexpected = set(mapping) - required
    if missing:
        raise RecommendationV2ConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise RecommendationV2ConfigurationError(f"{path}.{sorted(unexpected)[0]} is not supported.")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RecommendationV2ConfigurationError(f"{path} must be a mapping.")
    return value


def _bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise RecommendationV2ConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise RecommendationV2ConfigurationError(f"{path}.{key} must be a finite number.")
    return float(value)


def _positive_int(mapping: Mapping[str, object], key: str, path: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RecommendationV2ConfigurationError(f"{path}.{key} must be a positive integer.")
    return value
