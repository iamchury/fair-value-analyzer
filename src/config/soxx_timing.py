from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from math import isfinite
from pathlib import Path
from typing import Any

from src.analysis.soxx_timing import SoxxTimingConfiguration, validate_soxx_timing_config


class SoxxTimingConfigurationError(ValueError):
    pass


def load_soxx_timing_configuration(path: str | Path = "config/soxx_timing.yaml") -> SoxxTimingConfiguration:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = _safe_load_yaml(file)
    except OSError as exc:
        raise SoxxTimingConfigurationError(f"{config_path}: failed to read SOXX timing configuration.") from exc
    except _yaml_error_types() as exc:
        raise SoxxTimingConfigurationError(f"{config_path}: invalid YAML in SOXX timing configuration.") from exc
    try:
        return parse_soxx_timing_configuration(document)
    except SoxxTimingConfigurationError as exc:
        raise SoxxTimingConfigurationError(f"{config_path}: {exc}") from exc


def parse_soxx_timing_configuration(document: object) -> SoxxTimingConfiguration:
    root = _mapping(document, "document")
    allowed = {
        "symbol",
        "history",
        "moving_averages",
        "cross",
        "moving_average_convergence",
        "prior_high",
        "thresholds",
        "display",
    }
    _reject_unknown(root, allowed, "document")
    history = _mapping(root.get("history", {}), "history")
    moving = _mapping(root.get("moving_averages", {}), "moving_averages")
    levels = _mapping(moving.get("buy_sell_levels", {}), "moving_averages.buy_sell_levels")
    cross = _mapping(root.get("cross", {}), "cross")
    convergence = _mapping(root.get("moving_average_convergence", {}), "moving_average_convergence")
    prior_high = _mapping(root.get("prior_high", {}), "prior_high")
    thresholds = _mapping(root.get("thresholds", {}), "thresholds")
    display = _mapping(root.get("display", {}), "display")
    _reject_unknown(history, {"period", "interval", "minimum_observations", "price_field_preference"}, "history")
    _reject_unknown(moving, {"fast", "buy_sell_levels", "long"}, "moving_averages")
    _reject_unknown(levels, {"initial", "strong", "very_strong"}, "moving_averages.buy_sell_levels")
    _reject_unknown(cross, {"confirmation_days", "completed_trading_day_only"}, "cross")
    _reject_unknown(convergence, {"enabled", "periods", "max_spread_pct"}, "moving_average_convergence")
    _reject_unknown(prior_high, {"lookback_trading_days", "exclude_current_day"}, "prior_high")
    _reject_unknown(thresholds, {"sell_caution_drawdown_pct", "strong_buy_drawdown_pct"}, "thresholds")
    _reject_unknown(
        display,
        {
            "enabled",
            "show_chart",
            "show_signal_history",
            "signal_history_days",
            "default_chart_period",
            "show_prior_high",
            "show_drawdown",
            "show_moving_averages",
            "show_all_crosses",
        },
        "display",
    )
    config = replace(
        SoxxTimingConfiguration(),
        symbol=_string(root, "symbol", "document", "SOXX"),
        period=_string(history, "period", "history", "2y"),
        interval=_string(history, "interval", "history", "1d"),
        minimum_observations=_integer(history, "minimum_observations", "history", 60),
        price_field_preference=_string_tuple(
            history,
            "price_field_preference",
            "history",
            ("Adj Close", "Close"),
        ),
        fast_period=_integer(moving, "fast", "moving_averages", 5),
        initial_period=_integer(levels, "initial", "moving_averages.buy_sell_levels", 10),
        strong_period=_integer(levels, "strong", "moving_averages.buy_sell_levels", 15),
        very_strong_period=_integer(levels, "very_strong", "moving_averages.buy_sell_levels", 20),
        long_period=_integer(moving, "long", "moving_averages", 50),
        confirmation_days=_integer(cross, "confirmation_days", "cross", 1),
        completed_trading_day_only=_boolean(cross, "completed_trading_day_only", "cross", True),
        convergence_enabled=_boolean(convergence, "enabled", "moving_average_convergence", True),
        convergence_periods=_integer_tuple(convergence, "periods", "moving_average_convergence", (5, 10, 15, 20)),
        convergence_max_spread_pct=_number(convergence, "max_spread_pct", "moving_average_convergence", 1.5),
        prior_high_lookback_trading_days=_integer(prior_high, "lookback_trading_days", "prior_high", 252),
        prior_high_exclude_current_day=_boolean(prior_high, "exclude_current_day", "prior_high", True),
        sell_caution_drawdown_pct=_number(thresholds, "sell_caution_drawdown_pct", "thresholds", -10.0),
        strong_buy_drawdown_pct=_number(thresholds, "strong_buy_drawdown_pct", "thresholds", -30.0),
        display_enabled=_boolean(display, "enabled", "display", True),
        show_chart=_boolean(display, "show_chart", "display", True),
        show_signal_history=_boolean(display, "show_signal_history", "display", True),
        signal_history_days=_integer(display, "signal_history_days", "display", 120),
        default_chart_period=_string(display, "default_chart_period", "display", "6m"),
        show_prior_high=_boolean(display, "show_prior_high", "display", True),
        show_drawdown=_boolean(display, "show_drawdown", "display", True),
        show_moving_averages=_boolean(display, "show_moving_averages", "display", True),
        show_all_crosses=_boolean(display, "show_all_crosses", "display", True),
    )
    try:
        validate_soxx_timing_config(config)
    except ValueError as exc:
        raise SoxxTimingConfigurationError(str(exc)) from exc
    return config


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SoxxTimingConfigurationError(f"{path} must be a mapping.")
    return value


