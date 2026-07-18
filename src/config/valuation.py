from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from src.analysis.macro_adjustment import (
    TreasuryYieldConfig,
    validate_config as validate_treasury_yield_config,
)
from src.analysis.target_pe import TargetPEConfig, validate_target_pe_config
from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    validate_valuation_decision_config,
)
from src.yahoo.treasury import TreasuryHistoryConfig, validate_history_config


class ValuationConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ValuationConfiguration:
    treasury_history: TreasuryHistoryConfig
    treasury_yield: TreasuryYieldConfig
    target_pe: TargetPEConfig
    decision: ValuationDecisionConfig


def load_valuation_configuration(
    path: str | Path = "config/valuation.yaml",
) -> ValuationConfiguration:
    """Load valuation configuration from a YAML file."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = _safe_load_yaml(file)
    except OSError as exc:
        raise ValuationConfigurationError(
            f"{config_path}: failed to read valuation configuration."
        ) from exc
    except _yaml_error_types() as exc:
        raise ValuationConfigurationError(
            f"{config_path}: invalid YAML in valuation configuration."
        ) from exc

    if document is None:
        raise ValuationConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_valuation_configuration(document)
    except ValuationConfigurationError as exc:
        raise ValuationConfigurationError(
            f"{config_path}: {exc}"
        ) from exc


def parse_valuation_configuration(
    document: Mapping[str, object],
) -> ValuationConfiguration:
    """Construct valuation config dataclasses from a parsed YAML mapping."""
    root = _require_mapping(document, "document")
    _validate_exact_keys(root, {"macro", "valuation"}, "document")

    macro = _require_mapping(_require_key(root, "macro", "macro"), "macro")
    _validate_allowed_keys(
        macro,
        required_keys={"treasury_yield"},
        optional_keys={"federal_reserve"},
        path="macro",
    )
    treasury_section = _require_mapping(
        _require_key(macro, "treasury_yield", "macro.treasury_yield"),
        "macro.treasury_yield",
    )

    valuation = _require_mapping(
        _require_key(root, "valuation", "valuation"),
        "valuation",
    )
    _validate_exact_keys(valuation, {"target_pe", "decision"}, "valuation")
    target_pe_section = _require_mapping(
        _require_key(valuation, "target_pe", "valuation.target_pe"),
        "valuation.target_pe",
    )
    decision_section = _require_mapping(
        _require_key(valuation, "decision", "valuation.decision"),
        "valuation.decision",
    )

    treasury_history = _build_treasury_history_config(treasury_section)
    treasury_yield = _build_treasury_yield_config(treasury_section)
    target_pe = _build_target_pe_config(target_pe_section)
    decision = _build_decision_config(decision_section)

    return ValuationConfiguration(
        treasury_history=treasury_history,
        treasury_yield=treasury_yield,
        target_pe=target_pe,
        decision=decision,
    )


def _build_treasury_history_config(
    section: Mapping[str, object],
) -> TreasuryHistoryConfig:
    _validate_exact_keys(
        section,
        _TREASURY_HISTORY_KEYS | _TREASURY_YIELD_KEYS,
        "macro.treasury_yield",
    )
    config = TreasuryHistoryConfig(
        symbol=_require_string(section, "symbol", "macro.treasury_yield"),
        value_scale=_require_string(section, "value_scale", "macro.treasury_yield"),
        short_window_observations=_require_integer(
            section,
            "short_window_observations",
            "macro.treasury_yield",
        ),
        long_window_observations=_require_integer(
            section,
            "long_window_observations",
            "macro.treasury_yield",
        ),
    )
    _validate_domain(config, validate_history_config, "macro.treasury_yield")
    return config


def _build_treasury_yield_config(
    section: Mapping[str, object],
) -> TreasuryYieldConfig:
    config = TreasuryYieldConfig(
        threshold_yield_percent=_require_real_number(
            section,
            "threshold_yield_percent",
            "macro.treasury_yield",
        ),
        maximum_discount_percent=_require_real_number(
            section,
            "maximum_discount_percent",
            "macro.treasury_yield",
        ),
        trend_tolerance_percentage_points=_require_real_number(
            section,
            "trend_tolerance_percentage_points",
            "macro.treasury_yield",
        ),
        rising_adjustment_percent=_require_real_number(
            section,
            "rising_adjustment_percent",
            "macro.treasury_yield",
        ),
        neutral_adjustment_percent=_require_real_number(
            section,
            "neutral_adjustment_percent",
            "macro.treasury_yield",
        ),
        falling_adjustment_percent=_require_real_number(
            section,
            "falling_adjustment_percent",
            "macro.treasury_yield",
        ),
    )
    _validate_domain(config, validate_treasury_yield_config, "macro.treasury_yield")
    return config


def _build_target_pe_config(section: Mapping[str, object]) -> TargetPEConfig:
    _validate_exact_keys(section, _TARGET_PE_KEYS, "valuation.target_pe")
    config = TargetPEConfig(
        minimum_target_pe=_require_real_number(
            section, "minimum_target_pe", "valuation.target_pe"
        ),
        maximum_target_pe=_require_real_number(
            section, "maximum_target_pe", "valuation.target_pe"
        ),
        default_target_peg=_require_real_number(
            section, "default_target_peg", "valuation.target_pe"
        ),
        maximum_eps_growth_percent=_require_real_number(
            section, "maximum_eps_growth_percent", "valuation.target_pe"
        ),
        low_peg_threshold=_require_real_number(
            section, "low_peg_threshold", "valuation.target_pe"
        ),
        normal_peg_upper_threshold=_require_real_number(
            section, "normal_peg_upper_threshold", "valuation.target_pe"
        ),
        high_peg_threshold=_require_real_number(
            section, "high_peg_threshold", "valuation.target_pe"
        ),
        low_peg_adjustment=_require_real_number(
            section, "low_peg_adjustment", "valuation.target_pe"
        ),
        normal_peg_adjustment=_require_real_number(
            section, "normal_peg_adjustment", "valuation.target_pe"
        ),
        elevated_peg_adjustment=_require_real_number(
            section, "elevated_peg_adjustment", "valuation.target_pe"
        ),
        high_peg_adjustment=_require_real_number(
            section, "high_peg_adjustment", "valuation.target_pe"
        ),
        preferred_sector_adjustment=_require_real_number(
            section, "preferred_sector_adjustment", "valuation.target_pe"
        ),
        ordinary_sector_adjustment=_require_real_number(
            section, "ordinary_sector_adjustment", "valuation.target_pe"
        ),
        high_forward_pe_premium_threshold=_require_real_number(
            section, "high_forward_pe_premium_threshold", "valuation.target_pe"
        ),
        high_forward_pe_adjustment=_require_real_number(
            section, "high_forward_pe_adjustment", "valuation.target_pe"
        ),
        preferred_sectors=_require_string_sequence(
            section, "preferred_sectors", "valuation.target_pe"
        ),
    )
    _validate_domain(config, validate_target_pe_config, "valuation.target_pe")
    return config


def _build_decision_config(
    section: Mapping[str, object],
) -> ValuationDecisionConfig:
    _validate_exact_keys(section, _DECISION_KEYS, "valuation.decision")
    config = ValuationDecisionConfig(
        buy_discount_percent=_require_real_number(
            section, "buy_discount_percent", "valuation.decision"
        ),
        sell_premium_percent=_require_real_number(
            section, "sell_premium_percent", "valuation.decision"
        ),
    )
    _validate_domain(config, validate_valuation_decision_config, "valuation.decision")
    return config


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValuationConfigurationError(f"{path} must be a mapping.")
    return value


def _validate_exact_keys(
    mapping: Mapping[str, object],
    expected_keys: set[str],
    path: str,
) -> None:
    actual_keys = set(mapping)
    missing_keys = expected_keys - actual_keys
    unexpected_keys = actual_keys - expected_keys

    if missing_keys:
        key = sorted(missing_keys)[0]
        raise ValuationConfigurationError(f"{path}.{key} is required.")
    if unexpected_keys:
        key = sorted(unexpected_keys)[0]
        raise ValuationConfigurationError(f"{path}.{key} is not supported.")


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
        key = sorted(missing_keys)[0]
        raise ValuationConfigurationError(f"{path}.{key} is required.")
    if unexpected_keys:
        key = sorted(unexpected_keys)[0]
        raise ValuationConfigurationError(f"{path}.{key} is not supported.")


def _require_key(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> object:
    try:
        return mapping[key]
    except KeyError as exc:
        raise ValuationConfigurationError(f"{path} is required.") from exc


def _require_real_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float:
    value = _require_key(mapping, key, f"{path}.{key}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValuationConfigurationError(f"{path}.{key} must be a real number.")
    if not isfinite(value):
        raise ValuationConfigurationError(f"{path}.{key} must be finite.")
    return value


def _require_integer(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> int:
    value = _require_key(mapping, key, f"{path}.{key}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValuationConfigurationError(f"{path}.{key} must be an integer.")
    return value


def _require_string(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> str:
    value = _require_key(mapping, key, f"{path}.{key}")
    if not isinstance(value, str):
        raise ValuationConfigurationError(f"{path}.{key} must be a string.")
    return value


def _require_string_sequence(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> tuple[str, ...]:
    value = _require_key(mapping, key, f"{path}.{key}")
    if not isinstance(value, list):
        raise ValuationConfigurationError(f"{path}.{key} must be a list.")

    sectors = []
    for index, item in enumerate(value):
        item_path = f"{path}.{key}[{index}]"
        if not isinstance(item, str):
            raise ValuationConfigurationError(f"{item_path} must be a string.")
        stripped = item.strip()
        if not stripped:
            raise ValuationConfigurationError(f"{item_path} must not be empty.")
        sectors.append(stripped)
    return tuple(sectors)


def _validate_domain(config: Any, validator: Any, path: str) -> None:
    try:
        validator(config)
    except ValueError as exc:
        raise ValuationConfigurationError(f"{path}: {exc}") from exc


def _safe_load_yaml(file: Any) -> object:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ValuationConfigurationError(
            "PyYAML is required to load valuation configuration files."
        ) from exc
    return yaml.safe_load(file)


def _yaml_error_types() -> tuple[type[BaseException], ...]:
    try:
        import yaml
    except ModuleNotFoundError:
        return ()
    return (yaml.YAMLError,)


_TREASURY_HISTORY_KEYS = {
    "symbol",
    "value_scale",
    "short_window_observations",
    "long_window_observations",
}

_TREASURY_YIELD_KEYS = {
    "threshold_yield_percent",
    "maximum_discount_percent",
    "trend_tolerance_percentage_points",
    "rising_adjustment_percent",
    "neutral_adjustment_percent",
    "falling_adjustment_percent",
}

_TARGET_PE_KEYS = {
    "minimum_target_pe",
    "maximum_target_pe",
    "default_target_peg",
    "maximum_eps_growth_percent",
    "low_peg_threshold",
    "normal_peg_upper_threshold",
    "high_peg_threshold",
    "low_peg_adjustment",
    "normal_peg_adjustment",
    "elevated_peg_adjustment",
    "high_peg_adjustment",
    "preferred_sector_adjustment",
    "ordinary_sector_adjustment",
    "high_forward_pe_premium_threshold",
    "high_forward_pe_adjustment",
    "preferred_sectors",
}

_DECISION_KEYS = {
    "buy_discount_percent",
    "sell_premium_percent",
}
