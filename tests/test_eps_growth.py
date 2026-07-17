from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.analysis.eps_growth import (
    EPSGrowthInputs,
    EPSGrowthResult,
    EPSTransition,
    calculate_eps_growth,
    calculate_eps_growth_percent,
    classify_eps_transition,
    is_growth_rate_usable_for_target_pe,
    validate_eps_growth_inputs,
)


@pytest.mark.parametrize(
    "inputs",
    [
        EPSGrowthInputs(5, 6),
        EPSGrowthInputs(0, 1),
        EPSGrowthInputs(-2, -1),
        EPSGrowthInputs(None, 1),
        EPSGrowthInputs(1, None),
        EPSGrowthInputs(None, None),
    ],
)
def test_valid_inputs(inputs: EPSGrowthInputs) -> None:
    validate_eps_growth_inputs(inputs)


@pytest.mark.parametrize("bad_value", [nan, inf, -inf])
@pytest.mark.parametrize("field_name", ["trailing_eps", "forward_eps"])
def test_nan_and_infinity_rejected(
    bad_value: float,
    field_name: str,
) -> None:
    values = {"trailing_eps": 5.0, "forward_eps": 6.0}
    values[field_name] = bad_value

    with pytest.raises(ValueError):
        validate_eps_growth_inputs(
            EPSGrowthInputs(values["trailing_eps"], values["forward_eps"])
        )


@pytest.mark.parametrize("bad_value", [True, False, "5", object(), {}, []])
@pytest.mark.parametrize("field_name", ["trailing_eps", "forward_eps"])
def test_booleans_strings_objects_and_containers_rejected(
    bad_value: object,
    field_name: str,
) -> None:
    values = {"trailing_eps": 5.0, "forward_eps": 6.0}
    values[field_name] = bad_value

    with pytest.raises(ValueError):
        validate_eps_growth_inputs(
            EPSGrowthInputs(values["trailing_eps"], values["forward_eps"])
        )


def test_non_input_object_rejected() -> None:
    with pytest.raises(ValueError):
        validate_eps_growth_inputs({"trailing_eps": 5.0, "forward_eps": 6.0})


@pytest.mark.parametrize(
    ("trailing_eps", "forward_eps", "expected"),
    [
        (5, 6, EPSTransition.POSITIVE_GROWTH),
        (5, 4, EPSTransition.NEGATIVE_GROWTH),
        (5, 5, EPSTransition.FLAT),
        (5, 0, EPSTransition.NEGATIVE_GROWTH),
        (-2, 0, EPSTransition.LOSS_TO_PROFIT),
        (-2, 1, EPSTransition.LOSS_TO_PROFIT),
        (1, -2, EPSTransition.PROFIT_TO_LOSS),
        (-2, -1, EPSTransition.LOSS_NARROWING),
        (-1, -2, EPSTransition.LOSS_WIDENING),
        (-2, -2, EPSTransition.FLAT),
        (0, 1, EPSTransition.ZERO_BASE),
        (None, 5, EPSTransition.UNAVAILABLE),
        (5, None, EPSTransition.UNAVAILABLE),
        (None, None, EPSTransition.UNAVAILABLE),
    ],
)
def test_classification_rules(
    trailing_eps: float | None,
    forward_eps: float | None,
    expected: EPSTransition,
) -> None:
    assert classify_eps_transition(trailing_eps, forward_eps) == expected


@pytest.mark.parametrize(
    ("trailing_eps", "forward_eps", "expected"),
    [
        (5, 6, 20),
        (5, 4, -20),
        (5, 5, 0),
        (-2, -1, 50),
        (-1, -2, -100),
        (-2, 1, 150),
    ],
)
def test_growth_formula(
    trailing_eps: float,
    forward_eps: float,
    expected: float,
) -> None:
    assert calculate_eps_growth_percent(trailing_eps, forward_eps) == expected


def test_growth_formula_rejects_zero_trailing_eps() -> None:
    with pytest.raises(ValueError):
        calculate_eps_growth_percent(0, 1)


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "5", object(), []])
@pytest.mark.parametrize("field_name", ["trailing_eps", "forward_eps"])
def test_growth_formula_rejects_invalid_numbers(
    bad_value: object,
    field_name: str,
) -> None:
    values = {"trailing_eps": 5.0, "forward_eps": 6.0}
    values[field_name] = bad_value

    with pytest.raises(ValueError):
        calculate_eps_growth_percent(values["trailing_eps"], values["forward_eps"])


def test_growth_formula_does_not_round() -> None:
    assert calculate_eps_growth_percent(3, 4) == pytest.approx(100 / 3)