def _reject_unknown(mapping: Mapping[str, object], allowed: set[str], path: str) -> None:
    for key in mapping:
        if key not in allowed:
            raise SoxxTimingConfigurationError(f"{path}.{key} is not supported.")


def _string(mapping: Mapping[str, object], key: str, path: str, default: str) -> str:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise SoxxTimingConfigurationError(f"{path}.{key} must be a non-empty string.")
    return value.strip()


def _integer(mapping: Mapping[str, object], key: str, path: str, default: int) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SoxxTimingConfigurationError(f"{path}.{key} must be an integer.")
    return value


def _number(mapping: Mapping[str, object], key: str, path: str, default: float) -> float:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise SoxxTimingConfigurationError(f"{path}.{key} must be finite.")
    return float(value)


def _boolean(mapping: Mapping[str, object], key: str, path: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise SoxxTimingConfigurationError(f"{path}.{key} must be a boolean.")
    return value


def _string_tuple(mapping: Mapping[str, object], key: str, path: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = mapping.get(key, default)
    if not isinstance(value, (list, tuple)) or not value:
        raise SoxxTimingConfigurationError(f"{path}.{key} must be a non-empty list.")
    result = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, str) or not item.strip():
            raise SoxxTimingConfigurationError(f"{path}.{key}[{index}] must be a non-empty string.")
        result.append(item.strip())
    return tuple(result)


def _integer_tuple(mapping: Mapping[str, object], key: str, path: str, default: tuple[int, ...]) -> tuple[int, ...]:
    value = mapping.get(key, default)
    if not isinstance(value, (list, tuple)) or not value:
        raise SoxxTimingConfigurationError(f"{path}.{key} must be a non-empty list.")
    result = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise SoxxTimingConfigurationError(f"{path}.{key}[{index}] must be an integer.")
        result.append(item)
    return tuple(result)


def _safe_load_yaml(file: Any) -> object:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise SoxxTimingConfigurationError("PyYAML is required to load SOXX timing configuration files.") from exc
    return yaml.safe_load(file)


def _yaml_error_types() -> tuple[type[BaseException], ...]:
    try:
        import yaml
    except ModuleNotFoundError:
        return ()
    return (yaml.YAMLError,)
