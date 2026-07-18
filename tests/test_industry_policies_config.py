from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.config.industry_policies import (
    IndustryPolicyConfigurationError,
    TargetPEMode,
    ValuationStyle,
    load_industry_policy_configuration,
    parse_industry_policy_configuration,
)


def valid_document(**overrides: object) -> dict[str, object]:
    document = {
        "policies": {
            "cyclical": {
                "valuation_style": "cyclical",
                "target_pe_mode": "fixed",
                "fixed_target_pe": 10.0,
                "minimum_target_pe": 7.0,
                "maximum_target_pe": 12.0,
                "use_eps_growth": False,
                "use_peg_adjustment": False,
                "use_sector_adjustment": False,
                "use_forward_pe_penalty": False,
                "rationale": " conservative ",
            },
            "growth": {
                "valuation_style": "growth",
                "target_pe_mode": "calculated",
                "fixed_target_pe": None,
                "minimum_target_pe": 25.0,
                "maximum_target_pe": 45.0,
                "use_eps_growth": True,
                "use_peg_adjustment": True,
                "use_sector_adjustment": True,
                "use_forward_pe_penalty": True,
                "rationale": "growth",
            },
            "quality_growth": {
                "valuation_style": "quality_growth",
                "target_pe_mode": "calculated",
                "fixed_target_pe": None,
                "minimum_target_pe": 20.0,
                "maximum_target_pe": 40.0,
                "use_eps_growth": True,
                "use_peg_adjustment": True,
                "use_sector_adjustment": False,
                "use_forward_pe_penalty": True,
                "rationale": "quality",
            },
        },
        "symbols": {
            "mu": {"policy": "cyclical"},
            "LITE": {"policy": "growth"},
            "GLW": {"policy": "quality_growth"},
        },
    }
    document.update(overrides)
    return document


def test_repository_yaml_loads_expected_policies() -> None:
    configuration = load_industry_policy_configuration()

    assert set(configuration.policies) == {"CYCLICAL", "GROWTH", "QUALITY_GROWTH"}
    assert configuration.symbol_policy_names == {
        "MU": "CYCLICAL",
        "LITE": "GROWTH",
        "GLW": "QUALITY_GROWTH",
    }
    assert configuration.policies["CYCLICAL"].target_pe_mode == TargetPEMode.FIXED
    assert configuration.policies["GROWTH"].valuation_style == ValuationStyle.GROWTH


def test_valid_document_normalizes_and_is_immutable() -> None:
    configuration = parse_industry_policy_configuration(valid_document())

    assert configuration.policies["CYCLICAL"].rationale == "conservative"
    assert configuration.symbol_policy_names["MU"] == "CYCLICAL"
    with pytest.raises(TypeError):
        configuration.policies["NEW"] = configuration.policies["CYCLICAL"]
    with pytest.raises(FrozenInstanceError):
        configuration.policies["CYCLICAL"].fixed_target_pe = 11.0


@pytest.mark.parametrize(
    "document",
    [
        {"bad": {}},
        valid_document(extra={}),
        valid_document(policies={}),
        valid_document(symbols={"mu": {"policy": "cyclical"}, "MU": {"policy": "cyclical"}}),
        valid_document(symbols={"X": {"policy": "missing"}}),
    ],
)
def test_invalid_top_level_and_references_raise(document: object) -> None:
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("valuation_style", "mature"),
        ("target_pe_mode", "blended"),
        ("minimum_target_pe", 0.0),
        ("maximum_target_pe", 0.0),
        ("maximum_target_pe", 201.0),
        ("minimum_target_pe", True),
        ("minimum_target_pe", nan),
        ("minimum_target_pe", inf),
        ("use_eps_growth", 1),
        ("use_peg_adjustment", "true"),
    ],
)
def test_invalid_policy_fields_raise(key: str, value: object) -> None:
    document = valid_document()
    document["policies"]["growth"][key] = value
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)


def test_minimum_greater_than_maximum_rejected() -> None:
    document = valid_document()
    document["policies"]["growth"]["minimum_target_pe"] = 50.0
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)


def test_unknown_policy_key_rejected() -> None:
    document = valid_document()
    document["policies"]["growth"]["unknown"] = True
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)


@pytest.mark.parametrize(
    "updates",
    [
        {"fixed_target_pe": None},
        {"fixed_target_pe": 20.0},
        {"use_eps_growth": True},
        {"use_peg_adjustment": True},
        {"use_sector_adjustment": True},
        {"use_forward_pe_penalty": True},
    ],
)
def test_fixed_mode_contradictions_rejected(updates: dict[str, object]) -> None:
    document = valid_document()
    document["policies"]["cyclical"].update(updates)
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)


def test_calculated_mode_rejects_fixed_pe() -> None:
    document = valid_document()
    document["policies"]["growth"]["fixed_target_pe"] = 35.0
    with pytest.raises(IndustryPolicyConfigurationError):
        parse_industry_policy_configuration(document)
