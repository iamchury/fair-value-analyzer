from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isclose, isfinite
from pathlib import Path
from types import MappingProxyType

import yaml


class AnalystConsensusConfigurationError(ValueError):
    pass


class AnalystFairValueMethod(str, Enum):
    MEAN = "MEAN"
    MIDPOINT = "MIDPOINT"
    WEIGHTED_MEAN_MIDPOINT = "WEIGHTED_MEAN_MIDPOINT"


@dataclass(frozen=True)
class AnalystConsensusRule:
    enabled: bool
    fair_value_method: AnalystFairValueMethod
    mean_weight: float
    midpoint_weight: float
    apply_treasury_multiplier: bool
    low_dispersion_threshold_percent: float
    medium_dispersion_threshold_percent: float
    extreme_dispersion_threshold_percent: float
    stale_after_days: int
    rationale: str | None


@dataclass(frozen=True)
class AnalystConsensusConfiguration:
    default_rule: AnalystConsensusRule
    symbol_rules: Mapping[str, AnalystConsensusRule]


def load_analyst_consensus_configuration(
    path: str | Path = "config/analyst_consensus.yaml",
) -> AnalystConsensusConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise AnalystConsensusConfigurationError(
            f"{config_path}: failed to read analyst consensus configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise AnalystConsensusConfigurationError(
            f"{config_path}: invalid YAML in analyst consensus configuration."
        ) from exc
    if document is None:
        raise AnalystConsensusConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_analyst_consensus_configuration(document)
    except AnalystConsensusConfigurationError as exc:
        raise AnalystConsensusConfigurationError(f"{config_path}: {exc}") from exc


def parse_analyst_consensus_configuration(
    document: Mapping[str, object],
) -> AnalystConsensusConfiguration:
    if not isinstance(document, Mapping):
        raise AnalystConsensusConfigurationError("document must be a mapping.")
    _validate_allowed_keys(document, {"defaults"}, {"symbols"}, "document")
    default_rule = _parse_rule(_require_mapping(document["defaults"], "defaults"), "defaults")
    raw_symbols = document.get("symbols", {})
    if raw_symbols is None:
        raw_symbols = {}
    symbols = _require_mapping(raw_symbols, "symbols")
    symbol_rules: dict[str, AnalystConsensusRule] = {}
    for raw_symbol, raw_rule in symbols.items():
        symbol = _normalize_symbol(raw_symbol, "symbols key")
        if symbol in symbol_rules:
            raise AnalystConsensusConfigurationError(f"{symbol} is duplicated.")
        symbol_rules[symbol] = _parse_rule(
            _require_mapping(raw_rule, f"symbols.{symbol}"),
            f"symbols.{symbol}",
            default_rule,
        )
    return AnalystConsensusConfiguration(
        default_rule=default_rule,
        symbol_rules=MappingProxyType(symbol_rules),
    )


def get_analyst_consensus_rule(
    configuration: AnalystConsensusConfiguration,
    symbol: str,
) -> AnalystConsensusRule:
    return configuration.symbol_rules.get(
        _normalize_symbol(symbol, "symbol"),
        configuration.default_rule,
    )


