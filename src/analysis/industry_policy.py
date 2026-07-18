from collections.abc import Mapping
from dataclasses import dataclass

from src.analysis.target_pe import (
    AdjustmentCategory,
    TargetPEAdjustment,
    TargetPEConfig,
    TargetPEInputs,
    TargetPERecommendation,
    calculate_effective_eps_growth_percent,
    calculate_forward_pe_adjustment,
    calculate_peg_adjustment,
    calculate_sector_adjustment,
    validate_target_pe_config,
    validate_target_pe_inputs,
)
from src.config.industry_policies import (
    IndustryPolicyConfiguration,
    IndustryValuationPolicy,
    TargetPEMode,
    ValuationStyle,
)


@dataclass(frozen=True)
class CalculationStep:
    name: str
    input_values: Mapping[str, object]
    formula: str | None
    result: float | None
    explanation: str


@dataclass(frozen=True)
class AppliedIndustryPolicy:
    symbol: str
    policy_name: str
    policy: IndustryValuationPolicy


@dataclass(frozen=True)
class IndustryPolicyTargetPEResult:
    symbol: str
    policy_applied: bool
    policy_name: str | None
    valuation_style: ValuationStyle | None
    target_pe_mode: TargetPEMode | None
    original_target_pe: float
    policy_target_pe: float
    minimum_target_pe: float | None
    maximum_target_pe: float | None
    fixed_target_pe: float | None
    enabled_adjustments: tuple[str, ...]
    disabled_adjustments: tuple[str, ...]
    rationale: str | None
    warnings: tuple[str, ...]
    calculation_steps: tuple[CalculationStep, ...]
    adjustments: tuple[TargetPEAdjustment, ...] = ()


def select_industry_policy(
    symbol: str,
    configuration: IndustryPolicyConfiguration | None,
) -> AppliedIndustryPolicy | None:
    """Return the explicitly configured policy for a symbol, if one exists."""
    if configuration is None:
        return None
    normalized_symbol = _normalize_symbol(symbol)
    policy_name = configuration.symbol_policy_names.get(normalized_symbol)
    if policy_name is None:
        return None
    return AppliedIndustryPolicy(
        symbol=normalized_symbol,
        policy_name=policy_name,
        policy=configuration.policies[policy_name],
    )


def apply_industry_policy_to_target_pe(
    symbol: str,
    original_target_pe: TargetPERecommendation,
    inputs: TargetPEInputs,
    target_pe_config: TargetPEConfig,
    configuration: IndustryPolicyConfiguration | None,
) -> IndustryPolicyTargetPEResult:
    """Apply an explicit industry policy to an existing Target PE result."""
    validate_target_pe_config(target_pe_config)
    validate_target_pe_inputs(inputs)
    normalized_symbol = _normalize_symbol(symbol)
    applied = select_industry_policy(normalized_symbol, configuration)
    if applied is None:
        return IndustryPolicyTargetPEResult(
            symbol=normalized_symbol,
            policy_applied=False,
            policy_name=None,
            valuation_style=None,
            target_pe_mode=None,
            original_target_pe=original_target_pe.recommended_target_pe,
            policy_target_pe=original_target_pe.recommended_target_pe,
            minimum_target_pe=None,
            maximum_target_pe=None,
            fixed_target_pe=None,
            enabled_adjustments=(),
            disabled_adjustments=(),
            rationale=None,
            warnings=(),
            calculation_steps=(
                CalculationStep(
                    name="No industry policy",
                    input_values={"symbol": normalized_symbol},
                    formula=None,
                    result=original_target_pe.recommended_target_pe,
                    explanation=(
                        "No explicit industry policy was configured; original "
                        "Target PE remains authoritative."
                    ),
                ),
            ),
        )

    if applied.policy.target_pe_mode == TargetPEMode.FIXED:
        return _fixed_policy_result(normalized_symbol, original_target_pe, applied)
    return _calculated_policy_result(
        normalized_symbol,
        original_target_pe,
        inputs,
        target_pe_config,
        applied,
    )


