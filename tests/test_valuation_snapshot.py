from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone

import pytest

from src.analysis.research_valuation import (
    ResearchValuationResult,
    ResearchValuationStatus,
    ValuationComparisonResult,
)
from src.analysis.stock_valuation import StockValuationStatus
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotCollection,
    ValuationSnapshotStatus,
    ValuationSnapshotStep,
    ValuationValueType,
    build_valuation_snapshot_collection,
    create_automatic_per_snapshot,
    create_dcf_reference_snapshot,
    create_research_per_snapshot,
    valuation_snapshot_collection_to_dict,
    valuation_snapshot_to_dict,
)
from src.config.valuation_profiles import ValuationProfile, ValuationStyle
from src.services.stock_analysis import StockAnalysisWithProfileResult
from tests.test_text_report import (
    analyst_result,
    company,
    fair_value,
    research_profile_result,
    service_result,
    valuation,
)


GENERATED_AT = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def snapshot(**overrides: object) -> ValuationSnapshot:
    values = {
        "symbol": " lite ",
        "model_type": ValuationModelType.AUTOMATIC_PER,
        "model_name": "Automatic PER Model",
        "value_type": ValuationValueType.INTRINSIC_VALUE,
        "status": ValuationSnapshotStatus.COMPLETE,
        "confidence": ValuationConfidenceLevel.MEDIUM,
        "raw_fair_value": 180.0,
        "adjusted_fair_value": 147.42,
        "selected_fair_value": 147.42,
        "currency": "USD",
        "valuation_date": date(2026, 7, 18),
        "source_as_of": date(2026, 7, 17),
        "generated_at": GENERATED_AT,
        "methodology": "method",
        "rationale": "rationale",
        "assumptions": {"outer": {"items": [1, 2]}},
        "metrics": {"metric": [3, 4]},
        "warnings": ["warning"],
        "calculation_steps": (
            ValuationSnapshotStep(
                name="step",
                input_values={"x": [1]},
                formula="x",
                result=1.0,
                explanation="copy",
            ),
        ),
    }
    values.update(overrides)
    return ValuationSnapshot(**values)


def test_valid_snapshot_is_immutable_and_normalizes_metadata() -> None:
    original_assumptions = {"outer": {"items": [1, 2]}}
    result = snapshot(assumptions=original_assumptions)

    assert result.symbol == "LITE"
    assert result.warnings == ("warning",)
    assert result.assumptions["outer"]["items"] == (1, 2)
    assert result.metrics["metric"] == (3, 4)
    original_assumptions["outer"]["items"].append(99)
    assert result.assumptions["outer"]["items"] == (1, 2)
    with pytest.raises(TypeError):
        result.assumptions["new"] = "blocked"
    with pytest.raises(TypeError):
        result.assumptions["outer"]["new"] = "blocked"
    with pytest.raises(FrozenInstanceError):
        result.symbol = "MU"


@pytest.mark.parametrize(
    "status",
    [
        ValuationSnapshotStatus.COMPLETE,
        ValuationSnapshotStatus.PARTIAL,
        ValuationSnapshotStatus.UNAVAILABLE,
        ValuationSnapshotStatus.ERROR,
    ],
)
def test_snapshot_supports_all_statuses(status: ValuationSnapshotStatus) -> None:
    result = snapshot(status=status)

    assert result.status == status


@pytest.mark.parametrize("field", ["raw_fair_value", "adjusted_fair_value", "selected_fair_value"])
@pytest.mark.parametrize("bad_value", [0.0, -1.0, True, float("nan"), float("inf"), float("-inf")])
def test_snapshot_rejects_invalid_fair_values(field: str, bad_value: object) -> None:
    with pytest.raises(ValueError):
        snapshot(**{field: bad_value})


def test_snapshot_rejects_empty_symbol_and_naive_generated_at() -> None:
    with pytest.raises(ValueError, match="empty"):
        snapshot(symbol=" ")
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(generated_at=datetime(2026, 7, 18, 12, 0))


def test_unknown_model_type_is_supported() -> None:
    result = snapshot(
        model_type=ValuationModelType.UNKNOWN,
        value_type=ValuationValueType.UNKNOWN,
    )

    assert result.model_type == ValuationModelType.UNKNOWN


def test_automatic_adapter_copies_existing_values_without_recalculation() -> None:
    result = service_result()
    adapted = create_automatic_per_snapshot(result, GENERATED_AT)

    assert adapted.model_type == ValuationModelType.AUTOMATIC_PER
    assert adapted.raw_fair_value == 180.0
    assert adapted.adjusted_fair_value == 147.42
    assert adapted.selected_fair_value == 147.42
    assert adapted.assumptions["valuation_eps"] == 6.0
    assert adapted.assumptions["original_target_pe"] == 30.0
    assert adapted.assumptions["applied_target_pe"] == 30.0
    assert adapted.assumptions["treasury_multiplier"] == 0.819
    assert adapted.metrics["current_price"] == 80.0
    assert adapted.metrics["eps_growth_percent"] == 20.0
    assert adapted.metrics["effective_eps_growth_percent"] == 20.0
    assert adapted.metrics["current_forward_pe"] == 25.0
    assert adapted.status == ValuationSnapshotStatus.COMPLETE
    assert adapted.confidence == ValuationConfidenceLevel.MEDIUM
    assert result.valuation.fair_value.adjusted_fair_value == 147.42


