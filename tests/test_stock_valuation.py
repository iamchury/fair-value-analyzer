from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

import src.analysis.stock_valuation as stock_valuation
from src.analysis.eps_growth import (
    EPSGrowthInputs,
    EPSGrowthResult,
    EPSTransition,
    calculate_eps_growth,
)
from src.analysis.fair_value import FairValueResult
from src.analysis.macro_adjustment import MacroAdjustment, TreasuryYieldConfig
from src.analysis.stock_valuation import (
    StockValuationConfig,
    StockValuationInputs,
    StockValuationResult,
    StockValuationStatus,
    calculate_stock_valuation,
    validate_stock_valuation_inputs,
)
from src.analysis.target_pe import TargetPEConfig, TargetPERecommendation
from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    ValuationDecisionResult,
    ValuationRecommendation,
)
from src.config.industry_policies import (
    IndustryPolicyConfiguration,
    IndustryValuationPolicy,
    TargetPEMode,
    ValuationStyle,
)


@pytest.fixture
def target_pe_config() -> TargetPEConfig:
    return TargetPEConfig(
        minimum_target_pe=15.0,
        maximum_target_pe=50.0,
        default_target_peg=1.0,
        maximum_eps_growth_percent=40.0,
        low_peg_threshold=1.0,
        normal_peg_upper_threshold=1.5,
        high_peg_threshold=2.0,
        low_peg_adjustment=5.0,
        normal_peg_adjustment=0.0,
        elevated_peg_adjustment=-2.0,
        high_peg_adjustment=-5.0,
        preferred_sector_adjustment=5.0,
        ordinary_sector_adjustment=0.0,
        high_forward_pe_premium_threshold=1.5,
        high_forward_pe_adjustment=-2.0,
        preferred_sectors=(
            "Technology",
            "Semiconductors",
            "Semiconductor Equipment",
            "Communication Equipment",
            "Computer Hardware",
            "Electronic Components",
        ),
    )


@pytest.fixture
def treasury_config() -> TreasuryYieldConfig:
    return TreasuryYieldConfig(
        threshold_yield_percent=4.3,
        maximum_discount_percent=25.0,
        trend_tolerance_percentage_points=0.05,
        rising_adjustment_percent=-10.0,
        neutral_adjustment_percent=0.0,
        falling_adjustment_percent=10.0,
    )


@pytest.fixture
def decision_config() -> ValuationDecisionConfig:
    return ValuationDecisionConfig(
        buy_discount_percent=20.0,
        sell_premium_percent=20.0,
    )


@pytest.fixture
def config(
    target_pe_config: TargetPEConfig,
    treasury_config: TreasuryYieldConfig,
    decision_config: ValuationDecisionConfig,
) -> StockValuationConfig:
    return StockValuationConfig(
        target_pe=target_pe_config,
        treasury_yield=treasury_config,
        decision=decision_config,
    )


def complete_inputs(**overrides: object) -> StockValuationInputs:
    values = {
        "symbol": "lite",
        "current_price": 80.0,
        "trailing_eps": 5.0,
        "forward_eps": 6.0,
        "peg_ratio": 0.95,
        "sector": "Technology",
        "industry": "Communication Equipment",
        "current_forward_pe": 25.0,
        "treasury_current_yield_percent": 4.6,
        "treasury_short_sma_percent": 4.5,
        "treasury_long_sma_percent": 4.4,
    }
    values.update(overrides)
    return StockValuationInputs(**values)


def test_complete_buy_example(config: StockValuationConfig) -> None:
    result = calculate_stock_valuation(complete_inputs(), config)

    assert isinstance(result, StockValuationResult)
    assert result.symbol == "LITE"
    assert result.status == StockValuationStatus.COMPLETE
    assert result.eps_growth.growth_percent == 20.0
    assert isinstance(result.target_pe, TargetPERecommendation)
    assert result.target_pe.growth_based_pe == 20.0
    assert result.target_pe.raw_target_pe == 30.0
    assert result.target_pe.recommended_target_pe == 30.0
    assert isinstance(result.macro_adjustment, MacroAdjustment)
    assert result.macro_adjustment.level_discount_percent == pytest.approx(9.0)
    assert result.macro_adjustment.trend_adjustment_percent == -10.0
    assert result.macro_adjustment.total_adjustment_multiplier == pytest.approx(0.819)
    assert isinstance(result.fair_value, FairValueResult)
    assert result.fair_value.base_fair_value == 180.0
    assert result.fair_value.adjusted_fair_value == pytest.approx(147.42)
    assert isinstance(result.valuation_decision, ValuationDecisionResult)
    assert result.valuation_decision.buy_price == pytest.approx(117.936)
    assert result.valuation_decision.recommendation == ValuationRecommendation.BUY
    assert result.explanation == (
        "Valuation completed using usable EPS growth, recommended Target PE, "
        "Treasury macro adjustment, and the configured valuation thresholds."
    )


