from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isclose, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


class EPSSelectionConfigurationError(ValueError):
    pass


class EPSSelectionMethod(str, Enum):
    LEGACY_FORWARD = "LEGACY_FORWARD"
    CURRENT_YEAR = "CURRENT_YEAR"
    NEXT_YEAR = "NEXT_YEAR"
    WEIGHTED_CURRENT_NEXT = "WEIGHTED_CURRENT_NEXT"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class EPSSelectionRule:
    method: EPSSelectionMethod
    current_year_weight: float | None
    next_year_weight: float | None
    manual_eps: float | None
    manual_period_label: str | None
    rationale: str | None


@dataclass(frozen=True)
class EPSSelectionConfiguration:
    default_rule: EPSSelectionRule
    symbol_rules: Mapping[str, EPSSelectionRule]


def load_eps_selection_configuration(
    path: str | Path = "config/eps_selection.yaml",
) -> EPSSelectionConfiguration:
    """Load EPS selection rules from YAML."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise EPSSelectionConfigurationError(
            f"{config_path}: failed to read EPS selection configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise EPSSelectionConfigurationError(
            f"{config_path}: invalid YAML in EPS selection configuration."
        ) from exc
    if document is None:
        raise EPSSelectionConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_eps_selection_configuration(document)
    except EPSSelectionConfigurationError as exc:
        raise EPSSelectionConfigurationError(f"{config_path}: {exc}") from exc


def parse_eps_selection_configuration(
    document: Mapping[str, object],
) -> EPSSelectionConfiguration:
    """Parse EPS selection configuration into immutable rule objects."""
    if not isinstance(document, Mapping):
        raise EPSSelectionConfigurationError("document must be a mapping.")
    _validate_allowed_keys(document, {"defaults"}, {"symbols"}, "document")

    defaults = _require_mapping(document["defaults"], "defaults")
    default_rule = _parse_rule(defaults, "defaults")
    raw_symbols = document.get("symbols", {})
    if raw_symbols is None:
        raw_symbols = {}
    symbols_section = _require_mapping(raw_symbols, "symbols")

    symbol_rules: dict[str, EPSSelectionRule] = {}
    for raw_symbol, raw_rule in symbols_section.items():
        symbol = _normalize_symbol(raw_symbol, "symbols key")
        if symbol in symbol_rules:
            raise EPSSelectionConfigurationError(f"{symbol} is duplicated.")
        symbol_rules[symbol] = _parse_rule(
            _require_mapping(raw_rule, f"symbols.{symbol}"),
            f"symbols.{symbol}",
            fallback=default_rule,
        )

    return EPSSelectionConfiguration(
        default_rule=default_rule,
        symbol_rules=MappingProxyType(symbol_rules),
    )


def get_eps_selection_rule(
    configuration: EPSSelectionConfiguration | None,
    symbol: str,
) -> EPSSelectionRule:
    """Return the symbol-specific EPS selection rule or the default rule."""
    if configuration is None:
        return EPSSelectionRule(
            method=EPSSelectionMethod.LEGACY_FORWARD,
            current_year_weight=None,
            next_year_weight=None,
            manual_eps=None,
            manual_period_label=None,
            rationale=None,
        )
    return configuration.symbol_rules.get(
        _normalize_symbol(symbol, "symbol"),
        configuration.default_rule,
    )


def _parse_rule(
    rule: Mapping[str, object],
    path: str,
    fallback: EPSSelectionRule | None = None,
) -> EPSSelectionRule:
    _validate_allowed_keys(
        rule,
        {"method"},
        {
            "current_year_weight",
            "next_year_weight",
            "manual_eps",
            "manual_period_label",
            "rationale",
        },
        path,
    )
    method = _parse_method(_require_key(rule, "method", path), f"{path}.method")
    current_weight = _optional_number(rule, "current_year_weight", path)
    next_weight = _optional_number(rule, "next_year_weight", path)
    manual_eps = _optional_number(rule, "manual_eps", path)
    manual_label = _optional_string(rule.get("manual_period_label"), f"{path}.manual_period_label")
    rationale = _optional_string(rule.get("rationale"), f"{path}.rationale")

    if method == EPSSelectionMethod.WEIGHTED_CURRENT_NEXT:
        current_weight = _require_weight(rule, "current_year_weight", path)
        next_weight = _require_weight(rule, "next_year_weight", path)
        if not isclose(current_weight + next_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise EPSSelectionConfigurationError(
                f"{path}: current_year_weight and next_year_weight must sum to 1.0."
            )
        if manual_eps is not None or manual_label is not None:
            raise EPSSelectionConfigurationError(
                f"{path}: manual fields are not supported for weighted_current_next."
            )
    elif method == EPSSelectionMethod.MANUAL:
        manual_eps = _require_number(rule, "manual_eps", path)
        manual_label = _require_non_empty_string(rule, "manual_period_label", path)
        if current_weight is not None or next_weight is not None:
            raise EPSSelectionConfigurationError(
                f"{path}: weights are not supported for manual."
            )
    elif method == EPSSelectionMethod.LEGACY_FORWARD:
        if manual_eps is not None or manual_label is not None:
            raise EPSSelectionConfigurationError(
                f"{path}: manual fields are not supported for legacy_forward."
            )
    else:
        if (
            current_weight is not None
            or next_weight is not None
            or manual_eps is not None
            or manual_label is not None
        ):
            raise EPSSelectionConfigurationError(
                f"{path}: method-specific fields are not supported for {method.value.lower()}."
            )

    return EPSSelectionRule(
        method=method,
        current_year_weight=current_weight,
        next_year_weight=next_weight,
        manual_eps=manual_eps,
        manual_period_label=manual_label,
        rationale=rationale,
    )


def _validate_allowed_keys(
    mapping: Mapping[str, object],
    required_keys: set[str],
    optional_keys: set[str],
    path: str,
) -> None:
    actual_keys = set(mapping)
    missing_keys = required_keys - actual_keys
    unexpected_keys = actual_keys - required_keys - optional_keys
    if missing_keys:
        raise EPSSelectionConfigurationError(
            f"{path}.{sorted(missing_keys)[0]} is required."
        )
    if unexpected_keys:
        raise EPSSelectionConfigurationError(
            f"{path}.{sorted(unexpected_keys)[0]} is not supported."
        )


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EPSSelectionConfigurationError(f"{path} must be a mapping.")
    return value


def _require_key(mapping: Mapping[str, object], key: str, path: str) -> object:
    try:
        return mapping[key]
    except KeyError as exc:
        raise EPSSelectionConfigurationError(f"{path}.{key} is required.") from exc


def _parse_method(value: object, path: str) -> EPSSelectionMethod:
    if isinstance(value, bool) or not isinstance(value, str):
        raise EPSSelectionConfigurationError(f"{path} must be a string.")
    normalized = value.strip().upper()
    try:
        return EPSSelectionMethod(normalized)
    except ValueError as exc:
        raise EPSSelectionConfigurationError(f"{path} is not supported.") from exc


def _normalize_symbol(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise EPSSelectionConfigurationError(f"{path} must be a string.")
    symbol = value.strip().upper()
    if not symbol:
        raise EPSSelectionConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in symbol):
        raise EPSSelectionConfigurationError(f"{path} must not contain whitespace.")
    return symbol


def _require_number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = _require_key(mapping, key, path)
    return _coerce_number(value, f"{path}.{key}")


def _optional_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float | None:
    if key not in mapping:
        return None
    return _coerce_number(mapping[key], f"{path}.{key}")


def _coerce_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EPSSelectionConfigurationError(f"{path} must be a finite number.")
    if not isfinite(value):
        raise EPSSelectionConfigurationError(f"{path} must be finite.")
    return float(value)


def _require_weight(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = _require_number(mapping, key, path)
    if not 0 <= value <= 1:
        raise EPSSelectionConfigurationError(f"{path}.{key} must be between 0 and 1.")
    return value


def _require_non_empty_string(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> str:
    value = _require_key(mapping, key, path)
    text = _optional_string(value, f"{path}.{key}")
    if text is None:
        raise EPSSelectionConfigurationError(f"{path}.{key} must not be empty.")
    return text


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise EPSSelectionConfigurationError(f"{path} must be a string.")
    text = value.strip()
    return text or None