def _fixed_policy_result(
    symbol: str,
    original: TargetPERecommendation,
    applied: AppliedIndustryPolicy,
) -> IndustryPolicyTargetPEResult:
    policy = applied.policy
    assert policy.fixed_target_pe is not None
    return IndustryPolicyTargetPEResult(
        symbol=symbol,
        policy_applied=True,
        policy_name=applied.policy_name,
        valuation_style=policy.valuation_style,
        target_pe_mode=policy.target_pe_mode,
        original_target_pe=original.recommended_target_pe,
        policy_target_pe=policy.fixed_target_pe,
        minimum_target_pe=policy.minimum_target_pe,
        maximum_target_pe=policy.maximum_target_pe,
        fixed_target_pe=policy.fixed_target_pe,
        enabled_adjustments=(),
        disabled_adjustments=_disabled_adjustments(policy),
        rationale=policy.rationale,
        warnings=("Original calculated Target PE was overridden by fixed industry policy.",),
        calculation_steps=(
            CalculationStep(
                name="Fixed industry Target PE",
                input_values={
                    "original_target_pe": original.recommended_target_pe,
                    "fixed_target_pe": policy.fixed_target_pe,
                },
                formula="fixed_target_pe",
                result=policy.fixed_target_pe,
                explanation="Fixed industry policy overrides the original Target PE.",
            ),
        ),
    )


def _calculated_policy_result(
    symbol: str,
    original: TargetPERecommendation,
    inputs: TargetPEInputs,
    config: TargetPEConfig,
    applied: AppliedIndustryPolicy,
) -> IndustryPolicyTargetPEResult:
    policy = applied.policy
    adjustments: list[TargetPEAdjustment] = []
    growth_based_pe = 0.0
    effective_growth = calculate_effective_eps_growth_percent(
        inputs.forward_eps_growth_percent,
        config,
    )

    if policy.use_eps_growth:
        growth_based_pe = effective_growth * config.default_target_peg
        adjustments.append(
            TargetPEAdjustment(
                category=AdjustmentCategory.GROWTH,
                label="EPS growth",
                value=growth_based_pe,
                explanation=(
                    f"Effective Forward EPS growth of {effective_growth}% "
                    f"produced a base PE of {growth_based_pe}."
                ),
            )
        )
    if policy.use_peg_adjustment:
        adjustments.append(calculate_peg_adjustment(inputs.peg_ratio, config))
    if policy.use_sector_adjustment:
        adjustments.append(
            calculate_sector_adjustment(inputs.sector, inputs.industry, config)
        )
    if policy.use_forward_pe_penalty:
        adjustments.append(
            calculate_forward_pe_adjustment(
                inputs.current_forward_pe,
                growth_based_pe,
                config,
            )
        )

    raw_target_pe = sum(adjustment.value for adjustment in adjustments)
    policy_target_pe = min(
        max(raw_target_pe, policy.minimum_target_pe),
        policy.maximum_target_pe,
    )
    if policy_target_pe != raw_target_pe:
        adjustments.append(
            TargetPEAdjustment(
                category=AdjustmentCategory.LIMIT,
                label="Industry policy PE range",
                value=policy_target_pe - raw_target_pe,
                explanation=(
                    "Target PE was clipped to the configured industry policy "
                    f"range of {policy.minimum_target_pe} to {policy.maximum_target_pe}."
                ),
            )
        )

    return IndustryPolicyTargetPEResult(
        symbol=symbol,
        policy_applied=True,
        policy_name=applied.policy_name,
        valuation_style=policy.valuation_style,
        target_pe_mode=policy.target_pe_mode,
        original_target_pe=original.recommended_target_pe,
        policy_target_pe=policy_target_pe,
        minimum_target_pe=policy.minimum_target_pe,
        maximum_target_pe=policy.maximum_target_pe,
        fixed_target_pe=policy.fixed_target_pe,
        enabled_adjustments=_enabled_adjustments(policy),
        disabled_adjustments=_disabled_adjustments(policy),
        rationale=policy.rationale,
        warnings=(),
        calculation_steps=(
            CalculationStep(
                name="Calculated industry Target PE",
                input_values={
                    "raw_target_pe": raw_target_pe,
                    "minimum_target_pe": policy.minimum_target_pe,
                    "maximum_target_pe": policy.maximum_target_pe,
                },
                formula="clip(sum(enabled_adjustments), minimum, maximum)",
                result=policy_target_pe,
                explanation="Enabled policy adjustments were summed and clipped.",
            ),
        ),
        adjustments=tuple(adjustments),
    )


def _enabled_adjustments(policy: IndustryValuationPolicy) -> tuple[str, ...]:
    return tuple(
        label
        for label, enabled in _adjustment_flags(policy)
        if enabled
    )


def _disabled_adjustments(policy: IndustryValuationPolicy) -> tuple[str, ...]:
    return tuple(
        label
        for label, enabled in _adjustment_flags(policy)
        if not enabled
    )


def _adjustment_flags(policy: IndustryValuationPolicy) -> tuple[tuple[str, bool], ...]:
    return (
        ("EPS Growth Adjustment", policy.use_eps_growth),
        ("PEG Adjustment", policy.use_peg_adjustment),
        ("Sector Adjustment", policy.use_sector_adjustment),
        ("Forward PE Penalty", policy.use_forward_pe_penalty),
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
