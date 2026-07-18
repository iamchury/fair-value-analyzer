from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.config.eps_selection import (
    EPSSelectionConfigurationError,
    EPSSelectionMethod,
    EPSSelectionRule,
    load_eps_selection_configuration,
    parse_eps_selection_configuration,
)


def rule(**overrides: object) -> dict[str, object]:
    values = {"method": "legacy_forward"}
    values.update(overrides)
    return values


def document(defaults=None, symbols=None, **extra):
    values = {"defaults": defaults or rule()}
    if symbols is not None:
        values["symbols"] = symbols
    values.update(extra)
    return values


def test_repository_eps_selection_yaml_loads_expected_rules() -> None:
    config = load_eps_selection_configuration("config/eps_selection.yaml")

    assert config.default_rule.method == EPSSelectionMethod.LEGACY_FORWARD
    assert config.default_rule.current_year_weight == 0.5
    assert config.default_rule.next_year_weight == 0.5
    assert config.symbol_rules["MU"].method == EPSSelectionMethod.CURRENT_YEAR
    assert config.symbol_rules["LITE"].method == EPSSelectionMethod.NEXT_YEAR
    assert config.symbol_rules["GLW"].method == EPSSelectionMethod.CURRENT_YEAR


def test_symbols_normalized_and_mapping_immutable() -> None:
    config = parse_eps_selection_configuration(
        document(symbols={" lite ": rule(method="next_year")})
    )

    assert config.symbol_rules["LITE"].method == EPSSelectionMethod.NEXT_YEAR
    with pytest.raises(TypeError):
        config.symbol_rules["MU"] = config.default_rule
    with pytest.raises(FrozenInstanceError):
        config.default_rule.method = EPSSelectionMethod.MANUAL


@pytest.mark.parametrize(
    "method",
    [
        "legacy_forward",
        "current_year",
        "next_year",
        "weighted_current_next",
        "manual",
    ],
)
def test_all_methods_load(method: str) -> None:
    values = {"method": method}
    if method == "weighted_current_next":
        values.update(current_year_weight=0.5, next_year_weight=0.5)
    if method == "manual":
        values.update(manual_eps=1.0, manual_period_label="FY2026")

    config = parse_eps_selection_configuration(document(defaults=values))

    assert isinstance(config.default_rule, EPSSelectionRule)


@pytest.mark.parametrize(
    "bad_document",
    [
        document(extra=True),
        {"symbols": {}},
        document(defaults=rule(extra=True)),
        document(defaults=rule(method="bad")),
        document(symbols={"MU": rule(method="current_year", manual_eps=1.0)}),
        document(symbols={"MU": rule(method="current_year", current_year_weight=1.0)}),
        document(symbols={"MU": rule(method="manual", manual_eps=1.0)}),
        document(symbols={"MU": rule(method="manual", manual_eps=1.0, manual_period_label=" ")}),
    ],
)
def test_invalid_documents_raise_configuration_error(bad_document: object) -> None:
    with pytest.raises(EPSSelectionConfigurationError):
        parse_eps_selection_configuration(bad_document)


@pytest.mark.parametrize("manual_eps", [True, nan, inf])
def test_manual_eps_rejects_invalid_values(manual_eps: object) -> None:
    with pytest.raises(EPSSelectionConfigurationError):
        parse_eps_selection_configuration(
            document(defaults=rule(method="manual", manual_eps=manual_eps, manual_period_label="FY2026"))
        )


@pytest.mark.parametrize("manual_eps", [-1.0, 0.0, 1.0])
def test_manual_eps_accepts_negative_zero_and_positive(manual_eps: float) -> None:
    config = parse_eps_selection_configuration(
        document(defaults=rule(method="manual", manual_eps=manual_eps, manual_period_label=" FY2026 "))
    )

    assert config.default_rule.manual_eps == manual_eps
    assert config.default_rule.manual_period_label == "FY2026"


@pytest.mark.parametrize(
    "weights",
    [
        {},
        {"current_year_weight": 0.5},
        {"current_year_weight": -0.1, "next_year_weight": 1.1},
        {"current_year_weight": 1.1, "next_year_weight": -0.1},
        {"current_year_weight": True, "next_year_weight": 0.0},
        {"current_year_weight": 0.3, "next_year_weight": 0.3},
    ],
)
def test_weighted_method_rejects_invalid_weights(weights: dict[str, object]) -> None:
    with pytest.raises(EPSSelectionConfigurationError):
        parse_eps_selection_configuration(
            document(defaults=rule(method="weighted_current_next", **weights))
        )


@pytest.mark.parametrize(
    ("current_weight", "next_weight"),
    [(0.0, 1.0), (1.0, 0.0), (0.5, 0.5)],
)
def test_weighted_method_accepts_valid_weight_combinations(
    current_weight: float,
    next_weight: float,
) -> None:
    config = parse_eps_selection_configuration(
        document(
            defaults=rule(
                method="weighted_current_next",
                current_year_weight=current_weight,
                next_year_weight=next_weight,
            )
        )
    )

    assert config.default_rule.current_year_weight == current_weight
    assert config.default_rule.next_year_weight == next_weight


def test_duplicate_normalized_symbols_rejected() -> None:
    with pytest.raises(EPSSelectionConfigurationError, match="MU is duplicated"):
        parse_eps_selection_configuration(
            document(symbols={"MU": rule(), " mu ": rule(method="next_year")})
        )


def test_rationale_is_trimmed_and_empty_becomes_none() -> None:
    config = parse_eps_selection_configuration(
        document(symbols={"MU": rule(method="current_year", rationale="  use current  "), "LITE": rule(method="next_year", rationale=" ")})
    )

    assert config.symbol_rules["MU"].rationale == "use current"
    assert config.symbol_rules["LITE"].rationale is None