def test_complete_hold_example(config: StockValuationConfig) -> None:
    result = calculate_stock_valuation(
        complete_inputs(current_price=130.0),
        config,
    )

    assert result.status == StockValuationStatus.COMPLETE
    assert result.valuation_decision.recommendation == ValuationRecommendation.HOLD


def test_complete_sell_example(config: StockValuationConfig) -> None:
    result = calculate_stock_valuation(
        complete_inputs(current_price=180.0),
        config,
    )

    assert result.status == StockValuationStatus.COMPLETE
    assert result.valuation_decision.recommendation == ValuationRecommendation.SELL


@pytest.mark.parametrize(
    ("trailing_eps", "forward_eps", "transition"),
    [
        (-2.0, 1.0, EPSTransition.LOSS_TO_PROFIT),
        (1.0, -2.0, EPSTransition.PROFIT_TO_LOSS),
        (-2.0, -1.0, EPSTransition.LOSS_NARROWING),
        (None, 5.0, EPSTransition.UNAVAILABLE),
        (0.0, 1.0, EPSTransition.ZERO_BASE),
    ],
)
def test_unusable_eps_growth_stops_before_target_pe(
    config: StockValuationConfig,
    trailing_eps: float | None,
    forward_eps: float | None,
    transition: EPSTransition,
) -> None:
    result = calculate_stock_valuation(
        complete_inputs(trailing_eps=trailing_eps, forward_eps=forward_eps),
        config,
    )

    assert result.status == StockValuationStatus.TARGET_PE_UNAVAILABLE
    assert result.eps_growth.transition == transition
    assert result.target_pe is None
    assert result.macro_adjustment is None
    assert result.fair_value is None
    assert result.valuation_decision is None
    assert result.explanation == (
        "Target PE was not calculated because the EPS growth comparison "
        f"is classified as {transition.value} and is not usable by the "
        "conventional growth-derived PE model."
    )


def test_decision_not_applicable_reachable_with_zero_forward_eps(
    config: StockValuationConfig,
) -> None:
    result = calculate_stock_valuation(
        complete_inputs(
            current_price=80.0,
            trailing_eps=5.0,
            forward_eps=0.0,
            peg_ratio=None,
            sector=None,
            industry=None,
            current_forward_pe=None,
        ),
        config,
    )

    assert result.status == StockValuationStatus.DECISION_NOT_APPLICABLE
    assert result.target_pe is not None
    assert result.macro_adjustment is not None
    assert result.fair_value is not None
    assert result.fair_value.adjusted_fair_value == 0.0
    assert result.valuation_decision.recommendation == (
        ValuationRecommendation.NOT_APPLICABLE
    )
    assert result.explanation == (
        "Fair value was calculated, but adjusted fair value is not positive, "
        "so a normal BUY, HOLD, or SELL decision is not applicable."
    )


def test_fair_value_unavailable_defensive_path(
    monkeypatch: pytest.MonkeyPatch,
    config: StockValuationConfig,
) -> None:
    monkeypatch.setattr(
        stock_valuation,
        "calculate_eps_growth",
        lambda inputs: EPSGrowthResult(
            trailing_eps=5.0,
            forward_eps=None,
            growth_percent=20.0,
            transition=EPSTransition.POSITIVE_GROWTH,
            is_growth_rate_usable_for_target_pe=True,
            explanation="forced usable EPS growth",
        ),
    )

    result = calculate_stock_valuation(
        complete_inputs(forward_eps=None),
        config,
    )

    assert result.status == StockValuationStatus.FAIR_VALUE_UNAVAILABLE
    assert result.target_pe is not None
    assert result.macro_adjustment is not None
    assert result.fair_value is None
    assert result.valuation_decision is None
    assert result.explanation == (
        "Target PE and macro adjustment were calculated, but Forward EPS "
        "was unavailable for fair-value calculation."
    )


def test_no_internal_rounding(config: StockValuationConfig) -> None:
    result = calculate_stock_valuation(
        complete_inputs(
            current_price=1.0,
            trailing_eps=3.0,
            forward_eps=4.0,
            peg_ratio=None,
            sector=None,
            industry=None,
            current_forward_pe=None,
        ),
        config,
    )

    assert result.eps_growth.growth_percent == pytest.approx(100 / 3)
    assert result.fair_value.adjusted_fair_value == pytest.approx(
        4.0 * result.target_pe.recommended_target_pe * 0.819
    )


def test_normalized_symbol_and_values_retained(config: StockValuationConfig) -> None:
    result = calculate_stock_valuation(
        complete_inputs(symbol="  lite  "),
        config,
    )

    assert result.symbol == "LITE"
    assert result.current_price == 80.0
    assert result.trailing_eps == 5.0
    assert result.forward_eps == 6.0


