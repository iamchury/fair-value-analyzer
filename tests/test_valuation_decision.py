from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    ValuationDecisionInputs,
    ValuationDecisionResult,
    ValuationRecommendation,
    calculate_buy_price,
    calculate_discount_to_fair_value_percent,
    calculate_sell_price,
    calculate_upside_to_fair_value_percent,
    calculate_valuation_decision,
    classify_valuation_recommendation,
    validate_valuation_decision_config,
    validate_valuation_decision_inputs,
)


@pytest.fixture
def config() -> ValuationDecisionConfig:
    return ValuationDecisionConfig(
        buy_discount_percent=20.0,
        sell_premium_percent=20.0,
    )


def test_valid_default_config(config: ValuationDecisionConfig) -> None:
    validate_valuation_decision_config(config)


def test_zero_buy_discount_accepted() -> None:
    validate_valuation_decision_config(ValuationDecisionConfig(0.0, 20.0))


@pytest.mark.parametrize("buy_discount", [100.0, 100.1, -0.1])
def test_invalid_buy_discount_rejected(buy_discount: float) -> None:
    with pytest.raises(ValueError):
        validate_valuation_decision_config(
            ValuationDecisionConfig(buy_discount, 20.0)
        )


def test_zero_sell_premium_accepted() -> None:
    validate_valuation_decision_config(ValuationDecisionConfig(20.0, 0.0))


def test_negative_sell_premium_rejected() -> None:
    with pytest.raises(ValueError):
        validate_valuation_decision_config(ValuationDecisionConfig(20.0, -0.1))


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "20", object()])
@pytest.mark.parametrize("field_name", ["buy_discount", "sell_premium"])
def test_invalid_config_numeric_values_rejected(
    bad_value: object,
    field_name: str,
) -> None:
    values = {"buy_discount": 20.0, "sell_premium": 20.0}
    values[field_name] = bad_value
    with pytest.raises(ValueError):
        validate_valuation_decision_config(
            ValuationDecisionConfig(
                values["buy_discount"],
                values["sell_premium"],
            )
        )


def test_positive_current_price_and_any_fair_value_accepted() -> None:
    validate_valuation_decision_inputs(ValuationDecisionInputs(1.0, 100.0))
    validate_valuation_decision_inputs(ValuationDecisionInputs(1.0, 0.0))
    validate_valuation_decision_inputs(ValuationDecisionInputs(1.0, -100.0))


@pytest.mark.parametrize("current_price", [0.0, -0.1])
def test_non_positive_current_price_rejected(current_price: float) -> None:
    with pytest.raises(ValueError):
        validate_valuation_decision_inputs(
            ValuationDecisionInputs(current_price, 100.0)
        )


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "100", object()])
@pytest.mark.parametrize("field_name", ["current_price", "adjusted_fair_value"])
def test_invalid_input_numeric_values_rejected(
    bad_value: object,
    field_name: str,
) -> None:
    values = {"current_price": 100.0, "adjusted_fair_value": 100.0}
    values[field_name] = bad_value
    with pytest.raises(ValueError):
        validate_valuation_decision_inputs(
            ValuationDecisionInputs(
                values["current_price"],
                values["adjusted_fair_value"],
            )
        )


@pytest.mark.parametrize(
    ("fair_value", "discount", "expected"),
    [
        (100.0, 20.0, 80.0),
        (100.0, 0.0, 100.0),
        (123.45, 12.3, 108.26565),
        (1 / 3, 12.5, (1 / 3) * 0.875),
    ],
)
def test_buy_price_calculation(
    fair_value: float,
    discount: float,
    expected: float,
) -> None:
    assert calculate_buy_price(fair_value, discount) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("fair_value", "premium", "expected"),
    [
        (100.0, 20.0, 120.0),
        (100.0, 0.0, 100.0),
        (123.45, 12.3, 138.63435),
        (1 / 3, 12.5, (1 / 3) * 1.125),
    ],
)
def test_sell_price_calculation(
    fair_value: float,
    premium: float,
    expected: float,
) -> None:
    assert calculate_sell_price(fair_value, premium) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("current_price", "fair_value", "expected"),
    [(80.0, 100.0, 20.0), (100.0, 100.0, 0.0), (120.0, 100.0, -20.0)],
)
def test_discount_calculation(
    current_price: float,
    fair_value: float,
    expected: float,
) -> None:
    assert calculate_discount_to_fair_value_percent(
        current_price,
        fair_value,
    ) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("current_price", "fair_value", "expected"),
    [
        (80.0, 100.0, 25.0),
        (100.0, 100.0, 0.0),
        (120.0, 100.0, (100.0 - 120.0) / 120.0 * 100),
    ],
)
def test_upside_calculation(
    current_price: float,
    fair_value: float,
    expected: float,
) -> None:
    assert calculate_upside_to_fair_value_percent(
        current_price,
        fair_value,
    ) == pytest.approx(expected)


def test_upside_formula_differs_from_discount_formula() -> None:
    discount = calculate_discount_to_fair_value_percent(80.0, 100.0)
    upside = calculate_upside_to_fair_value_percent(80.0, 100.0)
    assert discount == 20.0
    assert upside == 25.0


