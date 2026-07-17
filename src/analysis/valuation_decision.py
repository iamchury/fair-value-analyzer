from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ValuationRecommendation(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ValuationDecisionConfig:
    buy_discount_percent: float
    sell_premium_percent: float


@dataclass(frozen=True)
class ValuationDecisionInputs:
    current_price: float
    adjusted_fair_value: float


@dataclass(frozen=True)
class ValuationDecisionResult:
    current_price: float
    adjusted_fair_value: float
    buy_discount_percent: float
    sell_premium_percent: float
    buy_price: float | None
    sell_price: float | None
    discount_to_fair_value_percent: float | None
    upside_to_fair_value_percent: float | None
    recommendation: ValuationRecommendation
    explanation: str


def validate_valuation_decision_config(
    config: ValuationDecisionConfig,
) -> None:
    """Validate valuation-decision configuration."""
    _require_number("buy_discount_percent", config.buy_discount_percent)
    _require_number("sell_premium_percent", config.sell_premium_percent)

    if not 0 <= config.buy_discount_percent < 100:
        raise ValueError("buy_discount_percent must be >= 0 and < 100.")
    if config.sell_premium_percent < 0:
        raise ValueError("sell_premium_percent must be non-negative.")


def validate_valuation_decision_inputs(
    inputs: ValuationDecisionInputs,
) -> None:
    """Validate valuation-decision inputs."""
    _require_number("current_price", inputs.current_price)
    _require_number("adjusted_fair_value", inputs.adjusted_fair_value)

    if inputs.current_price <= 0:
        raise ValueError("current_price must be greater than 0.")


def calculate_buy_price(
    adjusted_fair_value: float,
    buy_discount_percent: float,
) -> float:
    """Calculate buy price from adjusted fair value and discount percent."""
    _require_number("adjusted_fair_value", adjusted_fair_value)
    _require_number("buy_discount_percent", buy_discount_percent)
    if not 0 <= buy_discount_percent < 100:
        raise ValueError("buy_discount_percent must be >= 0 and < 100.")
    return adjusted_fair_value * (1 - buy_discount_percent / 100)


def calculate_sell_price(
    adjusted_fair_value: float,
    sell_premium_percent: float,
) -> float:
    """Calculate sell price from adjusted fair value and premium percent."""
    _require_number("adjusted_fair_value", adjusted_fair_value)
    _require_number("sell_premium_percent", sell_premium_percent)
    if sell_premium_percent < 0:
        raise ValueError("sell_premium_percent must be non-negative.")
    return adjusted_fair_value * (1 + sell_premium_percent / 100)


def calculate_discount_to_fair_value_percent(
    current_price: float,
    adjusted_fair_value: float,
) -> float:
    """Calculate current-price discount relative to adjusted fair value."""
    _require_positive_price(current_price)
    _require_positive_fair_value(adjusted_fair_value)
    return ((adjusted_fair_value - current_price) / adjusted_fair_value) * 100


def calculate_upside_to_fair_value_percent(
    current_price: float,
    adjusted_fair_value: float,
) -> float:
    """Calculate upside required for current price to reach fair value."""
    _require_positive_price(current_price)
    _require_positive_fair_value(adjusted_fair_value)
    return ((adjusted_fair_value - current_price) / current_price) * 100


def classify_valuation_recommendation(
    current_price: float,
    buy_price: float,
    sell_price: float,
) -> ValuationRecommendation:
    """Classify valuation recommendation using inclusive buy/sell thresholds."""
    _require_positive_price(current_price)
    _require_number("buy_price", buy_price)
    _require_number("sell_price", sell_price)
    if current_price <= buy_price:
        return ValuationRecommendation.BUY
    if current_price >= sell_price:
        return ValuationRecommendation.SELL
    return ValuationRecommendation.HOLD


def calculate_valuation_decision(
    inputs: ValuationDecisionInputs,
    config: ValuationDecisionConfig,
) -> ValuationDecisionResult:
    """Calculate price-versus-fair-value valuation decision."""
    validate_valuation_decision_config(config)
    validate_valuation_decision_inputs(inputs)

    if inputs.adjusted_fair_value <= 0:
        return ValuationDecisionResult(
            current_price=inputs.current_price,
            adjusted_fair_value=inputs.adjusted_fair_value,
            buy_discount_percent=config.buy_discount_percent,
            sell_premium_percent=config.sell_premium_percent,
            buy_price=None,
            sell_price=None,
            discount_to_fair_value_percent=None,
            upside_to_fair_value_percent=None,
            recommendation=ValuationRecommendation.NOT_APPLICABLE,
            explanation=(
                "Adjusted fair value must be positive to produce a valuation "
                "recommendation."
            ),
        )

    buy_price = calculate_buy_price(
        inputs.adjusted_fair_value,
        config.buy_discount_percent,
    )
    sell_price = calculate_sell_price(
        inputs.adjusted_fair_value,
        config.sell_premium_percent,
    )
    discount = calculate_discount_to_fair_value_percent(
        inputs.current_price,
        inputs.adjusted_fair_value,
    )
    upside = calculate_upside_to_fair_value_percent(
        inputs.current_price,
        inputs.adjusted_fair_value,
    )
    recommendation = classify_valuation_recommendation(
        inputs.current_price,
        buy_price,
        sell_price,
    )

    return ValuationDecisionResult(
        current_price=inputs.current_price,
        adjusted_fair_value=inputs.adjusted_fair_value,
        buy_discount_percent=config.buy_discount_percent,
        sell_premium_percent=config.sell_premium_percent,
        buy_price=buy_price,
        sell_price=sell_price,
        discount_to_fair_value_percent=discount,
        upside_to_fair_value_percent=upside,
        recommendation=recommendation,
        explanation=_build_explanation(inputs.current_price, buy_price, sell_price),
    )


def _build_explanation(
    current_price: float,
    buy_price: float,
    sell_price: float,
) -> str:
    if current_price <= buy_price:
        return (
            f"Current price {current_price} is at or below the configured "
            f"buy price {buy_price}."
        )
    if current_price >= sell_price:
        return (
            f"Current price {current_price} is at or above the configured "
            f"sell price {sell_price}."
        )
    return (
        f"Current price {current_price} is between the buy price {buy_price} "
        f"and sell price {sell_price}."
    )


def _require_positive_price(value: float) -> None:
    _require_number("current_price", value)
    if value <= 0:
        raise ValueError("current_price must be greater than 0.")


def _require_positive_fair_value(value: float) -> None:
    _require_number("adjusted_fair_value", value)
    if value <= 0:
        raise ValueError("adjusted_fair_value must be greater than 0.")


def _require_number(field_name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