@pytest.mark.parametrize("bad_symbol", ["", "   ", "BRK B", 123])
def test_invalid_symbol_rejected(
    config: StockValuationConfig,
    bad_symbol: object,
) -> None:
    with pytest.raises(ValueError):
        validate_stock_valuation_inputs(complete_inputs(symbol=bad_symbol))


def test_positive_current_price_accepted(config: StockValuationConfig) -> None:
    validate_stock_valuation_inputs(complete_inputs(current_price=1.0))


@pytest.mark.parametrize("current_price", [0.0, -1.0])
def test_non_positive_current_price_rejected(
    current_price: float,
) -> None:
    with pytest.raises(ValueError):
        validate_stock_valuation_inputs(complete_inputs(current_price=current_price))


@pytest.mark.parametrize(
    ("trailing_eps", "forward_eps"),
    [(None, None), (-1.0, -2.0), (0.0, 0.0), (5.0, 6.0)],
)
def test_optional_eps_values_accepted(
    trailing_eps: float | None,
    forward_eps: float | None,
) -> None:
    validate_stock_valuation_inputs(
        complete_inputs(trailing_eps=trailing_eps, forward_eps=forward_eps)
    )


@pytest.mark.parametrize("peg_ratio", [0.0, -1.0])
def test_invalid_peg_rejected(peg_ratio: float) -> None:
    with pytest.raises(ValueError):
        validate_stock_valuation_inputs(complete_inputs(peg_ratio=peg_ratio))


def test_unusual_negative_current_forward_pe_accepted() -> None:
    validate_stock_valuation_inputs(complete_inputs(current_forward_pe=-10.0))


@pytest.mark.parametrize(
    "field_name",
    [
        "treasury_current_yield_percent",
        "treasury_short_sma_percent",
        "treasury_long_sma_percent",
    ],
)
@pytest.mark.parametrize("bad_value", [0.0, -1.0, 20.01])
def test_invalid_treasury_values_rejected(
    field_name: str,
    bad_value: float,
) -> None:
    with pytest.raises(ValueError):
        validate_stock_valuation_inputs(complete_inputs(**{field_name: bad_value}))


@pytest.mark.parametrize("bad_value", [nan, inf, -inf, True, "1", object()])
@pytest.mark.parametrize(
    "field_name",
    [
        "current_price",
        "trailing_eps",
        "forward_eps",
        "peg_ratio",
        "current_forward_pe",
        "treasury_current_yield_percent",
        "treasury_short_sma_percent",
        "treasury_long_sma_percent",
    ],
)
def test_invalid_numeric_values_rejected(
    field_name: str,
    bad_value: object,
) -> None:
    with pytest.raises(ValueError):
        validate_stock_valuation_inputs(complete_inputs(**{field_name: bad_value}))


def test_config_dataclass_is_immutable(config: StockValuationConfig) -> None:
    with pytest.raises(FrozenInstanceError):
        config.decision = ValuationDecisionConfig(10.0, 10.0)


def test_invalid_nested_target_pe_config_raises_clear_error(
    config: StockValuationConfig,
) -> None:
    bad_config = StockValuationConfig(
        target_pe=TargetPEConfig(
            **{**config.target_pe.__dict__, "maximum_target_pe": 10.0}
        ),
        treasury_yield=config.treasury_yield,
        decision=config.decision,
    )

    with pytest.raises(ValueError, match="maximum_target_pe"):
        calculate_stock_valuation(complete_inputs(), bad_config)


def test_invalid_nested_treasury_config_raises_clear_error(
    config: StockValuationConfig,
) -> None:
    bad_config = StockValuationConfig(
        target_pe=config.target_pe,
        treasury_yield=TreasuryYieldConfig(
            **{**config.treasury_yield.__dict__, "threshold_yield_percent": 0.0}
        ),
        decision=config.decision,
    )

    with pytest.raises(ValueError, match="threshold_yield_percent"):
        calculate_stock_valuation(complete_inputs(), bad_config)


def test_invalid_nested_decision_config_raises_clear_error(
    config: StockValuationConfig,
) -> None:
    bad_config = StockValuationConfig(
        target_pe=config.target_pe,
        treasury_yield=config.treasury_yield,
        decision=ValuationDecisionConfig(100.0, 20.0),
    )

    with pytest.raises(ValueError, match="buy_discount_percent"):
        calculate_stock_valuation(complete_inputs(), bad_config)