def _parse_rule(
    rule: Mapping[str, object],
    path: str,
    fallback: AnalystConsensusRule | None = None,
) -> AnalystConsensusRule:
    required = set() if fallback is not None else {
        "enabled",
        "fair_value_method",
        "mean_weight",
        "midpoint_weight",
        "apply_treasury_multiplier",
        "low_dispersion_threshold_percent",
        "medium_dispersion_threshold_percent",
        "extreme_dispersion_threshold_percent",
        "stale_after_days",
    }
    optional = {
        "enabled",
        "fair_value_method",
        "mean_weight",
        "midpoint_weight",
        "apply_treasury_multiplier",
        "low_dispersion_threshold_percent",
        "medium_dispersion_threshold_percent",
        "extreme_dispersion_threshold_percent",
        "stale_after_days",
        "rationale",
    } - required
    _validate_allowed_keys(rule, required, optional, path)
    base = fallback
    enabled = _optional_bool(rule, "enabled", path, base.enabled if base else None)
    method = _optional_method(rule, "fair_value_method", path, base.fair_value_method if base else None)
    mean_weight = _optional_weight(rule, "mean_weight", path, base.mean_weight if base else None)
    midpoint_weight = _optional_weight(rule, "midpoint_weight", path, base.midpoint_weight if base else None)
    apply_treasury = _optional_bool(
        rule,
        "apply_treasury_multiplier",
        path,
        base.apply_treasury_multiplier if base else None,
    )
    low = _optional_positive_number(
        rule,
        "low_dispersion_threshold_percent",
        path,
        base.low_dispersion_threshold_percent if base else None,
    )
    medium = _optional_positive_number(
        rule,
        "medium_dispersion_threshold_percent",
        path,
        base.medium_dispersion_threshold_percent if base else None,
    )
    extreme = _optional_positive_number(
        rule,
        "extreme_dispersion_threshold_percent",
        path,
        base.extreme_dispersion_threshold_percent if base else None,
    )
    stale = _optional_int(
        rule,
        "stale_after_days",
        path,
        base.stale_after_days if base else None,
    )
    rationale = _optional_string(
        rule.get("rationale", base.rationale if base else None),
        f"{path}.rationale",
    )
    if not isclose(mean_weight + midpoint_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise AnalystConsensusConfigurationError(
            f"{path}: mean_weight and midpoint_weight must sum to 1.0."
        )
    if not (low < medium < extreme):
        raise AnalystConsensusConfigurationError(
            f"{path}: dispersion thresholds must be strictly increasing."
        )
    if extreme > 1000:
        raise AnalystConsensusConfigurationError(
            f"{path}.extreme_dispersion_threshold_percent must be no more than 1000."
        )
    if not 1 <= stale <= 3650:
        raise AnalystConsensusConfigurationError(
            f"{path}.stale_after_days must be between 1 and 3650."
        )
    return AnalystConsensusRule(
        enabled=enabled,
        fair_value_method=method,
        mean_weight=mean_weight,
        midpoint_weight=midpoint_weight,
        apply_treasury_multiplier=apply_treasury,
        low_dispersion_threshold_percent=low,
        medium_dispersion_threshold_percent=medium,
        extreme_dispersion_threshold_percent=extreme,
        stale_after_days=stale,
        rationale=rationale,
    )


def _validate_allowed_keys(mapping, required, optional, path) -> None:
    actual = set(mapping)
    missing = required - actual
    unexpected = actual - required - optional
    if missing:
        raise AnalystConsensusConfigurationError(f"{path}.{sorted(missing)[0]} is required.")
    if unexpected:
        raise AnalystConsensusConfigurationError(f"{path}.{sorted(unexpected)[0]} is not supported.")


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AnalystConsensusConfigurationError(f"{path} must be a mapping.")
    return value


def _normalize_symbol(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise AnalystConsensusConfigurationError(f"{path} must be a string.")
    symbol = value.strip().upper()
    if not symbol:
        raise AnalystConsensusConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in symbol):
        raise AnalystConsensusConfigurationError(f"{path} must not contain whitespace.")
    return symbol


def _optional_method(mapping, key, path, fallback):
    if key not in mapping:
        if fallback is None:
            raise AnalystConsensusConfigurationError(f"{path}.{key} is required.")
        return fallback
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, str):
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be a string.")
    try:
        return AnalystFairValueMethod(value.strip().upper())
    except ValueError as exc:
        raise AnalystConsensusConfigurationError(f"{path}.{key} is not supported.") from exc


def _optional_bool(mapping, key, path, fallback):
    if key not in mapping:
        if fallback is None:
            raise AnalystConsensusConfigurationError(f"{path}.{key} is required.")
        return fallback
    if not isinstance(mapping[key], bool):
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be a boolean.")
    return mapping[key]


def _optional_weight(mapping, key, path, fallback):
    value = _optional_number(mapping, key, path, fallback)
    if not 0 <= value <= 1:
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be between 0 and 1.")
    return value


def _optional_positive_number(mapping, key, path, fallback):
    value = _optional_number(mapping, key, path, fallback)
    if value <= 0:
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be greater than 0.")
    return value


def _optional_number(mapping, key, path, fallback):
    if key not in mapping:
        if fallback is None:
            raise AnalystConsensusConfigurationError(f"{path}.{key} is required.")
        return fallback
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be a finite number.")
    if not isfinite(value):
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be finite.")
    return float(value)


def _optional_int(mapping, key, path, fallback):
    if key not in mapping:
        if fallback is None:
            raise AnalystConsensusConfigurationError(f"{path}.{key} is required.")
        return fallback
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalystConsensusConfigurationError(f"{path}.{key} must be an integer.")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise AnalystConsensusConfigurationError(f"{path} must be a string.")
    text = value.strip()
    return text or None
