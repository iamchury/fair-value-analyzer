from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.analysis.fair_value import (
    FairValueInputs,
    FairValueResult,
    calculate_adjusted_fair_value,
    calculate_base_fair_value,
    calculate_fair_value,
    validate_fair_value_inputs,
)


@pytest.mark.parametrize(
    ("forward_eps", "recommended_target_pe", "expected"),
    [
        (10, 30, 300),
        (0, 25, 0),
        (-2, 20, -40),
        (10.5, 20.0, 210.0),
    ],
)
def test_base_fair_value_formula(
    forward_eps: float,
    recommended_target_pe: float,
    expected: float,
) -> None:
    assert calculate_base_fair_value(forward_eps, recommended_target_pe) == expected


@pytest.mark.parametrize(
    ("base_fair_value", "multiplier", "expected"),
    [
        (300, 1.0, 300),
        (300, 0.819, 245.7),
        (300, 1.1, 330),
        (300, 0.0, 0),
        (-40, 0.9, -36),
    ],
)
def test_adjusted_fair_value_formula(
    base_fair_value: float,
    multiplier: float,
    expected: float,
) -> None:
    assert calculate_adjusted_fair_value(base_fair_value, multiplier) == pytest.approx(
        expected
    )


def test_default_macro_multiplier() -> None:
    inputs = FairValueInputs(forward_eps=10, recommended_target_pe=30)
    result = calculate_fair_value(inputs)
    assert result.macro_adjustment_multiplier == 1.0
    assert result.adjusted_fair_value == 300


@pytest.mark.parametrize(
    ("inputs", "expected_base", "expected_adjusted"),
    [
        (FairValueInputs(10, 30, 1.0), 300, 300),
        (FairValueInputs(10, 30, 0.819), 300, 245.7),
        (FairValueInputs(5, 15, 0.819), 75, 61.425),
        (FairValueInputs(-2, 20, 0.9), -40, -36),
        (FairValueInputs(0, 25, 1.1), 0, 0),
    ],
)
def test_deterministic_examples_a_through_e(
    inputs: FairValueInputs,
    expected_base: float,
    expected_adjusted: float,
) -> None:
    result = calculate_fair_value(inputs)
    assert result.base_fair_value == pytest.approx(expected_base)
    assert result.adjusted_fair_value == pytest.approx(expected_adjusted)


def test_returned_field_values_and_result_type() -> None:
    inputs = FairValueInputs(5, 15, 0.819)
    result = calculate_fair_value(inputs)

    assert isinstance(result, FairValueResult)
    assert result.forward_eps == 5
    assert result.recommended_target_pe == 15
    assert result.macro_adjustment_multiplier == 0.819
    assert result.base_fair_value == 75
    assert result.adjusted_fair_value == pytest.approx(61.425)


def test_no_internal_rounding() -> None:
    result = calculate_fair_value(FairValueInputs(1 / 3, 10, 0.819))
    assert result.base_fair_value == pytest.approx(10 / 3)
    assert result.adjusted_fair_value == pytest.approx((10 / 3) * 0.819)


@pytest.mark.parametrize(
    "inputs",
    [
        FairValueInputs(10, 30, 1),
        FairValueInputs(10.0, 30.0, 1.0),
        FairValueInputs(10, 30, 0.5),
        FairValueInputs(10, 30, 1.0),
        FairValueInputs(10, 30, 1.5),
        FairValueInputs(10, 30, 0.0),
        FairValueInputs(-2, 20, 0.9),
        FairValueInputs(0, 20, 0.9),
    ],
)
def test_valid_inputs(inputs: FairValueInputs) -> None:
    validate_fair_value_inputs(inputs)


@pytest.mark.parametrize(
    "inputs",
    [
        FairValueInputs(10, 0, 1),
        FairValueInputs(10, -1, 1),
        FairValueInputs(10, 30, -0.1),
    ],
)
def test_domain_validation_rejects_invalid_values(inputs: FairValueInputs) -> None:
    with pytest.raises(ValueError):
        validate_fair_value_inputs(inputs)


@pytest.mark.parametrize("bad_value", [nan, inf, -inf])
@pytest.mark.parametrize("field_name", ["forward_eps", "recommended_target_pe", "macro"])
def test_nan_and_infinity_rejected_in_every_input_field(
    bad_value: float,
    field_name: str,
) -> None:
    values = {
        "forward_eps": 10.0,
        "recommended_target_pe": 30.0,
        "macro": 1.0,
    }
    values[field_name] = bad_value

    with pytest.raises(ValueError):
        validate_fair_value_inputs(
            FairValueInputs(
                values["forward_eps"],
                values["recommended_target_pe"],
                values["macro"],
            )
        )


@pytest.mark.parametrize("bad_value", [True, False, "10", object()])
@pytest.mark.parametrize("field_name", ["forward_eps", "recommended_target_pe", "macro"])
def test_booleans_strings_and_objects_rejected_in_every_input_field(
    bad_value: object,
    field_name: str,
) -> None:
    values = {
        "forward_eps": 10.0,
        "recommended_target_pe": 30.0,
        "macro": 1.0,
    }
    values[field_name] = bad_value

    with pytest.raises(ValueError):
        validate_fair_value_inputs(
            FairValueInputs(
                values["forward_eps"],
                values["recommended_target_pe"],
                values["macro"],
            )
        )


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "10", object()])
def test_base_fair_value_rejects_invalid_forward_eps(bad_value: object) -> None:
    with pytest.raises(ValueError):
        calculate_base_fair_value(bad_value, 30)


@pytest.mark.parametrize("bad_value", [0, -1, nan, inf, -inf, True, "30", object()])
def test_base_fair_value_rejects_invalid_target_pe(bad_value: object) -> None:
    with pytest.raises(ValueError):
        calculate_base_fair_value(10, bad_value)


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "300", object()])
def test_adjusted_fair_value_rejects_invalid_base_value(bad_value: object) -> None:
    with pytest.raises(ValueError):
        calculate_adjusted_fair_value(bad_value, 1.0)


@pytest.mark.parametrize("bad_value", [-0.1, nan, inf, -inf, True, "1", object()])
def test_adjusted_fair_value_rejects_invalid_multiplier(bad_value: object) -> None:
    with pytest.raises(ValueError):
        calculate_adjusted_fair_value(300, bad_value)


def test_dataclasses_are_immutable() -> None:
    inputs = FairValueInputs(10, 30)
    result = calculate_fair_value(inputs)

    with pytest.raises(FrozenInstanceError):
        inputs.forward_eps = 11
    with pytest.raises(FrozenInstanceError):
        result.adjusted_fair_value = 301