def test_target_pe_not_calculated_when_eps_growth_unusable(
    monkeypatch: pytest.MonkeyPatch,
    config: StockValuationConfig,
) -> None:
    def fail_recommend_target_pe(*args, **kwargs):
        raise AssertionError("Target PE should not be calculated.")

    monkeypatch.setattr(
        stock_valuation,
        "recommend_target_pe",
        fail_recommend_target_pe,
    )

    result = calculate_stock_valuation(
        complete_inputs(trailing_eps=-2.0, forward_eps=1.0),
        config,
    )

    assert result.status == StockValuationStatus.TARGET_PE_UNAVAILABLE


def test_macro_not_calculated_when_target_pe_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    config: StockValuationConfig,
) -> None:
    def fail_macro(*args, **kwargs):
        raise AssertionError("Macro adjustment should not be calculated.")

    monkeypatch.setattr(stock_valuation, "calculate_macro_adjustment", fail_macro)

    result = calculate_stock_valuation(
        complete_inputs(trailing_eps=0.0, forward_eps=1.0),
        config,
    )

    assert result.status == StockValuationStatus.TARGET_PE_UNAVAILABLE


def test_fair_value_not_calculated_when_prior_stage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    config: StockValuationConfig,
) -> None:
    def fail_fair_value(*args, **kwargs):
        raise AssertionError("Fair value should not be calculated.")

    monkeypatch.setattr(stock_valuation, "calculate_fair_value", fail_fair_value)

    result = calculate_stock_valuation(
        complete_inputs(trailing_eps=None, forward_eps=5.0),
        config,
    )

    assert result.status == StockValuationStatus.TARGET_PE_UNAVAILABLE


def test_valuation_decision_not_calculated_when_fair_value_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    config: StockValuationConfig,
) -> None:
    monkeypatch.setattr(
        stock_valuation,
        "calculate_eps_growth",
        lambda inputs: EPSGrowthResult(
            trailing_eps=5.0,
            forward_eps=None,
            growth_percent=20.0,
            transition=EPSTransition.POSITIVE_GROWTH,
            is_growth_rate_usable_for_target_pe=True,
            explanation="forced usable EPS growth",
        ),
    )

    def fail_decision(*args, **kwargs):
        raise AssertionError("Valuation decision should not be calculated.")

    monkeypatch.setattr(
        stock_valuation,
        "calculate_valuation_decision",
        fail_decision,
    )

    result = calculate_stock_valuation(
        complete_inputs(forward_eps=None),
        config,
    )

    assert result.status == StockValuationStatus.FAIR_VALUE_UNAVAILABLE


def test_input_and_result_dataclasses_are_immutable(
    config: StockValuationConfig,
) -> None:
    inputs = complete_inputs()
    result = calculate_stock_valuation(inputs, config)

    with pytest.raises(FrozenInstanceError):
        inputs.current_price = 81.0
    with pytest.raises(FrozenInstanceError):
        result.status = StockValuationStatus.TARGET_PE_UNAVAILABLE


def test_result_retains_existing_eps_growth_result_type(
    config: StockValuationConfig,
) -> None:
    result = calculate_stock_valuation(complete_inputs(), config)

    assert result.eps_growth == calculate_eps_growth(EPSGrowthInputs(5.0, 6.0))


def test_industry_policy_changes_target_pe_used_but_preserves_original(
    config: StockValuationConfig,
) -> None:
    policy = IndustryValuationPolicy(
        name="CYCLICAL",
        valuation_style=ValuationStyle.CYCLICAL,
        target_pe_mode=TargetPEMode.FIXED,
        fixed_target_pe=10.0,
        minimum_target_pe=7.0,
        maximum_target_pe=12.0,
        use_eps_growth=False,
        use_peg_adjustment=False,
        use_sector_adjustment=False,
        use_forward_pe_penalty=False,
        rationale="cyclical",
    )
    policy_config = IndustryPolicyConfiguration(
        policies={"CYCLICAL": policy},
        symbol_policy_names={"MU": "CYCLICAL"},
    )
    policy_enabled_config = StockValuationConfig(
        target_pe=config.target_pe,
        treasury_yield=config.treasury_yield,
        decision=config.decision,
        industry_policy=policy_config,
    )

    result = calculate_stock_valuation(
        complete_inputs(
            symbol="MU",
            trailing_eps=44.06,
            forward_eps=150.77,
            valuation_eps=73.37,
            valuation_eps_method="CURRENT_YEAR",
            valuation_eps_period="0y",
            peg_ratio=0.13,
            current_forward_pe=5.63,
        ),
        policy_enabled_config,
    )

    assert result.target_pe.recommended_target_pe == 50.0
    assert result.target_pe_used == 10.0
    assert result.industry_policy.original_target_pe == 50.0
    assert result.industry_policy.policy_target_pe == 10.0
    assert result.fair_value.recommended_target_pe == 10.0
    assert result.fair_value.adjusted_fair_value == pytest.approx(73.37 * 10.0 * 0.819)
