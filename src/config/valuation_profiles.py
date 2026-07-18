from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


class ValuationProfileConfigurationError(ValueError):
    pass


class ValuationStyle(str, Enum):
    GROWTH = "GROWTH"
    CYCLICAL = "CYCLICAL"
    QUALITY_GROWTH = "QUALITY_GROWTH"


@dataclass(frozen=True)
class ValuationProfile:
    symbol: str
    valuation_style: ValuationStyle
    valuation_eps: float
    eps_fiscal_year: str
    target_pe: float
    use_peg_adjustment: bool
    dcf_fair_value: float | None
    source_note: str | None


def parse_valuation_profiles(
    document: Mapping[str, object],
) -> Mapping[str, ValuationProfile]:
    """Parse valuation profile YAML content into immutable profile objects."""
    if not isinstance(document, Mapping):
        raise ValuationProfileConfigurationError("document must be a mapping.")
    _validate_exact_keys(document, {"profiles"}, "document")

    profiles_section = document["profiles"]
    if not isinstance(profiles_section, Mapping):
        raise ValuationProfileConfigurationError("profiles must be a mapping.")
    if not profiles_section:
        raise ValuationProfileConfigurationError("profiles must not be empty.")

    profiles: dict[str, ValuationProfile] = {}
    for raw_symbol, raw_profile in profiles_section.items():
        symbol = _normalize_symbol(raw_symbol, "profiles key")
        if symbol in profiles:
            raise ValuationProfileConfigurationError(f"{symbol} is duplicated.")
        if not isinstance(raw_profile, Mapping):
            raise ValuationProfileConfigurationError(
                f"profiles.{symbol} must be a mapping."
            )
        profiles[symbol] = _parse_profile(symbol, raw_profile)
    return MappingProxyType(profiles)


def load_valuation_profiles(
    path: str | Path = "config/valuation_profiles.yaml",
) -> Mapping[str, ValuationProfile]:
    """Load valuation profiles from a YAML file."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise ValuationProfileConfigurationError(
            f"{config_path}: failed to read valuation profiles."
        ) from exc
    except yaml.YAMLError as exc:
        raise ValuationProfileConfigurationError(
            f"{config_path}: invalid YAML in valuation profiles."
        ) from exc

    if document is None:
        raise ValuationProfileConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_valuation_profiles(document)
    except ValuationProfileConfigurationError as exc:
        raise ValuationProfileConfigurationError(f"{config_path}: {exc}") from exc


def _parse_profile(
    symbol: str,
    profile: Mapping[str, object],
) -> ValuationProfile:
    path = f"profiles.{symbol}"
    _validate_exact_keys(
        profile,
        {
            "valuation_style",
            "valuation_eps",
            "eps_fiscal_year",
            "target_pe",
            "use_peg_adjustment",
            "dcf_fair_value",
            "source_note",
        },
        path,
    )
    return ValuationProfile(
        symbol=symbol,
        valuation_style=_parse_style(_require_key(profile, "valuation_style", path)),
        valuation_eps=_require_finite_number(profile, "valuation_eps", path),
        eps_fiscal_year=_require_non_empty_string(profile, "eps_fiscal_year", path),
        target_pe=_require_positive_number(profile, "target_pe", path, maximum=200),
        use_peg_adjustment=_require_bool(profile, "use_peg_adjustment", path),
        dcf_fair_value=_require_optional_positive_number(
            profile,
            "dcf_fair_value",
            path,
        ),
        source_note=_optional_string(profile["source_note"], f"{path}.source_note"),
    )


def _validate_exact_keys(
    mapping: Mapping[str, object],
    expected_keys: set[str],
    path: str,
) -> None:
    actual_keys = set(mapping)
    missing_keys = expected_keys - actual_keys
    unexpected_keys = actual_keys - expected_keys
    if missing_keys:
        raise ValuationProfileConfigurationError(
            f"{path}.{sorted(missing_keys)[0]} is required."
        )
    if unexpected_keys:
        raise ValuationProfileConfigurationError(
            f"{path}.{sorted(unexpected_keys)[0]} is not supported."
        )


def _require_key(mapping: Mapping[str, object], key: str, path: str) -> object:
    try:
        return mapping[key]
    except KeyError as exc:
        raise ValuationProfileConfigurationError(f"{path}.{key} is required.") from exc


def _normalize_symbol(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValuationProfileConfigurationError(f"{path} must be a string.")
    symbol = value.strip().upper()
    if not symbol:
        raise ValuationProfileConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in symbol):
        raise ValuationProfileConfigurationError(
            f"{path} must not contain whitespace."
        )
    return symbol


def _parse_style(value: object) -> ValuationStyle:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValuationProfileConfigurationError(
            "valuation_style must be a string."
        )
    normalized = value.strip().upper()
    try:
        return ValuationStyle(normalized)
    except ValueError as exc:
        raise ValuationProfileConfigurationError(
            "valuation_style is not supported."
        ) from exc


def _require_finite_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float:
    value = _require_key(mapping, key, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must be a finite number."
        )
    if not isfinite(value):
        raise ValuationProfileConfigurationError(f"{path}.{key} must be finite.")
    return float(value)


def _require_positive_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
    maximum: float | None = None,
) -> float:
    value = _require_finite_number(mapping, key, path)
    if value <= 0:
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must be greater than 0."
        )
    if maximum is not None and value > maximum:
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must be no more than {maximum}."
        )
    return value


def _require_optional_positive_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float | None:
    value = _require_key(mapping, key, path)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must be a finite number or null."
        )
    if not isfinite(value):
        raise ValuationProfileConfigurationError(f"{path}.{key} must be finite.")
    if value <= 0:
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must be greater than 0."
        )
    return float(value)


def _require_non_empty_string(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> str:
    value = _require_key(mapping, key, path)
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValuationProfileConfigurationError(f"{path}.{key} must be a string.")
    text = value.strip()
    if not text:
        raise ValuationProfileConfigurationError(
            f"{path}.{key} must not be empty."
        )
    return text


def _require_bool(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = _require_key(mapping, key, path)
    if not isinstance(value, bool):
        raise ValuationProfileConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValuationProfileConfigurationError(f"{path} must be a string or null.")
    text = value.strip()
    return text or None
