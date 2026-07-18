from dataclasses import FrozenInstanceError

import pytest

from src.analysis.eps_selection import EPSSelectionInputs, EPSSelectionStatus, select_eps
from src.config.eps_selection import EPSSelectionMethod, EPSSelectionRule


def rule(method: EPSSelectionMethod, **overrides) -> EPSSelectionRule:
    values = {
        "method": method,
        "current_year_weight": None,
        "next_year_weight": None,
        "manual_eps": None,
        "manual_period_label": None,
        "rationale": "because",
    }
    values.update(overrides)
    return EPSSelectionRule(**values)


def inputs(selection_rule: EPSSelectionRule, **overrides) -> EPSSelectionInputs:
    values = {
        "symbol": "MU",
        "legacy_forward_eps": 150.77,
        "legacy_forward_period_label": "+1y",
        "current_year_eps": 73.37,
        "current_year_period_label": "0y",
        "next_year_eps": 150.47,
        "next_year_period_label": "+1y",
        "rule": selection_rule,
    }
    values.update(overrides)
    return EPSSelectionInputs(**values)


def test_legacy_forward_selected() -> None:
    result = select_eps(inputs(rule(EPSSelectionMethod.LEGACY_FORWARD)))

    assert result.selected_eps == 150.77
    assert result.applied_method == EPSSelectionMethod.LEGACY_FORWARD
    assert result.status == EPSSelectionStatus.COMPLETE


def test_current_year_selected_and_material_difference_warns() -> None:
    result = select_eps(inputs(rule(EPSSelectionMethod.CURRENT_YEAR)))

    assert result.selected_eps == 73.37
    assert result.selected_period_label == "0y"
    assert result.requested_method == EPSSelectionMethod.CURRENT_YEAR
    assert result.applied_method == EPSSelectionMethod.CURRENT_YEAR
    assert result.selected_vs_legacy_difference_percent == pytest.approx(
        -51.336472773098095
    )
    assert "Fair-value EPS differs" in result.warnings[0]


def test_next_year_selected() -> None:
    result = select_eps(inputs(rule(EPSSelectionMethod.NEXT_YEAR)))

    assert result.selected_eps == 150.47
    assert result.selected_period_label == "+1y"


def test_weighted_current_next_selected() -> None:
    result = select_eps(
        inputs(
            rule(
                EPSSelectionMethod.WEIGHTED_CURRENT_NEXT,
                current_year_weight=0.25,
                next_year_weight=0.75,
            )
        )
    )

    assert result.selected_eps == pytest.approx(131.195)
    assert result.selected_period_label == "0.25*0y + 0.75*+1y"
    assert result.calculation_steps[0].name == "weighted_current_next"


@pytest.mark.parametrize("manual_eps", [-1.0, 0.0, 9.5])
def test_manual_selected_without_fallback(manual_eps: float) -> None:
    result = select_eps(
        inputs(
            rule(
                EPSSelectionMethod.MANUAL,
                manual_eps=manual_eps,
                manual_period_label="FY2026",
            )
        )
    )

    assert result.selected_eps == manual_eps
    assert result.selected_period_label == "FY2026"
    assert result.applied_method == EPSSelectionMethod.MANUAL


def test_current_and_next_fallback_to_legacy() -> None:
    current = select_eps(
        inputs(rule(EPSSelectionMethod.CURRENT_YEAR), current_year_eps=None)
    )
    next_year = select_eps(
        inputs(rule(EPSSelectionMethod.NEXT_YEAR), next_year_eps=None)
    )

    assert current.status == EPSSelectionStatus.FALLBACK_USED
    assert current.applied_method == EPSSelectionMethod.LEGACY_FORWARD
    assert current.fallback_reason == "Current-year estimate unavailable; used Yahoo forwardEps."
    assert next_year.status == EPSSelectionStatus.FALLBACK_USED
    assert next_year.applied_method == EPSSelectionMethod.LEGACY_FORWARD


def test_weighted_fallbacks_are_visible() -> None:
    weighted = rule(
        EPSSelectionMethod.WEIGHTED_CURRENT_NEXT,
        current_year_weight=0.5,
        next_year_weight=0.5,
    )

    current_only = select_eps(inputs(weighted, next_year_eps=None))
    next_only = select_eps(inputs(weighted, current_year_eps=None))
    legacy = select_eps(inputs(weighted, current_year_eps=None, next_year_eps=None))

    assert current_only.applied_method == EPSSelectionMethod.CURRENT_YEAR
    assert current_only.status == EPSSelectionStatus.FALLBACK_USED
    assert next_only.applied_method == EPSSelectionMethod.NEXT_YEAR
    assert legacy.applied_method == EPSSelectionMethod.LEGACY_FORWARD


def test_complete_unavailability() -> None:
    result = select_eps(
        inputs(
            rule(EPSSelectionMethod.LEGACY_FORWARD),
            legacy_forward_eps=None,
            current_year_eps=None,
            next_year_eps=None,
        )
    )

    assert result.status == EPSSelectionStatus.UNAVAILABLE
    assert result.selected_eps is None
    assert result.applied_method is None


def test_result_immutable_and_inputs_not_mutated() -> None:
    source_inputs = inputs(rule(EPSSelectionMethod.CURRENT_YEAR))
    result = select_eps(source_inputs)

    assert source_inputs.current_year_eps == 73.37
    with pytest.raises(FrozenInstanceError):
        result.selected_eps = 1.0