@pytest.mark.parametrize(
    ("trailing_eps", "forward_eps", "transition", "expected"),
    [
        (5, 6, EPSTransition.POSITIVE_GROWTH, True),
        (5, 0, EPSTransition.NEGATIVE_GROWTH, True),
        (5, 5, EPSTransition.FLAT, True),
        (-2, 1, EPSTransition.LOSS_TO_PROFIT, False),
        (1, -2, EPSTransition.PROFIT_TO_LOSS, False),
        (-2, -1, EPSTransition.LOSS_NARROWING, False),
        (-1, -2, EPSTransition.LOSS_WIDENING, False),
        (-2, -2, EPSTransition.FLAT, False),
        (0, 1, EPSTransition.ZERO_BASE, False),
        (None, 1, EPSTransition.UNAVAILABLE, False),
    ],
)
def test_target_pe_usability_policy(
    trailing_eps: float | None,
    forward_eps: float | None,
    transition: EPSTransition,
    expected: bool,
) -> None:
    assert (
        is_growth_rate_usable_for_target_pe(
            trailing_eps,
            forward_eps,
            transition,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("inputs", "transition", "growth_percent", "usable", "explanation"),
    [
        (
            EPSGrowthInputs(5, 6),
            EPSTransition.POSITIVE_GROWTH,
            20,
            True,
            "Forward EPS increases from 5.0 to 6.0, representing growth of 20.0%.",
        ),
        (
            EPSGrowthInputs(5, 4),
            EPSTransition.NEGATIVE_GROWTH,
            -20,
            True,
            "Forward EPS decreases from 5.0 to 4.0, representing growth of -20.0%.",
        ),
        (
            EPSGrowthInputs(5, 5),
            EPSTransition.FLAT,
            0,
            True,
            "Forward EPS is unchanged from trailing EPS at 5.0.",
        ),
        (
            EPSGrowthInputs(-2, 1),
            EPSTransition.LOSS_TO_PROFIT,
            150,
            False,
            (
                "EPS changes from a loss of -2.0 to 1.0; the mathematical change "
                "is 150.0%, but it is not a conventional growth rate for Target PE."
            ),
        ),
        (
            EPSGrowthInputs(1, -2),
            EPSTransition.PROFIT_TO_LOSS,
            -300,
            False,
            (
                "EPS changes from a profit of 1.0 to a loss of -2.0; the "
                "mathematical change is -300.0%, but it is not usable as a "
                "conventional Target PE growth rate."
            ),
        ),
        (
            EPSGrowthInputs(-2, -1),
            EPSTransition.LOSS_NARROWING,
            50,
            False,
            (
                "The projected loss narrows from -2.0 to -1.0; the mathematical "
                "change is 50.0%, but it is not usable as a conventional Target PE "
                "growth rate."
            ),
        ),
        (
            EPSGrowthInputs(-1, -2),
            EPSTransition.LOSS_WIDENING,
            -100,
            False,
            (
                "The projected loss widens from -1.0 to -2.0; the mathematical "
                "change is -100.0%, but it is not usable as a conventional Target PE "
                "growth rate."
            ),
        ),
        (
            EPSGrowthInputs(-2, -2),
            EPSTransition.FLAT,
            0,
            False,
            "Forward EPS is unchanged from trailing EPS at -2.0.",
        ),
        (
            EPSGrowthInputs(0, 1),
            EPSTransition.ZERO_BASE,
            None,
            False,
            "Trailing EPS is zero, so percentage EPS growth cannot be calculated.",
        ),
        (
            EPSGrowthInputs(None, 5),
            EPSTransition.UNAVAILABLE,
            None,
            False,
            (
                "Trailing EPS and Forward EPS are both required to calculate EPS "
                "growth."
            ),
        ),
    ],
)
def test_final_result_deterministic_examples_a_through_j(
    inputs: EPSGrowthInputs,
    transition: EPSTransition,
    growth_percent: float | None,
    usable: bool,
    explanation: str,
) -> None:
    result = calculate_eps_growth(inputs)

    assert isinstance(result, EPSGrowthResult)
    assert result.trailing_eps == inputs.trailing_eps
    assert result.forward_eps == inputs.forward_eps
    assert result.growth_percent == growth_percent
    assert result.transition == transition
    assert result.is_growth_rate_usable_for_target_pe is usable
    assert result.explanation == explanation


def test_dataclasses_are_immutable() -> None:
    inputs = EPSGrowthInputs(5, 6)
    result = calculate_eps_growth(inputs)

    with pytest.raises(FrozenInstanceError):
        inputs.trailing_eps = 6
    with pytest.raises(FrozenInstanceError):
        result.growth_percent = 25
