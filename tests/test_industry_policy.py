from dataclasses import FrozenInstanceError

import pytest

from src.analysis.industry_policy import (
    IndustryPolicyTargetPEResult,
    apply_industry_policy_to_target_pe,
    select_industry_policy,
)
from src.analysis.target_pe import TargetPEConfig, TargetPEInputs, recommend_target_pe
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
        preferred_sectors=("Technology",),
    )


def policy_configuration() -> IndustryPolicyConfiguration:
    cyclical = IndustryValuationPolicy(
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
    growth = IndustryValuationPolicy(
        name="GROWTH",
        valuation_style=ValuationStyle.GROWTH,
        target_pe_mode=TargetPEMode.CALCULATED,
        fixed_target_pe=None,
        minimum_target_pe=25.0,
        maximum_target_pe=45.0,
        use_eps_growth=True,
        use_peg_adjustment=True,
        use_sector_adjustment=True,
        use_forward_pe_penalty=True,
        rationale="growth",
    )
    quality = IndustryValuationPolicy(
        name="QUALITY_GROWTH",
        valuation_style=ValuationStyle.QUALITY_GROWTH,
        target_pe_mode=TargetPEMode.CALCULATED,
        fixed_target_pe=None,
        minimum_target_pe=20.0,
        maximum_target_pe=40.0,
        use_eps_growth=True,
        use_peg_adjustment=True,
        use_sector_adjustment=False,
        use_forward_pe_penalty=True,
        rationale="quality",
    )
    return IndustryPolicyConfiguration(
        policies={
            "CYCLICAL": cyclical,
            "GROWTH": growth,
            "QUALITY_GROWTH": quality,
        },
        symbol_policy_names={
            "MU": "CYCLICAL",
            "LITE": "GROWTH",
            "GLW": "QUALITY_GROWTH",
        },
    )


def original_result(target_pe_config: TargetPEConfig):
    inputs = TargetPEInputs(242.19, 0.13, "Technology", "Semiconductors", 5.63)
    return recommend_target_pe(inputs, target_pe_config), inputs


def test_select_policy_is_explicit_only() -> None:
    configuration = policy_configuration()

    assert select_industry_policy("mu", configuration).policy_name == "CYCLICAL"
    assert select_industry_policy("AMAT", configuration) is None
    assert select_industry_policy("MU", None) is None


def test_no_policy_preserves_original_target_pe(target_pe_config: TargetPEConfig) -> None:
    original, inputs = original_result(target_pe_config)

    result = apply_industry_policy_to_target_pe(
        "AMAT",
        original,
        inputs,
        target_pe_config,
        policy_configuration(),
    )

    assert result.policy_applied is False
    assert result.original_target_pe == original.recommended_target_pe
    assert result.policy_target_pe == original.recommended_target_pe


def test_fixed_policy_overrides_and_records_original(target_pe_config: TargetPEConfig) -> None:
    original, inputs = original_result(target_pe_config)

    result = apply_industry_policy_to_target_pe(
        "MU",
        original,
        inputs,
        target_pe_config,
        policy_configuration(),
    )

    assert result.policy_applied is True
    assert result.policy_name == "CYCLICAL"
    assert result.original_target_pe == 50.0
    assert result.policy_target_pe == 10.0
    assert result.enabled_adjustments == ()
    assert "PEG Adjustment" in result.disabled_adjustments
    assert result.warnings


def test_calculated_policy_clips_maximum(target_pe_config: TargetPEConfig) -> None:
    original, inputs = original_result(target_pe_config)

    result = apply_industry_policy_to_target_pe(
        "LITE",
        original,
        inputs,
        target_pe_config,
        policy_configuration(),
    )

    assert result.policy_name == "GROWTH"
    assert result.original_target_pe == 50.0
    assert result.policy_target_pe == 45.0
    assert "EPS Growth Adjustment" in result.enabled_adjustments
    assert result.adjustments[-1].label == "Industry policy PE range"


def test_calculated_policy_can_disable_sector(target_pe_config: TargetPEConfig) -> None:
    original, inputs = original_result(target_pe_config)

    result = apply_industry_policy_to_target_pe(
        "GLW",
        original,
        inputs,
        target_pe_config,
        policy_configuration(),
    )

    assert result.policy_name == "QUALITY_GROWTH"
    assert result.policy_target_pe == 40.0
    assert "Sector Adjustment" in result.disabled_adjustments
    assert all(adjustment.category.value != "SECTOR" for adjustment in result.adjustments)


def test_result_is_immutable(target_pe_config: TargetPEConfig) -> None:
    original, inputs = original_result(target_pe_config)
    result = apply_industry_policy_to_target_pe(
        "MU",
        original,
        inputs,
        target_pe_config,
        policy_configuration(),
    )

    assert isinstance(result, IndustryPolicyTargetPEResult)
    with pytest.raises(FrozenInstanceError):
        result.policy_target_pe = 20.0
