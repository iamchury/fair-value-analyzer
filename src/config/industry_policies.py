from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


class IndustryPolicyConfigurationError(ValueError):
    pass


class ValuationStyle(str, Enum):
    CYCLICAL = "CYCLICAL"
    GROWTH = "GROWTH"
    QUALITY_GROWTH = "QUALITY_GROWTH"


class TargetPEMode(str, Enum):
    FIXED = "FIXED"
    CALCULATED = "CALCULATED"


@dataclass(frozen=True)
class IndustryValuationPolicy:
    name: str
    valuation_style: ValuationStyle
    target_pe_mode: TargetPEMode
    fixed_target_pe: float | None
    minimum_target_pe: float
    maximum_target_pe: float
    use_eps_growth: bool
    use_peg_adjustment: bool
    use_sector_adjustment: bool
    use_forward_pe_penalty: bool
    rationale: str | None


@dataclass(frozen=True)
class IndustryPolicyConfiguration:
    policies: Mapping[str, IndustryValuationPolicy]
    symbol_policy_names: Mapping[str, str]


def load_industry_policy_configuration(
    path: str | Path = "config/industry_policies.yaml",
) -> IndustryPolicyConfiguration:
    """Load explicit industry valuation policy rules from YAML."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise IndustryPolicyConfigurationError(
            f"{config_path}: failed to read industry policy configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise IndustryPolicyConfigurationError(
            f"{config_path}: invalid YAML in industry policy configuration."
        ) from exc
    if document is None:
        raise IndustryPolicyConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_industry_policy_configuration(document)
    except IndustryPolicyConfigurationError as exc:
        raise IndustryPolicyConfigurationError(f"{config_path}: {exc}") from exc


def parse_industry_policy_configuration(
    document: Mapping[str, object],
) -> IndustryPolicyConfiguration:
    """Parse industry policy YAML content into immutable policy objects."""
    if not isinstance(document, Mapping):
        raise IndustryPolicyConfigurationError("document must be a mapping.")
    _validate_allowed_keys(document, {"policies"}, {"symbols"}, "document")

    policies_section = _require_mapping(document["policies"], "policies")
    if not policies_section:
        raise IndustryPolicyConfigurationError("policies must not be empty.")

    policies: dict[str, IndustryValuationPolicy] = {}
    for raw_name, raw_policy in policies_section.items():
        name = _normalize_policy_name(raw_name, "policies key")
        if name in policies:
            raise IndustryPolicyConfigurationError(f"{name} is duplicated.")
        policies[name] = _parse_policy(
            name,
            _require_mapping(raw_policy, f"policies.{name}"),
        )

    symbols_section = document.get("symbols", {})
    if symbols_section is None:
        symbols_section = {}
    symbols_mapping = _require_mapping(symbols_section, "symbols")
    symbol_policy_names: dict[str, str] = {}
    for raw_symbol, raw_rule in symbols_mapping.items():
        symbol = _normalize_symbol(raw_symbol, "symbols key")
        if symbol in symbol_policy_names:
            raise IndustryPolicyConfigurationError(f"{symbol} is duplicated.")
        rule = _require_mapping(raw_rule, f"symbols.{symbol}")
        _validate_allowed_keys(rule, {"policy"}, set(), f"symbols.{symbol}")
        policy_name = _normalize_policy_name(
            _require_key(rule, "policy", f"symbols.{symbol}"),
            f"symbols.{symbol}.policy",
        )
        if policy_name not in policies:
            raise IndustryPolicyConfigurationError(
                f"symbols.{symbol}.policy references unknown policy {policy_name}."
            )
        symbol_policy_names[symbol] = policy_name

    return IndustryPolicyConfiguration(
        policies=MappingProxyType(policies),
        symbol_policy_names=MappingProxyType(symbol_policy_names),
    )


def _parse_policy(
    name: str,
    policy: Mapping[str, object],
) -> IndustryValuationPolicy:
    path = f"policies.{name}"
    _validate_allowed_keys(
        policy,
        {
            "valuation_style",
            "target_pe_mode",
            "fixed_target_pe",
            "minimum_target_pe",
            "maximum_target_pe",
            "use_eps_growth",
            "use_peg_adjustment",
            "use_sector_adjustment",
            "use_forward_pe_penalty",
            "rationale",
        },
        set(),
        path,
    )
    target_pe_mode = _parse_mode(_require_key(policy, "target_pe_mode", path))
    fixed_target_pe = _optional_number(policy, "fixed_target_pe", path)
    minimum_target_pe = _require_positive_number(policy, "minimum_target_pe", path)
    maximum_target_pe = _require_positive_number(policy, "maximum_target_pe", path)
    if minimum_target_pe > maximum_target_pe:
        raise IndustryPolicyConfigurationError(
            f"{path}.minimum_target_pe must be no more than maximum_target_pe."
        )
    if maximum_target_pe > 200:
        raise IndustryPolicyConfigurationError(
            f"{path}.maximum_target_pe must be no more than 200."
        )

    use_eps_growth = _require_bool(policy, "use_eps_growth", path)
    use_peg_adjustment = _require_bool(policy, "use_peg_adjustment", path)
    use_sector_adjustment = _require_bool(policy, "use_sector_adjustment", path)
    use_forward_pe_penalty = _require_bool(policy, "use_forward_pe_penalty", path)

    if target_pe_mode == TargetPEMode.FIXED:
        if fixed_target_pe is None:
            raise IndustryPolicyConfigurationError(
                f"{path}.fixed_target_pe is required for fixed mode."
            )
        if not minimum_target_pe <= fixed_target_pe <= maximum_target_pe:
            raise IndustryPolicyConfigurationError(
                f"{path}.fixed_target_pe must be within the configured PE range."
            )
        if (
            use_eps_growth
            or use_peg_adjustment
            or use_sector_adjustment
            or use_forward_pe_penalty
        ):
            raise IndustryPolicyConfigurationError(
                f"{path}: fixed mode does not support enabled adjustments."
            )
    elif fixed_target_pe is not None:
        raise IndustryPolicyConfigurationError(
            f"{path}.fixed_target_pe must be null for calculated mode."
        )

    return IndustryValuationPolicy(
        name=name,
        valuation_style=_parse_style(_require_key(policy, "valuation_style", path)),
        target_pe_mode=target_pe_mode,
        fixed_target_pe=fixed_target_pe,
        minimum_target_pe=minimum_target_pe,
        maximum_target_pe=maximum_target_pe,
        use_eps_growth=use_eps_growth,
        use_peg_adjustment=use_peg_adjustment,
        use_sector_adjustment=use_sector_adjustment,
        use_forward_pe_penalty=use_forward_pe_penalty,
        rationale=_optional_string(policy["rationale"], f"{path}.rationale"),
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
        raise IndustryPolicyConfigurationError(
            f"{path}.{sorted(missing_keys)[0]} is required."
        )
    if unexpected_keys:
        raise IndustryPolicyConfigurationError(
            f"{path}.{sorted(unexpected_keys)[0]} is not supported."
        )


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise IndustryPolicyConfigurationError(f"{path} must be a mapping.")
    return value


def _require_key(mapping: Mapping[str, object], key: str, path: str) -> object:
    try:
        return mapping[key]
    except KeyError as exc:
        raise IndustryPolicyConfigurationError(f"{path}.{key} is required.") from exc


def _parse_style(value: object) -> ValuationStyle:
    if isinstance(value, bool) or not isinstance(value, str):
        raise IndustryPolicyConfigurationError("valuation_style must be a string.")
    try:
        return ValuationStyle(value.strip().upper())
    except ValueError as exc:
        raise IndustryPolicyConfigurationError(
            "valuation_style is not supported."
        ) from exc


def _parse_mode(value: object) -> TargetPEMode:
    if isinstance(value, bool) or not isinstance(value, str):
        raise IndustryPolicyConfigurationError("target_pe_mode must be a string.")
    try:
        return TargetPEMode(value.strip().upper())
    except ValueError as exc:
        raise IndustryPolicyConfigurationError(
            "target_pe_mode is not supported."
        ) from exc


def _normalize_policy_name(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise IndustryPolicyConfigurationError(f"{path} must be a string.")
    name = value.strip().upper()
    if not name:
        raise IndustryPolicyConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in name):
        raise IndustryPolicyConfigurationError(f"{path} must not contain whitespace.")
    return name


def _normalize_symbol(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise IndustryPolicyConfigurationError(f"{path} must be a string.")
    symbol = value.strip().upper()
    if not symbol:
        raise IndustryPolicyConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in symbol):
        raise IndustryPolicyConfigurationError(f"{path} must not contain whitespace.")
    return symbol


def _require_positive_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float:
    value = _require_number(mapping, key, path)
    if value <= 0:
        raise IndustryPolicyConfigurationError(
            f"{path}.{key} must be greater than 0."
        )
    return value


def _require_number(mapping: Mapping[str, object], key: str, path: str) -> float:
    return _coerce_number(_require_key(mapping, key, path), f"{path}.{key}")


def _optional_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float | None:
    value = _require_key(mapping, key, path)
    if value is None:
        return None
    return _coerce_number(value, f"{path}.{key}")


def _coerce_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IndustryPolicyConfigurationError(f"{path} must be a finite number.")
    if not isfinite(value):
        raise IndustryPolicyConfigurationError(f"{path} must be finite.")
    return float(value)


def _require_bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = _require_key(mapping, key, path)
    if not isinstance(value, bool):
        raise IndustryPolicyConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise IndustryPolicyConfigurationError(f"{path} must be a string.")
    text = value.strip()
    return text or None
