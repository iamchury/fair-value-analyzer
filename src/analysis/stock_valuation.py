from dataclasses import dataclass
from enum import Enum
from math import isfinite

from src.analysis.eps_growth import (
    EPSGrowthInputs,
    EPSGrowthResult,
    calculate_eps_growth,
)
from src.analysis.fair_value import (
    FairValueInputs,
    FairValueResult,
    calculate_fair_value,
)
from src.analysis.macro_adjustment import (
    MacroAdjustment,
    TreasuryYieldConfig,
    calculate_macro_adjustment,
)
from src.analysis.target_pe import (
    TargetPEConfig,
    TargetPEInputs,
    TargetPERecommendation,
    recommend_target_pe,
)
from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    ValuationDecisionInputs,
    ValuationDecisionResult,
    ValuationRecommendation,
    calculate_valuation_decision,
)


class StockValuationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    TARGET_PE_UNAVAILABLE = "TARGET_PE_UNAVAILABLE"
    FAIR_VALUE_UNAVAILABLE = "FAIR_VALUE_UNAVAILABLE"
    DECISION_NOT_APPLICABLE = "DECISION_NOT_APPLICABLE"


@dataclass(frozen=True)
class StockValuationInputs:
    symbol: str
    current_price: float
    trailing_eps: float | None
    forward_eps: float | None
    peg_ratio: float | None
    sector: str | None
    industry: str | None
    current_forward_pe: float | None
    treasury_current_yield_percent: float
    treasury_short_sma_percent: float
    treasury_long_sma_percent: float


@dataclass(frozen=True)
class StockValuationConfig:
    target_pe: TargetPEConfig
    treasury_yield: TreasuryYieldConfig
    decision: ValuationDecisionConfig


@dataclass(frozen=True)
class StockValuationResult:
    symbol: str
    status: StockValuationStatus
    current_price: float
    trailing_eps: float | None
    forward_eps: float | None
    eps_growth: EPSGrowthResult
    target_pe: TargetPERecommendation | None
    macro_adjustment: MacroAdjustment | None
    fair_value: FairValueResult | None
    valuation_decision: ValuationDecisionResult | None
    explanation: str


def validate_stock_valuation_inputs(inputs: StockValuationInputs) -> None:
    """Validate primitive stock valuation orchestration inputs."""
    _normalize_symbol(inputs.symbol)
    _require_positive_number("current_price", inputs.current_price)
    _require_optional_number("trailing_eps", inputs.trailing_eps)
    _require_optional_number("forward_eps", inputs.forward_eps)
    _require_optional_positive_number("peg_ratio", inputs.peg_ratio)
    _require_optional_number("current_forward_pe", inputs.current_forward_pe)
    _require_treasury_percent(
        "treasury_current_yield_percent",
        inputs.treasury_current_yield_percent,
    )
    _require_treasury_percent(
        "treasury_short_sma_percent",
        inputs.treasury_short_sma_percent,
    )
    _require_treasury_percent(
        "treasury_long_sma_percent",
        inputs.treasury_long_sma_percent,
    )


def calculate_stock_valuation(
    inputs: StockValuationInputs,
    config: StockValuationConfig,
) -> StockValuationResult:
    """Run the pure stock valuation calculation pipeline."""
    validate_stock_valuation_inputs(inputs)
    symbol = _normalize_symbol(inputs.symbol)

    eps_growth = calculate_eps_growth(
        EPSGrowthInputs(
            trailing_eps=inputs.trailing_eps,
            forward_eps=inputs.forward_eps,
        )
    )
    if not eps_growth.is_growth_rate_usable_for_target_pe:
        return StockValuationResult(
            symbol=symbol,
            status=StockValuationStatus.TARGET_PE_UNAVAILABLE,
            current_price=inputs.current_price,
            trailing_eps=inputs.trailing_eps,
            forward_eps=inputs.forward_eps,
            eps_growth=eps_growth,
            target_pe=None,
            macro_adjustment=None,
            fair_value=None,
            valuation_decision=None,
            explanation=(
                "Target PE was not calculated because the EPS growth comparison "
                f"is classified as {eps_growth.transition.value} and is not usable "
                "by the conventional growth-derived PE model."
            ),
        )

    if eps_growth.growth_percent is None:
        raise ValueError("usable EPS growth must include growth_percent.")

    target_pe = recommend_target_pe(
        TargetPEInputs(
            forward_eps_growth_percent=eps_growth.growth_percent,
            peg_ratio=inputs.peg_ratio,
            sector=inputs.sector,
            industry=inputs.industry,
            current_forward_pe=inputs.current_forward_pe,
        ),
        config.target_pe,
    )
    macro_adjustment = calculate_macro_adjustment(
        inputs.treasury_current_yield_percent,
        inputs.treasury_short_sma_percent,
        inputs.treasury_long_sma_percent,
        config.treasury_yield,
    )

    if inputs.forward_eps is None:
        return StockValuationResult(
            symbol=symbol,
            status=StockValuationStatus.FAIR_VALUE_UNAVAILABLE,
            current_price=inputs.current_price,
            trailing_eps=inputs.trailing_eps,
            forward_eps=inputs.forward_eps,
            eps_growth=eps_growth,
            target_pe=target_pe,
            macro_adjustment=macro_adjustment,
            fair_value=None,
            valuation_decision=None,
            explanation=(
                "Target PE and macro adjustment were calculated, but Forward EPS "
                "was unavailable for fair-value calculation."
            ),
        )

    fair_value = calculate_fair_value(
        FairValueInputs(
            forward_eps=inputs.forward_eps,
            recommended_target_pe=target_pe.recommended_target_pe,
            macro_adjustment_multiplier=(
                macro_adjustment.total_adjustment_multiplier
            ),
        )
    )
    valuation_decision = calculate_valuation_decision(
        ValuationDecisionInputs(
            current_price=inputs.current_price,
            adjusted_fair_value=fair_value.adjusted_fair_value,
        ),
        config.decision,
    )

    if valuation_decision.recommendation == ValuationRecommendation.NOT_APPLICABLE:
        status = StockValuationStatus.DECISION_NOT_APPLICABLE
        explanation = (
            "Fair value was calculated, but adjusted fair value is not positive, "
            "so a normal BUY, HOLD, or SELL decision is not applicable."
        )
    else:
        status = StockValuationStatus.COMPLETE
        explanation = (
            "Valuation completed using usable EPS growth, recommended Target PE, "
            "Treasury macro adjustment, and the configured valuation thresholds."
        )

    return StockValuationResult(
        symbol=symbol,
        status=status,
        current_price=inputs.current_price,
        trailing_eps=inputs.trailing_eps,
        forward_eps=inputs.forward_eps,
        eps_growth=eps_growth,
        target_pe=target_pe,
        macro_adjustment=macro_adjustment,
        fair_value=fair_value,
        valuation_decision=valuation_decision,
        explanation=explanation,
    )


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    if any(character.isspace() for character in normalized):
        raise ValueError("symbol must not contain whitespace.")
    return normalized


def _require_optional_number(field_name: str, value: float | None) -> None:
    if value is None:
        return
    _require_number(field_name, value)


def _require_optional_positive_number(
    field_name: str,
    value: float | None,
) -> None:
    if value is None:
        return
    _require_positive_number(field_name, value)


def _require_positive_number(field_name: str, value: float) -> None:
    _require_number(field_name, value)
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


def _require_treasury_percent(field_name: str, value: float) -> None:
    _require_positive_number(field_name, value)
    if value > 20:
        raise ValueError(f"{field_name} must be no more than 20.")


def _require_number(field_name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