def test_automatic_adapter_preserves_warnings_and_partial_unavailable_states() -> None:
    with_warning = service_result(eps_selection=replace(_eps_selection_warning(), warnings=("source warning",)))
    warned = create_automatic_per_snapshot(with_warning, GENERATED_AT)
    assert warned.warnings == ("source warning",)
    assert warned.confidence == ValuationConfidenceLevel.LOW

    partial = service_result(
        valuation=valuation(status=StockValuationStatus.DECISION_NOT_APPLICABLE)
    )
    assert create_automatic_per_snapshot(partial, GENERATED_AT).status == (
        ValuationSnapshotStatus.PARTIAL
    )

    unavailable = service_result(
        valuation=valuation(
            status=StockValuationStatus.FAIR_VALUE_UNAVAILABLE,
            fair_value=None,
            valuation_decision=None,
        )
    )
    unavailable_snapshot = create_automatic_per_snapshot(unavailable, GENERATED_AT)
    assert unavailable_snapshot.status == ValuationSnapshotStatus.UNAVAILABLE
    assert unavailable_snapshot.confidence == ValuationConfidenceLevel.UNKNOWN


def test_research_adapter_copies_profile_and_comparison_values() -> None:
    result = research_profile_result()
    adapted = create_research_per_snapshot(result, GENERATED_AT)

    assert adapted.model_type == ValuationModelType.RESEARCH_PER
    assert adapted.raw_fair_value == 732.0
    assert adapted.adjusted_fair_value == 599.508
    assert adapted.selected_fair_value == 599.508
    assert adapted.assumptions["valuation_style"] == "GROWTH"
    assert adapted.assumptions["research_eps"] == 18.30
    assert adapted.assumptions["eps_fiscal_year"] == "FY2027"
    assert adapted.assumptions["research_target_pe"] == 40.0
    assert adapted.assumptions["source_note"] == "research note"
    assert adapted.metrics["difference_vs_automatic_percent"] == pytest.approx(
        -75.41069277039841
    )
    assert adapted.status == ValuationSnapshotStatus.COMPLETE
    assert adapted.confidence == ValuationConfidenceLevel.HIGH


def test_research_adapter_handles_missing_supporting_metadata_and_absence() -> None:
    base = research_profile_result()
    missing_note_profile = replace(base.profile, source_note=None)
    missing_note_research = replace(base.research_valuation, profile=missing_note_profile)
    partial_result = StockAnalysisWithProfileResult(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        profile=missing_note_profile,
        research_valuation=missing_note_research,
        valuation_comparison=base.valuation_comparison,
    )
    partial = create_research_per_snapshot(partial_result, GENERATED_AT)
    assert partial.status == ValuationSnapshotStatus.PARTIAL
    assert partial.confidence == ValuationConfidenceLevel.LOW

    unavailable = create_research_per_snapshot(service_result(), GENERATED_AT)
    assert unavailable.status == ValuationSnapshotStatus.UNAVAILABLE
    assert unavailable.confidence == ValuationConfidenceLevel.UNKNOWN


def test_dcf_reference_adapter_copies_reference_and_warns() -> None:
    result = _profile_result_with_dcf(618.10, "DCF source")

    adapted = create_dcf_reference_snapshot(result, GENERATED_AT)

    assert adapted.model_type == ValuationModelType.DCF_REFERENCE
    assert adapted.value_type == ValuationValueType.REFERENCE_VALUE
    assert adapted.raw_fair_value == 618.10
    assert adapted.adjusted_fair_value == 618.10
    assert adapted.selected_fair_value == 618.10
    assert adapted.status == ValuationSnapshotStatus.COMPLETE
    assert adapted.confidence == ValuationConfidenceLevel.MEDIUM
    assert "not a DCF calculation performed" in adapted.warnings[0]


def test_dcf_reference_adapter_handles_partial_missing_and_invalid_values() -> None:
    partial = create_dcf_reference_snapshot(_profile_result_with_dcf(618.10, None), GENERATED_AT)
    assert partial.status == ValuationSnapshotStatus.PARTIAL
    assert partial.confidence == ValuationConfidenceLevel.LOW

    missing = create_dcf_reference_snapshot(research_profile_result(), GENERATED_AT)
    assert missing.status == ValuationSnapshotStatus.UNAVAILABLE

    for bad_value in (0.0, -1.0):
        invalid = create_dcf_reference_snapshot(
            _profile_result_with_dcf(bad_value, "source"),
            GENERATED_AT,
        )
        assert invalid.status == ValuationSnapshotStatus.UNAVAILABLE
    with pytest.raises(ValueError):
        create_dcf_reference_snapshot(_profile_result_with_dcf(True, "source"), GENERATED_AT)