@pytest.mark.parametrize(
    ("current_price", "expected"),
    [
        (70.0, ValuationRecommendation.BUY),
        (80.0, ValuationRecommendation.BUY),
        (100.0, ValuationRecommendation.HOLD),
        (120.0, ValuationRecommendation.SELL),
        (130.0, ValuationRecommendation.SELL),
    ],
)
def test_recommendation_classification_boundaries(
    current_price: float,
    expected: ValuationRecommendation,
) -> None:
    assert classify_valuation_recommendation(current_price, 80.0, 120.0) == expected


@pytest.mark.parametrize(
    ("current_price", "fair_value", "expected_recommendation", "expected_discount", "expected_upside"),
    [
        (80.0, 100.0, ValuationRecommendation.BUY, 20.0, 25.0),
        (100.0, 100.0, ValuationRecommendation.HOLD, 0.0, 0.0),
        (
            120.0,
            100.0,
            ValuationRecommendation.SELL,
            -20.0,
            (100.0 - 120.0) / 120.0 * 100,
        ),
        (
            70.0,
            100.0,
            ValuationRecommendation.BUY,
            30.0,
            (100.0 - 70.0) / 70.0 * 100,
        ),
        (130.0, 100.0, ValuationRecommendation.SELL, -30.0, (100.0 - 130.0) / 130.0 * 100),
    ],
)
def test_positive_fair_value_deterministic_examples(
    config: ValuationDecisionConfig,
    current_price: float,
    fair_value: float,
    expected_recommendation: ValuationRecommendation,
    expected_discount: float,
    expected_upside: float,
) -> None:
    result = calculate_valuation_decision(
        ValuationDecisionInputs(current_price, fair_value),
        config,
    )
    assert result.buy_price == 80.0
    assert result.sell_price == 120.0
    assert result.discount_to_fair_value_percent == pytest.approx(
        expected_discount
    )
    assert result.upside_to_fair_value_percent == pytest.approx(expected_upside)
    assert result.recommendation == expected_recommendation


@pytest.mark.parametrize("fair_value", [-20.0, 0.0])
def test_non_positive_fair_value_is_not_applicable(
    config: ValuationDecisionConfig,
    fair_value: float,
) -> None:
    result = calculate_valuation_decision(
        ValuationDecisionInputs(50.0, fair_value),
        config,
    )
    assert result.buy_price is None
    assert result.sell_price is None
    assert result.discount_to_fair_value_percent is None
    assert result.upside_to_fair_value_percent is None
    assert result.recommendation == ValuationRecommendation.NOT_APPLICABLE
    assert "must be positive" in result.explanation


def test_returned_field_values_and_result_type(
    config: ValuationDecisionConfig,
) -> None:
    result = calculate_valuation_decision(
        ValuationDecisionInputs(80.0, 100.0),
        config,
    )
    assert isinstance(result, ValuationDecisionResult)
    assert result.current_price == 80.0
    assert result.adjusted_fair_value == 100.0
    assert result.buy_discount_percent == 20.0
    assert result.sell_premium_percent == 20.0


def test_explanation_content(config: ValuationDecisionConfig) -> None:
    buy = calculate_valuation_decision(ValuationDecisionInputs(80.0, 100.0), config)
    hold = calculate_valuation_decision(ValuationDecisionInputs(100.0, 100.0), config)
    sell = calculate_valuation_decision(ValuationDecisionInputs(120.0, 100.0), config)

    assert buy.explanation == (
        "Current price 80.0 is at or below the configured buy price 80.0."
    )
    assert hold.explanation == (
        "Current price 100.0 is between the buy price 80.0 and sell price 120.0."
    )
    assert sell.explanation == (
        "Current price 120.0 is at or above the configured sell price 120.0."
    )


def test_custom_configuration() -> None:
    result = calculate_valuation_decision(
        ValuationDecisionInputs(90.0, 100.0),
        ValuationDecisionConfig(10.0, 30.0),
    )
    assert result.buy_price == 90.0
    assert result.sell_price == 130.0
    assert result.recommendation == ValuationRecommendation.BUY


def test_no_internal_rounding(config: ValuationDecisionConfig) -> None:
    result = calculate_valuation_decision(
        ValuationDecisionInputs(1 / 3, 1.0),
        config,
    )
    assert result.discount_to_fair_value_percent == pytest.approx(
        (1 - 1 / 3) / 1 * 100
    )
    assert result.upside_to_fair_value_percent == pytest.approx(
        (1 - 1 / 3) / (1 / 3) * 100
    )


def test_dataclasses_are_immutable(config: ValuationDecisionConfig) -> None:
    inputs = ValuationDecisionInputs(80.0, 100.0)
    result = calculate_valuation_decision(inputs, config)
    with pytest.raises(FrozenInstanceError):
        inputs.current_price = 81.0
    with pytest.raises(FrozenInstanceError):
        result.recommendation = ValuationRecommendation.HOLD
