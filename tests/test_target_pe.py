from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.analysis.target_pe import (
    AdjustmentCategory,
    TargetPEConfig,
    TargetPEInputs,
    TargetPERecommendation,
    calculate_forward_pe_adjustment,
    calculate_growth_based_pe,
    calculate_peg_adjustment,
    calculate_sector_adjustment,
    recommend_target_pe,
    validate_target_pe_config,
    validate_target_pe_inputs,
)


@pytest.fixture
def config() -> TargetPEConfig:
    return TargetPEConfig(
        minimum_target_pe=15.0,
        maximum_target_pe=50.0,
        default_target_peg=1.0,
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


def test_valid_config_passes(config: TargetPEConfig) -> None:
    validate_target_pe_config(config)


@pytest.mark.parametrize(
    "bad_config",
    [
        TargetPEConfig(0, 50, 1, 1, 1.5, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 15, 1, 1, 1.5, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 50, 0, 1, 1.5, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 50, 1, 0, 1.5, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 50, 1, 1, 1, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 50, 1, 1, 1.5, 1.5, 5, 0, -2, -5, 5, 0, 1.5, -2, ("A",)),
        TargetPEConfig(15, 50, 1, 1, 1.5, 2, 5, 0, -2, -5, 5, 0, 0, -2, ("A",)),
        TargetPEConfig(15, 50, 1, 1, 1.5, 2, 5, 0, -2, -5, 5, 0, 1.5, -2, ("",)),
    ],
)
def test_invalid_configurations_raise(bad_config: TargetPEConfig) -> None:
    with pytest.raises(ValueError):
        validate_target_pe_config(bad_config)


@pytest.mark.parametrize("bad_value", [nan, inf, -inf])
def test_nan_and_infinity_config_values_raise(
    config: TargetPEConfig,
    bad_value: float,
) -> None:
    bad_config = TargetPEConfig(
        minimum_target_pe=config.minimum_target_pe,
        maximum_target_pe=config.maximum_target_pe,
        default_target_peg=bad_value,
        low_peg_threshold=config.low_peg_threshold,
        normal_peg_upper_threshold=config.normal_peg_upper_threshold,
        high_peg_threshold=config.high_peg_threshold,
        low_peg_adjustment=config.low_peg_adjustment,
        normal_peg_adjustment=config.normal_peg_adjustment,
        elevated_peg_adjustment=config.elevated_peg_adjustment,
        high_peg_adjustment=config.high_peg_adjustment,
        preferred_sector_adjustment=config.preferred_sector_adjustment,
        ordinary_sector_adjustment=config.ordinary_sector_adjustment,
        high_forward_pe_premium_threshold=(
            config.high_forward_pe_premium_threshold
        ),
        high_forward_pe_adjustment=config.high_forward_pe_adjustment,
        preferred_sectors=config.preferred_sectors,
    )
    with pytest.raises(ValueError):
        validate_target_pe_config(bad_config)


def test_valid_inputs_pass() -> None:
    validate_target_pe_inputs(TargetPEInputs(20, None, None, None, None))
    validate_target_pe_inputs(TargetPEInputs(-5, 1.2, "Tech", "Chips", -10))


@pytest.mark.parametrize("bad_growth", [nan, inf, -inf])
def test_invalid_growth_input_raises(bad_growth: float) -> None:
    with pytest.raises(ValueError):
        validate_target_pe_inputs(TargetPEInputs(bad_growth, None, None, None, None))


@pytest.mark.parametrize("bad_peg", [0, -1, nan, inf, -inf])
def test_invalid_peg_input_raises(bad_peg: float) -> None:
    with pytest.raises(ValueError):
        validate_target_pe_inputs(TargetPEInputs(20, bad_peg, None, None, None))


@pytest.mark.parametrize("bad_forward_pe", [nan, inf, -inf])
def test_invalid_current_forward_pe_input_raises(bad_forward_pe: float) -> None:
    with pytest.raises(ValueError):
        validate_target_pe_inputs(
            TargetPEInputs(20, None, None, None, bad_forward_pe)
        )


@pytest.mark.parametrize(
    ("growth", "expected_pe"),
    [(40, 40), (25, 25), (10, 10), (0, 0), (-5, -5)],
)
def test_growth_based_pe(
    config: TargetPEConfig,
    growth: float,
    expected_pe: float,
) -> None:
    assert calculate_growth_based_pe(growth, config) == expected_pe


def test_growth_based_pe_with_non_default_target_peg(
    config: TargetPEConfig,
) -> None:
    custom = TargetPEConfig(
        **{**config.__dict__, "default_target_peg": 1.2}
    )
    assert calculate_growth_based_pe(25, custom) == pytest.approx(30)


@pytest.mark.parametrize(
    ("peg_ratio", "expected_value", "expected_label"),
    [
        (None, 0.0, "PEG unavailable"),
        (0.95, 5.0, "PEG below 1.0"),
        (1.0, 0.0, "PEG normal"),
        (1.25, 0.0, "PEG normal"),
        (1.5, 0.0, "PEG normal"),
        (1.75, -2.0, "PEG elevated"),
        (2.0, -2.0, "PEG elevated"),
        (2.1, -5.0, "PEG above 2.0"),
    ],
)
def test_peg_adjustment_bands(
    config: TargetPEConfig,
    peg_ratio: float | None,
    expected_value: float,
    expected_label: str,
) -> None:
    adjustment = calculate_peg_adjustment(peg_ratio, config)
    assert adjustment.category == AdjustmentCategory.PEG
    assert adjustment.value == expected_value
    assert adjustment.label == expected_label
    assert adjustment.explanation


def test_sector_adjustment_preferred_sector(config: TargetPEConfig) -> None:
    adjustment = calculate_sector_adjustment("Technology", None, config)
    assert adjustment.value == 5.0
    assert "Sector 'Technology'" in adjustment.explanation


def test_sector_adjustment_preferred_industry(config: TargetPEConfig) -> None:
    adjustment = calculate_sector_adjustment(None, "Semiconductors", config)
    assert adjustment.value == 5.0
    assert "Industry 'Semiconductors'" in adjustment.explanation


def test_sector_adjustment_case_insensitive_and_stripped(
    config: TargetPEConfig,
) -> None:
    adjustment = calculate_sector_adjustment("  technology  ", None, config)
    assert adjustment.value == 5.0


def test_sector_adjustment_applies_premium_once(config: TargetPEConfig) -> None:
    adjustment = calculate_sector_adjustment(
        "Technology",
        "Semiconductors",
        config,
    )
    assert adjustment.value == 5.0


def test_sector_adjustment_ordinary_sector(config: TargetPEConfig) -> None:
    adjustment = calculate_sector_adjustment(
        "Consumer Defensive",
        "Food Distribution",
        config,
    )
    assert adjustment.value == 0.0
    assert adjustment.label == "Ordinary sector"


def test_sector_adjustment_missing_classification(config: TargetPEConfig) -> None:
    adjustment = calculate_sector_adjustment(None, None, config)
    assert adjustment.value == 0.0
    assert "unavailable" in adjustment.explanation


@pytest.mark.parametrize("current_forward_pe", [None, 0, -3])
def test_forward_pe_adjustment_missing_or_non_positive(
    config: TargetPEConfig,
    current_forward_pe: float | None,
) -> None:
    adjustment = calculate_forward_pe_adjustment(current_forward_pe, 20, config)
    assert adjustment.value == 0.0


def test_forward_pe_adjustment_non_positive_growth_based_pe(
    config: TargetPEConfig,
) -> None:
    adjustment = calculate_forward_pe_adjustment(20, 0, config)
    assert adjustment.value == 0.0


@pytest.mark.parametrize(
    ("current_forward_pe", "expected_value"),
    [(29.0, 0.0), (30.0, 0.0), (30.01, -2.0)],
)
def test_forward_pe_adjustment_thresholds(
    config: TargetPEConfig,
    current_forward_pe: float,
    expected_value: float,
) -> None:
    adjustment = calculate_forward_pe_adjustment(current_forward_pe, 20, config)
    assert adjustment.value == pytest.approx(expected_value)


def test_example_a_preferred_growth_stock(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(28, 0.95, "Technology", "Semiconductors", 35),
        config,
    )
    assert result.growth_based_pe == 28
    assert [item.value for item in result.adjustments[:4]] == [28, 5, 5, 0]
    assert result.raw_target_pe == 38
    assert result.recommended_target_pe == 38
    assert not result.was_minimum_applied
    assert not result.was_maximum_applied


def test_example_b_expensive_growth_stock(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(30, 2.2, "Technology", "Communication Equipment", 60),
        config,
    )
    assert [item.value for item in result.adjustments[:4]] == [30, -5, 5, -2]
    assert result.raw_target_pe == 28
    assert result.recommended_target_pe == 28


def test_example_c_maximum_cap(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(60, 0.8, "Technology", None, 70),
        config,
    )
    assert [item.value for item in result.adjustments[:4]] == [60, 5, 5, 0]
    assert result.raw_target_pe == 70
    assert result.recommended_target_pe == 50
    assert result.was_maximum_applied
    assert not result.was_minimum_applied
    assert result.adjustments[-1].category == AdjustmentCategory.LIMIT
    assert result.adjustments[-1].value == -20


def test_example_d_minimum_floor(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(5, 2.5, "Consumer Defensive", "Food Distribution", 10),
        config,
    )
    assert [item.value for item in result.adjustments[:4]] == [5, -5, 0, -2]
    assert result.raw_target_pe == -2
    assert result.recommended_target_pe == 15
    assert result.was_minimum_applied
    assert not result.was_maximum_applied
    assert result.adjustments[-1].category == AdjustmentCategory.LIMIT
    assert result.adjustments[-1].value == 17


def test_example_e_missing_data(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(20, None, None, None, None),
        config,
    )
    assert [item.value for item in result.adjustments] == [20, 0, 0, 0]
    assert result.growth_based_pe == 20
    assert result.raw_target_pe == 20
    assert result.recommended_target_pe == 20


def test_no_limit_case(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(25, 1.2, "Other", None, 20),
        config,
    )
    assert result.raw_target_pe == 25
    assert result.recommended_target_pe == 25
    assert len(result.adjustments) == 4


def test_adjustment_ordering_and_explanations(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(28, 0.95, "Technology", "Semiconductors", 35),
        config,
    )
    assert [item.category for item in result.adjustments] == [
        AdjustmentCategory.GROWTH,
        AdjustmentCategory.PEG,
        AdjustmentCategory.SECTOR,
        AdjustmentCategory.VALUATION,
    ]
    assert all(item.label and item.explanation for item in result.adjustments)


def test_growth_is_not_double_counted(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(28, 0.95, "Technology", "Semiconductors", 35),
        config,
    )
    non_growth_values = sum(item.value for item in result.adjustments[1:])
    assert result.raw_target_pe == result.growth_based_pe + non_growth_values


def test_recommendation_dataclasses_are_immutable(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(20, None, None, None, None),
        config,
    )
    with pytest.raises(FrozenInstanceError):
        result.recommended_target_pe = 30


def test_recommendation_result_type(config: TargetPEConfig) -> None:
    result = recommend_target_pe(
        TargetPEInputs(20, None, None, None, None),
        config,
    )
    assert isinstance(result, TargetPERecommendation)
    assert result.minimum_target_pe == config.minimum_target_pe
    assert result.maximum_target_pe == config.maximum_target_pe
