from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path

import pytest

from src.analysis.macro_adjustment import TreasuryYieldConfig
from src.analysis.target_pe import TargetPEConfig
from src.analysis.valuation_decision import ValuationDecisionConfig
from src.config.valuation import (
    ValuationConfiguration,
    ValuationConfigurationError,
    load_valuation_configuration,
    parse_valuation_configuration,
)
from src.yahoo.treasury import TreasuryHistoryConfig


requires_yaml = pytest.mark.skipif(
    importlib.util.find_spec("yaml") is None,
    reason="PyYAML is not installed in this environment.",
)


def valid_document() -> dict:
    return {
        "macro": {
            "treasury_yield": {
                "symbol": "^TNX",
                "value_scale": "percent",
                "threshold_yield_percent": 4.3,
                "maximum_discount_percent": 25.0,
                "short_window_observations": 20,
                "long_window_observations": 60,
                "trend_tolerance_percentage_points": 0.05,
                "rising_adjustment_percent": -10.0,
                "neutral_adjustment_percent": 0.0,
                "falling_adjustment_percent": 10.0,
            },
            "federal_reserve": {
                "collect_policy_rate": False,
                "apply_policy_rate_adjustment": False,
            },
        },
        "valuation": {
            "target_pe": {
                "minimum_target_pe": 15.0,
                "maximum_target_pe": 50.0,
                "default_target_peg": 1.0,
                "low_peg_threshold": 1.0,
                "normal_peg_upper_threshold": 1.5,
                "high_peg_threshold": 2.0,
                "low_peg_adjustment": 5.0,
                "normal_peg_adjustment": 0.0,
                "elevated_peg_adjustment": -2.0,
                "high_peg_adjustment": -5.0,
                "preferred_sector_adjustment": 5.0,
                "ordinary_sector_adjustment": 0.0,
                "high_forward_pe_premium_threshold": 1.5,
                "high_forward_pe_adjustment": -2.0,
                "preferred_sectors": [
                    " Technology ",
                    "Semiconductors",
                    "Semiconductor Equipment",
                ],
            },
            "decision": {
                "buy_discount_percent": 20.0,
                "sell_premium_percent": 20.0,
            },
        },
    }


def write_yaml(path: Path, document: object) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def assert_config_error(
    document: object,
    expected_path: str,
) -> None:
    with pytest.raises(ValuationConfigurationError, match=expected_path):
        parse_valuation_configuration(document)


def test_parse_complete_valid_mapping() -> None:
    result = parse_valuation_configuration(valid_document())

    assert isinstance(result, ValuationConfiguration)
    assert isinstance(result.treasury_history, TreasuryHistoryConfig)
    assert isinstance(result.treasury_yield, TreasuryYieldConfig)
    assert isinstance(result.target_pe, TargetPEConfig)
    assert isinstance(result.decision, ValuationDecisionConfig)
    assert result.treasury_history.symbol == "^TNX"
    assert result.treasury_history.value_scale == "percent"
    assert result.treasury_history.short_window_observations == 20
    assert result.treasury_history.long_window_observations == 60
    assert result.treasury_yield.threshold_yield_percent == 4.3
    assert result.treasury_yield.maximum_discount_percent == 25.0
    assert result.target_pe.minimum_target_pe == 15.0
    assert result.target_pe.maximum_target_pe == 50.0
    assert result.decision.buy_discount_percent == 20.0
    assert result.decision.sell_premium_percent == 20.0


def test_preferred_sectors_are_stripped_and_converted_to_tuple() -> None:
    result = parse_valuation_configuration(valid_document())

    assert result.target_pe.preferred_sectors == (
        "Technology",
        "Semiconductors",
        "Semiconductor Equipment",
    )


def test_federal_reserve_section_is_optional_and_ignored() -> None:
    document = valid_document()
    del document["macro"]["federal_reserve"]

    result = parse_valuation_configuration(document)

    assert result.treasury_history.symbol == "^TNX"


def test_valuation_configuration_is_immutable() -> None:
    result = parse_valuation_configuration(valid_document())

    with pytest.raises(FrozenInstanceError):
        result.decision = ValuationDecisionConfig(10.0, 10.0)


