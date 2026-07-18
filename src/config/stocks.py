from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class StocksConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class StocksConfiguration:
    symbols: tuple[str, ...]


def parse_stocks_configuration(
    document: Mapping[str, object],
) -> StocksConfiguration:
    """Parse and validate a stocks.yaml document."""
    if not isinstance(document, Mapping):
        raise StocksConfigurationError("document must be a mapping.")

    actual_keys = set(document)
    if "stocks" not in actual_keys:
        raise StocksConfigurationError("stocks is required.")
    unexpected_keys = actual_keys - {"stocks"}
    if unexpected_keys:
        key = sorted(unexpected_keys)[0]
        raise StocksConfigurationError(f"{key} is not supported.")

    raw_symbols = document["stocks"]
    if not isinstance(raw_symbols, list):
        raise StocksConfigurationError("stocks must be a list.")
    if not raw_symbols:
        raise StocksConfigurationError("stocks must not be empty.")

    symbols: list[str] = []
    seen: set[str] = set()
    for index, raw_symbol in enumerate(raw_symbols):
        symbol = _normalize_symbol(raw_symbol, f"stocks[{index}]")
        if symbol in seen:
            raise StocksConfigurationError(f"{symbol} is duplicated.")
        seen.add(symbol)
        symbols.append(symbol)

    return StocksConfiguration(symbols=tuple(symbols))


def load_stocks_configuration(
    path: str | Path = "config/stocks.yaml",
) -> StocksConfiguration:
    """Load stocks configuration from a YAML file."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file)
    except OSError as exc:
        raise StocksConfigurationError(
            f"{config_path}: failed to read stocks configuration."
        ) from exc
    except yaml.YAMLError as exc:
        raise StocksConfigurationError(
            f"{config_path}: invalid YAML in stocks configuration."
        ) from exc

    if document is None:
        raise StocksConfigurationError(
            f"{config_path}: YAML document must not be empty."
        )
    try:
        return parse_stocks_configuration(document)
    except StocksConfigurationError as exc:
        raise StocksConfigurationError(f"{config_path}: {exc}") from exc


def _normalize_symbol(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise StocksConfigurationError(f"{path} must be a string.")

    symbol = value.strip().upper()
    if not symbol:
        raise StocksConfigurationError(f"{path} must not be empty.")
    if any(character.isspace() for character in symbol):
        raise StocksConfigurationError(f"{path} must not contain whitespace.")
    return symbol
