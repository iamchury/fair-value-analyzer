from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path

import yaml


class RankingEngineConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RankingWeights:
    valuation: float
    recommendation: float
    evidence: float
    agreement: float
    momentum: float

    @property
    def total(self) -> float:
        return (
            self.valuation
            + self.recommendation
            + self.evidence
            + self.agreement
            + self.momentum
        )


@dataclass(frozen=True)
class MomentumReferenceDisplayConfiguration:
    enabled: bool
    near_reference_pct: float
    well_above_reference_pct: float
    well_below_reference_pct: float
    show_reference_date: bool
    show_cross_direction: bool
    show_current_rsi: bool
    show_price_difference: bool
    affect_ranking_score: bool


@dataclass(frozen=True)
class RankingEngineConfiguration:
    enabled: bool
    weights: RankingWeights
    momentum_reference_display: MomentumReferenceDisplayConfiguration = field(
        default_factory=lambda: MomentumReferenceDisplayConfiguration(
            enabled=True,
            near_reference_pct=3.0,
            well_above_reference_pct=10.0,
            well_below_reference_pct=-10.0,
            show_reference_date=True,
            show_cross_direction=True,
            show_current_rsi=True,
            show_price_difference=True,
            affect_ranking_score=False,
        )
    )


def load_ranking_engine_configuration(
    path: str | Path = "config/ranking_engine.yaml",
) -> RankingEngineConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise RankingEngineConfigurationError(
            f"{config_path}: failed to read ranking engine configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise RankingEngineConfigurationError(
            f"{config_path}: invalid YAML in ranking engine configuration."
        ) from exc
    if document is None:
        raise RankingEngineConfigurationError(f"{config_path}: YAML document must not be empty.")
    try:
        return parse_ranking_engine_configuration(document)
    except RankingEngineConfigurationError as exc:
        raise RankingEngineConfigurationError(f"{config_path}: {exc}") from exc


def parse_ranking_engine_configuration(document: Mapping[str, object]) -> RankingEngineConfiguration:
    if not isinstance(document, Mapping):
        raise RankingEngineConfigurationError("document must be a mapping.")
    _keys(document, {"enabled", "weights", "momentum_reference_display"}, "document")
    weights = _weights(_mapping(document["weights"], "weights"))
    return RankingEngineConfiguration(
        enabled=_bool(document, "enabled", "document"),
        weights=weights,
        momentum_reference_display=_momentum_reference_display(
            _mapping(document["momentum_reference_display"], "momentum_reference_display")
        ),
    )


def _weights(mapping: Mapping[str, object]) -> RankingWeights:
    _keys(mapping, {"valuation", "recommendation", "evidence", "agreement", "momentum"}, "weights")
    weights = RankingWeights(
        valuation=_positive_number(mapping, "valuation", "weights"),
        recommendation=_positive_number(mapping, "recommendation", "weights"),
        evidence=_positive_number(mapping, "evidence", "weights"),
        agreement=_positive_number(mapping, "agreement", "weights"),
        momentum=_positive_number(mapping, "momentum", "weights"),
    )
    if weights.total <= 0:
        raise RankingEngineConfigurationError("weights total must be positive.")
    return weights


def _momentum_reference_display(mapping: Mapping[str, object]) -> MomentumReferenceDisplayConfiguration:
    _keys(
        mapping,
        {
            "enabled",
            "near_reference_pct",
            "well_above_reference_pct",
            "well_below_reference_pct",
            "show_reference_date",
            "show_cross_direction",
            "show_current_rsi",
            "show_price_difference",
            "affect_ranking_score",
        },
        "momentum_reference_display",
    )
    display = MomentumReferenceDisplayConfiguration(
        enabled=_bool(mapping, "enabled", "momentum_reference_display"),
        near_reference_pct=_number(mapping, "near_reference_pct", "momentum_reference_display"),
        well_above_reference_pct=_number(mapping, "well_above_reference_pct", "momentum_reference_display"),
        well_below_reference_pct=_number(mapping, "well_below_reference_pct", "momentum_reference_display"),
        show_reference_date=_bool(mapping, "show_reference_date", "momentum_reference_display"),
        show_cross_direction=_bool(mapping, "show_cross_direction", "momentum_reference_display"),
        show_current_rsi=_bool(mapping, "show_current_rsi", "momentum_reference_display"),
        show_price_difference=_bool(mapping, "show_price_difference", "momentum_reference_display"),
        affect_ranking_score=_bool(mapping, "affect_ranking_score", "momentum_reference_display"),
    )
    if display.near_reference_pct < 0:
        raise RankingEngineConfigurationError("momentum_reference_display.near_reference_pct must be non-negative.")
    if display.well_below_reference_pct >= -display.near_reference_pct:
        raise RankingEngineConfigurationError("momentum_reference_display.well_below_reference_pct must be below -near_reference_pct.")
    if display.well_above_reference_pct <= display.near_reference_pct:
        raise RankingEngineConfigurationError("momentum_reference_display.well_above_reference_pct must be above near_reference_pct.")
    if display.affect_ranking_score:
        raise RankingEngineConfigurationError("momentum_reference_display.affect_ranking_score must remain false in V1.")
    return display


def _keys(mapping: Mapping[str, object], required: set[str], path: str) -> None:
    missing = required - set(mapping)
    unexpected = set(mapping) - required
    if missing:
        raise RankingEngineConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise RankingEngineConfigurationError(f"{path}.{sorted(unexpected)[0]} is not supported.")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RankingEngineConfigurationError(f"{path} must be a mapping.")
    return value


def _bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise RankingEngineConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _positive_number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RankingEngineConfigurationError(f"{path}.{key} must be a positive number.")
    number = float(value)
    if number <= 0 or not isfinite(number):
        raise RankingEngineConfigurationError(f"{path}.{key} must be a positive number.")
    return number


def _number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise RankingEngineConfigurationError(f"{path}.{key} must be a finite number.")
    return float(value)
