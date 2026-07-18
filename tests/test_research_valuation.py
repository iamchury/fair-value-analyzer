from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from src.analysis.research_valuation import (
    ResearchValuationInputs,
    ResearchValuationStatus,
    ValuationComparisonResult,
    calculate_research_valuation,
    compare_valuations,
)
from src.config.valuation_profiles import ValuationProfile, ValuationStyle


def profile(**overrides: object) -> ValuationProfile:
    values = {
        "symbol": "LITE",
        "valuation_style": ValuationStyle.GROWTH,
        "valuation_eps": 18.30,
        "eps_fiscal_year": "FY2027",
        "target_pe": 40.0,
        "use_peg_adjustment": True,
        "dcf_fair_value": None,
        "source_note": "research note",
    }
    values.update(overrides)
    return ValuationProfile(**values)


def test_research_fair_value_uses_profile_eps_target_pe_and_macro_multiplier() -> None:
    result = calculate_research_valuation(
        ResearchValuationInputs(
            profile=profile(),
            macro_adjustment_multiplier=0.819,
        )
    )

    assert result.status == ResearchValuationStatus.COMPLETE
    assert result.research_base_fair_value == pytest.approx(732.0)
    assert result.research_adjusted_fair_value == pytest.approx(599.508)
    assert result.macro_adjustment_multiplier == 0.819
    assert result.dcf_fair_value is None


def test_research_fair_value_supports_mu_reference_values() -> None:
    result = calculate_research_valuation(
        ResearchValuationInputs(
            profile=profile(
                symbol="MU",
                valuation_style=ValuationStyle.CYCLICAL,
                valuation_eps=73.39,
                eps_fiscal_year="FY2026",
                target_pe=10.0,
                use_peg_adjustment=False,
                dcf_fair_value=618.10,
            ),
            macro_adjustment_multiplier=0.9419,
        )
    )

    assert result.research_base_fair_value == pytest.approx(733.9)
    assert result.research_adjusted_fair_value == pytest.approx(691.26041)
    assert result.dcf_fair_value == 618.10


@pytest.mark.parametrize(
    ("valuation_eps", "multiplier"),
    [(0, 1.0), (-2.0, 1.0), (18.3, 0)],
)
def test_non_positive_adjusted_research_value_is_not_applicable(
    valuation_eps: float,
    multiplier: float,
) -> None:
    result = calculate_research_valuation(
        ResearchValuationInputs(
            profile=profile(valuation_eps=valuation_eps),
            macro_adjustment_multiplier=multiplier,
        )
    )

    assert result.status == ResearchValuationStatus.NOT_APPLICABLE


@pytest.mark.parametrize("multiplier", [True, "1", -0.1, nan, inf, -inf])
def test_invalid_macro_multiplier_is_rejected(multiplier: object) -> None:
    with pytest.raises(ValueError):
        calculate_research_valuation(
            ResearchValuationInputs(
                profile=profile(),
                macro_adjustment_multiplier=multiplier,
            )
        )


def test_use_peg_adjustment_is_metadata_only_for_research_calculation() -> None:
    enabled = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(use_peg_adjustment=True), macro_adjustment_multiplier=1)
    )
    disabled = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(use_peg_adjustment=False), macro_adjustment_multiplier=1)
    )

    assert enabled.research_adjusted_fair_value == disabled.research_adjusted_fair_value


def test_compare_valuations_handles_automatic_and_dcf_differences() -> None:
    research = calculate_research_valuation(
        ResearchValuationInputs(
            profile=profile(dcf_fair_value=618.10),
            macro_adjustment_multiplier=0.819,
        )
    )

    comparison = compare_valuations(147.42, research)

    assert comparison.automatic_fair_value == 147.42
    assert comparison.research_fair_value == pytest.approx(599.508)
    assert comparison.automatic_vs_research_difference == pytest.approx(-452.088)
    assert comparison.automatic_vs_research_difference_percent == pytest.approx(
        -75.40983606557377
    )
    assert comparison.research_vs_dcf_difference == pytest.approx(-18.592)
    assert comparison.research_vs_dcf_difference_percent == pytest.approx(
        -3.007927519818815
    )


def test_compare_valuations_handles_missing_automatic_and_dcf_values() -> None:
    research = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(), macro_adjustment_multiplier=1)
    )

    comparison = compare_valuations(None, research)

    assert comparison.automatic_fair_value is None
    assert comparison.automatic_vs_research_difference is None
    assert comparison.automatic_vs_research_difference_percent is None
    assert comparison.dcf_fair_value is None
    assert comparison.research_vs_dcf_difference is None


def test_compare_valuations_handles_automatic_greater_than_research() -> None:
    research = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(valuation_eps=10.0), macro_adjustment_multiplier=1)
    )

    comparison = compare_valuations(500.0, research)

    assert comparison.automatic_vs_research_difference == 100.0
    assert comparison.automatic_vs_research_difference_percent == 25.0


def test_compare_valuations_handles_equal_values() -> None:
    research = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(valuation_eps=10.0), macro_adjustment_multiplier=1)
    )

    comparison = compare_valuations(400.0, research)

    assert comparison.automatic_vs_research_difference == 0.0
    assert comparison.automatic_vs_research_difference_percent == 0.0


def test_compare_valuations_returns_none_percent_when_research_is_zero() -> None:
    research = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(valuation_eps=0.0), macro_adjustment_multiplier=1)
    )

    comparison = compare_valuations(400.0, research)

    assert comparison.automatic_vs_research_difference == 400.0
    assert comparison.automatic_vs_research_difference_percent is None


def test_comparison_percent_uses_absolute_denominator_for_negative_values() -> None:
    comparison = compare_valuations(
        -50.0,
        calculate_research_valuation(
            ResearchValuationInputs(
                profile=profile(valuation_eps=-10.0, target_pe=10.0),
                macro_adjustment_multiplier=1,
            )
        ),
    )

    assert comparison.automatic_vs_research_difference == 50.0
    assert comparison.automatic_vs_research_difference_percent == 50.0


def test_research_dataclasses_are_immutable() -> None:
    result = calculate_research_valuation(
        ResearchValuationInputs(profile=profile(), macro_adjustment_multiplier=1)
    )
    comparison = compare_valuations(800.0, result)

    with pytest.raises(FrozenInstanceError):
        result.research_adjusted_fair_value = 0
    with pytest.raises(FrozenInstanceError):
        comparison.research_fair_value = 0
