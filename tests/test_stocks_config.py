from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.config.stocks import (
    StocksConfiguration,
    StocksConfigurationError,
    load_stocks_configuration,
    parse_stocks_configuration,
)


def test_valid_stocks_configuration_is_normalized_tuple() -> None:
    config = parse_stocks_configuration(
        {"stocks": [" lite ", "^sox", "brk-b", "brk.b", "usd=krw"]}
    )

    assert config == StocksConfiguration(
        symbols=("LITE", "^SOX", "BRK-B", "BRK.B", "USD=KRW")
    )
    assert isinstance(config.symbols, tuple)


def test_stocks_configuration_is_immutable() -> None:
    config = parse_stocks_configuration({"stocks": ["LITE"]})

    with pytest.raises(FrozenInstanceError):
        config.symbols = ("MU",)


def test_actual_repository_stocks_yaml_loads_successfully() -> None:
    config = load_stocks_configuration("config/stocks.yaml")

    assert config.symbols == ("LITE", "MU", "AMAT", "NVDA", "GLW")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({}, "stocks is required"),
        ({"stocks": ["LITE"], "extra": []}, "extra is not supported"),
        ([], "document must be a mapping"),
        ({"stocks": "LITE"}, "stocks must be a list"),
        ({"stocks": []}, "stocks must not be empty"),
        ({"stocks": [123]}, "stocks\\[0\\] must be a string"),
        ({"stocks": [None]}, "stocks\\[0\\] must be a string"),
        ({"stocks": [True]}, "stocks\\[0\\] must be a string"),
        ({"stocks": [""]}, "stocks\\[0\\] must not be empty"),
        ({"stocks": ["   "]}, "stocks\\[0\\] must not be empty"),
        ({"stocks": ["BRK B"]}, "stocks\\[0\\] must not contain whitespace"),
        ({"stocks": ["LITE", "LITE"]}, "LITE is duplicated"),
        ({"stocks": ["LITE", " lite "]}, "LITE is duplicated"),
    ],
)
def test_invalid_stocks_configuration_rejected(
    document: object,
    message: str,
) -> None:
    with pytest.raises(StocksConfigurationError, match=message):
        parse_stocks_configuration(document)


def test_load_accepts_string_and_path_inputs(tmp_path: Path) -> None:
    path = tmp_path / "stocks.yaml"
    path.write_text("stocks:\n  - lite\n", encoding="utf-8")

    assert load_stocks_configuration(str(path)).symbols == ("LITE",)
    assert load_stocks_configuration(path).symbols == ("LITE",)


def test_missing_file_is_wrapped_with_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(StocksConfigurationError) as exc_info:
        load_stocks_configuration(path)

    assert str(path) in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


def test_malformed_yaml_is_wrapped_with_path(tmp_path: Path) -> None:
    path = tmp_path / "stocks.yaml"
    path.write_text("stocks: [LITE\n", encoding="utf-8")

    with pytest.raises(StocksConfigurationError) as exc_info:
        load_stocks_configuration(path)

    assert str(path) in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_empty_yaml_is_rejected_with_path(tmp_path: Path) -> None:
    path = tmp_path / "stocks.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(StocksConfigurationError) as exc_info:
        load_stocks_configuration(path)

    assert str(path) in str(exc_info.value)


def test_file_level_parse_error_chains_original_config_error(tmp_path: Path) -> None:
    path = tmp_path / "stocks.yaml"
    path.write_text("stocks: []\n", encoding="utf-8")

    with pytest.raises(StocksConfigurationError) as exc_info:
        load_stocks_configuration(path)

    assert str(path) in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, StocksConfigurationError)