@requires_yaml
def test_actual_repository_valuation_yaml_loads_successfully() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "valuation.yaml"

    result = load_valuation_configuration(config_path)

    assert result.treasury_history.symbol == "^TNX"
    assert result.treasury_yield.threshold_yield_percent == 4.3
    assert result.target_pe.minimum_target_pe == 15.0
    assert result.decision.buy_discount_percent == 20.0


@requires_yaml
def test_load_accepts_path_input(tmp_path: Path) -> None:
    config_path = tmp_path / "valuation.yaml"
    write_yaml(config_path, valid_document())

    result = load_valuation_configuration(config_path)

    assert result.target_pe.maximum_target_pe == 50.0


@requires_yaml
def test_load_accepts_string_path_input(tmp_path: Path) -> None:
    config_path = tmp_path / "valuation.yaml"
    write_yaml(config_path, valid_document())

    result = load_valuation_configuration(str(config_path))

    assert result.decision.sell_premium_percent == 20.0


def test_missing_file_is_wrapped_with_path(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.yaml"

    with pytest.raises(ValuationConfigurationError, match="missing.yaml") as error:
        load_valuation_configuration(config_path)

    assert isinstance(error.value.__cause__, OSError)


@requires_yaml
def test_invalid_yaml_is_wrapped_with_path(tmp_path: Path) -> None:
    config_path = tmp_path / "valuation.yaml"
    config_path.write_text("valuation: [", encoding="utf-8")

    with pytest.raises(ValuationConfigurationError, match="valuation.yaml") as error:
        load_valuation_configuration(config_path)

    assert error.value.__cause__ is not None


@requires_yaml
def test_empty_yaml_document_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "valuation.yaml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(ValuationConfigurationError, match="must not be empty"):
        load_valuation_configuration(config_path)


@requires_yaml
def test_non_mapping_root_from_file_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "valuation.yaml"
    write_yaml(config_path, ["not", "a", "mapping"])

    with pytest.raises(ValuationConfigurationError, match="document"):
        load_valuation_configuration(config_path)


def test_open_error_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_permission_error(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", raise_permission_error)

    with pytest.raises(ValuationConfigurationError, match="valuation.yaml") as error:
        load_valuation_configuration("valuation.yaml")

    assert isinstance(error.value.__cause__, PermissionError)


@pytest.mark.parametrize(
    ("section_path", "expected_path"),
    [
        (("macro",), r"macro"),
        (("valuation",), r"valuation"),
        (("macro", "treasury_yield"), r"macro\.treasury_yield"),
        (("valuation", "target_pe"), r"valuation\.target_pe"),
        (("valuation", "decision"), r"valuation\.decision"),
    ],
)
def test_missing_required_sections_raise(
    section_path: tuple[str, ...],
    expected_path: str,
) -> None:
    document = valid_document()
    parent = document
    for key in section_path[:-1]:
        parent = parent[key]
    del parent[section_path[-1]]

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("section_path", "replacement", "expected_path"),
    [
        (("macro",), [], r"macro"),
        (("valuation",), [], r"valuation"),
        (("macro", "treasury_yield"), 4.5, r"macro\.treasury_yield"),
        (("valuation", "target_pe"), "invalid", r"valuation\.target_pe"),
        (("valuation", "decision"), [], r"valuation\.decision"),
    ],
)
def test_sections_must_be_mappings(
    section_path: tuple[str, ...],
    replacement: object,
    expected_path: str,
) -> None:
    document = valid_document()
    parent = document
    for key in section_path[:-1]:
        parent = parent[key]
    parent[section_path[-1]] = replacement

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("section_path", "key", "expected_path"),
    [
        (("macro", "treasury_yield"), "threshold_yield_percent", r"threshold"),
        (("valuation", "target_pe"), "minimum_target_pe", r"minimum_target_pe"),
        (("valuation", "decision"), "buy_discount_percent", r"buy_discount"),
    ],
)
def test_missing_required_keys_raise(
    section_path: tuple[str, ...],
    key: str,
    expected_path: str,
) -> None:
    document = valid_document()
    section = document
    for path_key in section_path:
        section = section[path_key]
    del section[key]

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("section_path", "expected_path"),
    [
        (("macro",), r"macro\.unexpected"),
        (("macro", "treasury_yield"), r"macro\.treasury_yield\.unexpected"),
        (("valuation",), r"valuation\.unexpected"),
        (("valuation", "target_pe"), r"valuation\.target_pe\.unexpected"),
        (("valuation", "decision"), r"valuation\.decision\.unexpected"),
    ],
)
def test_unexpected_keys_raise(
    section_path: tuple[str, ...],
    expected_path: str,
) -> None:
    document = valid_document()
    section = document
    for key in section_path:
        section = section[key]
    section["unexpected"] = "nope"

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("section_path", "key", "bad_value", "expected_path"),
    [
        (
            ("macro", "treasury_yield"),
            "threshold_yield_percent",
            True,
            r"threshold_yield_percent",
        ),
        (
            ("valuation", "target_pe"),
            "minimum_target_pe",
            "15.0",
            r"minimum_target_pe",
        ),
        (
            ("valuation", "decision"),
            "sell_premium_percent",
            None,
            r"sell_premium_percent",
        ),
        (
            ("macro", "treasury_yield"),
            "short_window_observations",
            20.0,
            r"short_window_observations",
        ),
    ],
)
def test_scalar_type_validation_rejects_invalid_values(
    section_path: tuple[str, ...],
    key: str,
    bad_value: object,
    expected_path: str,
) -> None:
    document = valid_document()
    section = document
    for path_key in section_path:
        section = section[path_key]
    section[key] = bad_value

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("bad_value", "expected_path"),
    [
        ("Technology", r"preferred_sectors"),
        ({"name": "Technology"}, r"preferred_sectors"),
        ([1], r"preferred_sectors\[0\]"),
        (["  "], r"preferred_sectors\[0\]"),
    ],
)
def test_preferred_sector_type_validation(
    bad_value: object,
    expected_path: str,
) -> None:
    document = valid_document()
    document["valuation"]["target_pe"]["preferred_sectors"] = bad_value

    assert_config_error(document, expected_path)


