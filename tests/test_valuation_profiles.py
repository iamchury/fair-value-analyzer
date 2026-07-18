from dataclasses import FrozenInstanceError
from math import inf, nan
from pathlib import Path

import pytest

from src.config.valuation_profiles import (
    ValuationProfileConfigurationError,
    ValuationStyle,
    load_valuation_profiles,
    parse_valuation_profiles,
)


def profile_document(**profiles: object) -> dict[str, object]:
    return {"profiles": profiles}


def profile_values(**overrides: object) -> dict[str, object]:
    values = {
        "valuation_style": "growth",
        "valuation_eps": 18.30,
        "eps_fiscal_year": "FY2027",
        "target_pe": 40.0,
        "use_peg_adjustment": True,
        "dcf_fair_value": None,
        "source_note": "research note",
    }
    values.update(overrides)
    return values


def test_load_repository_profiles_contains_expected_symbols_and_values() -> None:
    profiles = load_valuation_profiles("config/valuation_profiles.yaml")

    assert tuple(profiles) == ("MU", "LITE", "GLW")
    assert profiles["MU"].valuation_style == ValuationStyle.CYCLICAL
    assert profiles["MU"].valuation_eps == 73.39
    assert profiles["MU"].eps_fiscal_year == "FY2026"
    assert profiles["MU"].target_pe == 10.0
    assert profiles["MU"].use_peg_adjustment is False
    assert profiles["MU"].dcf_fair_value == 618.10

    assert profiles["LITE"].valuation_style == ValuationStyle.GROWTH
    assert profiles["LITE"].valuation_eps == 18.30
    assert profiles["LITE"].target_pe == 40.0
    assert profiles["LITE"].use_peg_adjustment is True

    assert profiles["GLW"].valuation_style == ValuationStyle.QUALITY_GROWTH
    assert profiles["GLW"].valuation_eps == 3.20
    assert profiles["GLW"].target_pe == 40.0


def test_parse_profiles_normalizes_symbols_and_style_values() -> None:
    profiles = parse_valuation_profiles(
        profile_document(
            **{
                " lite ": profile_values(valuation_style="growth"),
                "mu": profile_values(valuation_style="cyclical"),
                "glw": profile_values(valuation_style="quality_growth"),
            }
        )
    )

    assert tuple(profiles) == ("LITE", "MU", "GLW")
    assert profiles["LITE"].valuation_style == ValuationStyle.GROWTH
    assert profiles["MU"].valuation_style == ValuationStyle.CYCLICAL
    assert profiles["GLW"].valuation_style == ValuationStyle.QUALITY_GROWTH


def test_profiles_mapping_and_objects_are_immutable() -> None:
    profiles = parse_valuation_profiles(profile_document(LITE=profile_values()))

    with pytest.raises(TypeError):
        profiles["MU"] = profiles["LITE"]
    with pytest.raises(FrozenInstanceError):
        profiles["LITE"].target_pe = 50.0


@pytest.mark.parametrize("valuation_eps", [18, 18.3, 0, -2.5])
def test_valuation_eps_accepts_any_finite_number(valuation_eps: float) -> None:
    profiles = parse_valuation_profiles(
        profile_document(LITE=profile_values(valuation_eps=valuation_eps))
    )

    assert profiles["LITE"].valuation_eps == float(valuation_eps)


@pytest.mark.parametrize("target_pe", [0, -1, 201, True, "40", nan, inf])
def test_target_pe_rejects_invalid_values(target_pe: object) -> None:
    with pytest.raises(ValuationProfileConfigurationError):
        parse_valuation_profiles(profile_document(LITE=profile_values(target_pe=target_pe)))


@pytest.mark.parametrize("dcf_fair_value", [618.1, None])
def test_dcf_fair_value_accepts_positive_number_or_null(
    dcf_fair_value: float | None,
) -> None:
    profiles = parse_valuation_profiles(
        profile_document(LITE=profile_values(dcf_fair_value=dcf_fair_value))
    )

    assert profiles["LITE"].dcf_fair_value == dcf_fair_value


@pytest.mark.parametrize("dcf_fair_value", [0, -1, True, "618", nan, inf])
def test_dcf_fair_value_rejects_invalid_values(dcf_fair_value: object) -> None:
    with pytest.raises(ValuationProfileConfigurationError):
        parse_valuation_profiles(
            profile_document(LITE=profile_values(dcf_fair_value=dcf_fair_value))
        )


@pytest.mark.parametrize("use_peg_adjustment", [1, "true", None])
def test_use_peg_adjustment_must_be_boolean(use_peg_adjustment: object) -> None:
    with pytest.raises(ValuationProfileConfigurationError):
        parse_valuation_profiles(
            profile_document(
                LITE=profile_values(use_peg_adjustment=use_peg_adjustment)
            )
        )


def test_duplicate_normalized_symbols_are_rejected() -> None:
    with pytest.raises(ValuationProfileConfigurationError, match="LITE is duplicated"):
        parse_valuation_profiles(
            profile_document(
                **{
                    "LITE": profile_values(),
                    " lite ": profile_values(target_pe=45.0),
                }
            )
        )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"profiles": {}},
        {"profiles": {"LITE": {}}},
        {"profiles": {"LITE": profile_values(extra=True)}},
        {"profiles": {"LITE": profile_values(valuation_style="unknown")}},
        {"profiles": {"LI TE": profile_values()}},
    ],
)
def test_invalid_documents_raise_configuration_error(document: object) -> None:
    with pytest.raises(ValuationProfileConfigurationError):
        parse_valuation_profiles(document)


def test_load_profiles_wraps_file_and_yaml_errors(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"
    bad_yaml_path = tmp_path / "bad.yaml"
    bad_yaml_path.write_text("profiles: [", encoding="utf-8")

    with pytest.raises(ValuationProfileConfigurationError, match="failed to read"):
        load_valuation_profiles(missing_path)
    with pytest.raises(ValuationProfileConfigurationError, match="invalid YAML"):
        load_valuation_profiles(bad_yaml_path)