def test_collection_order_lookup_and_validation() -> None:
    automatic = snapshot(model_type=ValuationModelType.AUTOMATIC_PER)
    research = snapshot(model_type=ValuationModelType.RESEARCH_PER)
    collection = ValuationSnapshotCollection(
        symbol="lite",
        snapshots=(research, automatic),
        generated_at=GENERATED_AT,
    )

    assert collection.symbol == "LITE"
    assert [item.model_type for item in collection.snapshots] == [
        ValuationModelType.AUTOMATIC_PER,
        ValuationModelType.RESEARCH_PER,
    ]
    assert collection.get(ValuationModelType.RESEARCH_PER) is research
    assert collection.get(ValuationModelType.DCF_REFERENCE) is None
    with pytest.raises(FrozenInstanceError):
        collection.snapshots = ()
    with pytest.raises(ValueError, match="duplicate"):
        ValuationSnapshotCollection("LITE", (automatic, automatic), GENERATED_AT)
    with pytest.raises(ValueError, match="collection symbol"):
        ValuationSnapshotCollection(
            "LITE",
            (snapshot(symbol="MU"),),
            GENERATED_AT,
        )


def test_collection_builder_omits_unavailable_optional_models() -> None:
    automatic_only = build_valuation_snapshot_collection(service_result(), GENERATED_AT)
    assert [item.model_type for item in automatic_only.snapshots] == [
        ValuationModelType.AUTOMATIC_PER
    ]

    with_research = build_valuation_snapshot_collection(research_profile_result(), GENERATED_AT)
    assert [item.model_type for item in with_research.snapshots] == [
        ValuationModelType.AUTOMATIC_PER,
        ValuationModelType.RESEARCH_PER,
    ]

    with_dcf = build_valuation_snapshot_collection(
        _profile_result_with_dcf(618.10, "DCF source"),
        GENERATED_AT,
    )
    assert [item.model_type for item in with_dcf.snapshots] == [
        ValuationModelType.AUTOMATIC_PER,
        ValuationModelType.RESEARCH_PER,
        ValuationModelType.DCF_REFERENCE,
    ]

    with_analyst = build_valuation_snapshot_collection(
        service_result(analyst_consensus=analyst_result()),
        GENERATED_AT,
    )
    assert [item.model_type for item in with_analyst.snapshots] == [
        ValuationModelType.AUTOMATIC_PER,
        ValuationModelType.ANALYST_CONSENSUS,
    ]


def test_snapshot_serialization_is_plain_and_deterministic() -> None:
    result = snapshot()
    serialized = valuation_snapshot_to_dict(result)

    assert list(serialized) == [
        "symbol",
        "model_type",
        "model_name",
        "value_type",
        "status",
        "confidence",
        "raw_fair_value",
        "adjusted_fair_value",
        "selected_fair_value",
        "currency",
        "valuation_date",
        "source_as_of",
        "generated_at",
        "methodology",
        "rationale",
        "assumptions",
        "metrics",
        "warnings",
        "calculation_steps",
    ]
    assert serialized["model_type"] == "AUTOMATIC_PER"
    assert serialized["valuation_date"] == "2026-07-18"
    assert serialized["generated_at"] == "2026-07-18T12:00:00+00:00"
    assert serialized["assumptions"] == {"outer": {"items": [1, 2]}}
    assert serialized["warnings"] == ["warning"]

    collection = ValuationSnapshotCollection("LITE", (result,), GENERATED_AT)
    collection_data = valuation_snapshot_collection_to_dict(collection)
    assert collection_data["snapshots"][0]["selected_fair_value"] == 147.42
    assert result.assumptions["outer"]["items"] == (1, 2)


def _profile_result_with_dcf(
    dcf_fair_value: object,
    source_note: str | None,
) -> StockAnalysisWithProfileResult:
    base = research_profile_result()
    profile = ValuationProfile(
        symbol="LITE",
        valuation_style=ValuationStyle.GROWTH,
        valuation_eps=18.30,
        eps_fiscal_year="FY2027",
        target_pe=40.0,
        use_peg_adjustment=True,
        dcf_fair_value=dcf_fair_value,
        source_note=source_note,
    )
    research = ResearchValuationResult(
        profile=profile,
        status=ResearchValuationStatus.COMPLETE,
        macro_adjustment_multiplier=0.819,
        research_base_fair_value=732.0,
        research_adjusted_fair_value=599.508,
        dcf_fair_value=dcf_fair_value,
    )
    comparison = ValuationComparisonResult(
        automatic_fair_value=147.42,
        research_fair_value=599.508,
        dcf_fair_value=dcf_fair_value,
        automatic_vs_research_difference=-452.088,
        automatic_vs_research_difference_percent=-75.41069277039841,
        research_vs_dcf_difference=None,
        research_vs_dcf_difference_percent=None,
    )
    return StockAnalysisWithProfileResult(
        company=company(),
        treasury=base.treasury,
        valuation=base.valuation,
        profile=profile,
        research_valuation=research,
        valuation_comparison=comparison,
    )


def _eps_selection_warning():
    from tests.test_text_report import eps_selection_result

    return eps_selection_result()