@pytest.mark.parametrize(
    ("mutator", "expected_path"),
    [
        (
            lambda document: document["valuation"]["target_pe"].update(
                {"minimum_target_pe": 50.0, "maximum_target_pe": 15.0}
            ),
            r"valuation\.target_pe",
        ),
        (
            lambda document: document["valuation"]["target_pe"].update(
                {"low_peg_threshold": 2.0, "normal_peg_upper_threshold": 1.5}
            ),
            r"valuation\.target_pe",
        ),
        (
            lambda document: document["macro"]["treasury_yield"].update(
                {"threshold_yield_percent": 0.0}
            ),
            r"macro\.treasury_yield",
        ),
        (
            lambda document: document["macro"]["treasury_yield"].update(
                {"long_window_observations": 20}
            ),
            r"macro\.treasury_yield",
        ),
        (
            lambda document: document["valuation"]["decision"].update(
                {"buy_discount_percent": 100.0}
            ),
            r"valuation\.decision",
        ),
        (
            lambda document: document["valuation"]["decision"].update(
                {"sell_premium_percent": -1.0}
            ),
            r"valuation\.decision",
        ),
    ],
)
def test_domain_validation_failures_are_wrapped(
    mutator: object,
    expected_path: str,
) -> None:
    document = deepcopy(valid_document())
    mutator(document)

    with pytest.raises(ValuationConfigurationError, match=expected_path) as error:
        parse_valuation_configuration(document)

    assert isinstance(error.value.__cause__, ValueError)


@requires_yaml
def test_file_level_parse_error_chains_original_config_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "valuation.yaml"
    document = valid_document()
    del document["valuation"]["decision"]
    write_yaml(config_path, document)

    with pytest.raises(ValuationConfigurationError, match="valuation.yaml") as error:
        load_valuation_configuration(config_path)

    assert isinstance(error.value.__cause__, ValuationConfigurationError)
