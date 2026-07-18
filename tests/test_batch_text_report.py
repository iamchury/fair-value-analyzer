import pytest

from src.analysis.research_valuation import (
    ResearchValuationResult,
    ResearchValuationStatus,
    ValuationComparisonResult,
)
from src.analysis.eps_selection import EPSSelectionResult, EPSSelectionStatus
from src.analysis.industry_policy import IndustryPolicyTargetPEResult
from tests.test_text_report import analyst_result
from src.config.eps_selection import EPSSelectionMethod
from src.config.industry_policies import TargetPEMode, ValuationStyle as IndustryValuationStyle
from src.config.valuation_profiles import ValuationProfile, ValuationStyle
from src.reports.batch_text_report import format_batch_stock_analysis_report
from src.services.batch_analysis import BatchStockAnalysisResult, StockAnalysisFailure
from src.services.stock_analysis import StockAnalysisWithProfileResult
from tests.test_text_report import service_result, valuation
from src.analysis.valuation_decision import ValuationRecommendation
from src.analysis.valuation_snapshot import build_valuation_snapshot_collection


def batch_result(successes=(), failures=(), requested=("LITE", "MU")):
    return BatchStockAnalysisResult(
        requested_symbols=tuple(requested),
        successful_results=tuple(successes),
        failures=tuple(failures),
    )


def test_all_success_report_counts_and_columns() -> None:
    lite = service_result()
    mu = service_result(valuation=valuation(recommendation=ValuationRecommendation.HOLD))
    mu = type(mu)(company=mu.company, treasury=mu.treasury, valuation=mu.valuation)
    result = batch_result((lite, mu), requested=("LITE", "MU"))

    report = format_batch_stock_analysis_report(result)

    assert "BATCH STOCK VALUATION REPORT" in report
    assert "Requested               : 2" in report
    assert "Successful              : 2" in report
    assert "Failed                  : 0" in report
    assert "Symbol" in report
    assert "Price" in report
    assert "Fair Value" in report
    assert "Buy Price" in report
    assert "Sell Price" in report
    assert "Decision" in report
    assert "Status" in report
    assert "LITE" in report
    assert "80.00 USD" in report
    assert "147.42 USD" in report
    assert "117.94 USD" in report
    assert "176.90 USD" in report
    assert "COMPLETE" in report
    assert "FAILURES" not in report


def test_partial_failure_report_preserves_input_order_and_details() -> None:
    lite = service_result()
    failure = StockAnalysisFailure("MU", "RuntimeError", "Yahoo request failed")
    result = batch_result((lite,), (failure,), requested=("LITE", "MU"))

    report = format_batch_stock_analysis_report(result)

    assert report.index("LITE") < report.index("MU")
    assert "Failed                  : 1" in report
    assert "MU" in report
    assert "ERROR" in report
    assert "FAILURES" in report
    assert "RuntimeError: Yahoo request failed" in report


def test_all_failure_report() -> None:
    result = batch_result(
        failures=(
            StockAnalysisFailure("LITE", "RuntimeError", "failed 1"),
            StockAnalysisFailure("MU", "ValueError", "failed 2"),
        ),
        requested=("LITE", "MU"),
    )

    report = format_batch_stock_analysis_report(result)

    assert "Successful              : 0" in report
    assert "Failed                  : 2" in report
    assert "LITE" in report
    assert "MU" in report
    assert "RuntimeError: failed 1" in report
    assert "ValueError: failed 2" in report


def test_unavailable_values_print_na() -> None:
    incomplete = service_result(
        valuation=valuation(fair_value=None, valuation_decision=None)
    )

    report = format_batch_stock_analysis_report(batch_result((incomplete,), requested=("LITE",)))

    assert "N/A" in report


def test_formatter_is_pure_deterministic_and_silent(capsys: pytest.CaptureFixture[str]) -> None:
    result = batch_result((service_result(),), requested=("LITE",))

    first = format_batch_stock_analysis_report(result)
    second = format_batch_stock_analysis_report(result)

    assert isinstance(first, str)
    assert first == second
    assert result.success_count == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_profiled_batch_report_includes_research_comparison_rows() -> None:
    profiled = ValuationProfile(
        symbol="LITE",
        valuation_style=ValuationStyle.GROWTH,
        valuation_eps=18.30,
        eps_fiscal_year="FY2027",
        target_pe=40.0,
        use_peg_adjustment=True,
        dcf_fair_value=None,
        source_note="research note",
    )
    research = ResearchValuationResult(
        profile=profiled,
        status=ResearchValuationStatus.COMPLETE,
        macro_adjustment_multiplier=0.819,
        research_base_fair_value=732.0,
        research_adjusted_fair_value=599.508,
        dcf_fair_value=None,
    )
    comparison = ValuationComparisonResult(
        automatic_fair_value=147.42,
        research_fair_value=599.508,
        dcf_fair_value=None,
        automatic_vs_research_difference=-452.088,
        automatic_vs_research_difference_percent=-75.41069277039841,
        research_vs_dcf_difference=None,
        research_vs_dcf_difference_percent=None,
    )
    base = service_result()
    result = batch_result(
        (
            StockAnalysisWithProfileResult(
                company=base.company,
                treasury=base.treasury,
                valuation=base.valuation,
                profile=profiled,
                research_valuation=research,
                valuation_comparison=comparison,
            ),
        ),
        requested=("LITE",),
    )

    report = format_batch_stock_analysis_report(result)

    assert "RESEARCH COMPARISON" in report
    assert "Auto FV" in report
    assert "Research FV" in report
    assert "147.42 USD" in report
    assert "599.51 USD" in report
    assert "GROWTH" in report
    assert "YES" in report


def test_batch_report_includes_eps_selection_table_when_present() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        eps_selection=EPSSelectionResult(
            symbol="LITE",
            requested_method=EPSSelectionMethod.NEXT_YEAR,
            applied_method=EPSSelectionMethod.NEXT_YEAR,
            status=EPSSelectionStatus.COMPLETE,
            selected_eps=18.22,
            selected_period_label="+1y",
            legacy_forward_eps=18.30,
            current_year_eps=8.23,
            next_year_eps=18.22,
            current_year_weight=None,
            next_year_weight=None,
            fallback_reason=None,
            rationale="Use next EPS.",
            selected_vs_legacy_difference_percent=-0.44,
            warnings=(),
            calculation_steps=(),
        ),
    )

    report = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))

    assert "EPS SELECTION" in report
    assert "Requested" in report
    assert "NEXT_YEAR" in report
    assert "18.22" in report
    assert "+1y" in report
    assert "COMPLETE" in report


def test_batch_report_includes_industry_policy_table_when_present() -> None:
    base = service_result()
    policy = IndustryPolicyTargetPEResult(
        symbol="LITE",
        policy_applied=True,
        policy_name="GROWTH",
        valuation_style=IndustryValuationStyle.GROWTH,
        target_pe_mode=TargetPEMode.CALCULATED,
        original_target_pe=50.0,
        policy_target_pe=45.0,
        minimum_target_pe=25.0,
        maximum_target_pe=45.0,
        fixed_target_pe=None,
        enabled_adjustments=("EPS Growth Adjustment",),
        disabled_adjustments=("Sector Adjustment",),
        rationale="growth",
        warnings=(),
        calculation_steps=(),
    )
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        industry_policy=policy,
    )

    report = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))

    assert "INDUSTRY POLICY" in report
    assert "Original PE" in report
    assert "Policy PE" in report
    assert "LITE" in report
    assert "GROWTH" in report
    assert "50.00" in report
    assert "45.00" in report


def test_batch_report_includes_analyst_consensus_table_when_present() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        analyst_consensus=analyst_result(),
    )

    report = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))

    assert "ANALYST CONSENSUS" in report
    assert "Mean Target" in report
    assert "Analyst FV" in report
    assert "MODERATE" in report
    assert "COMPLETE" in report


def test_batch_snapshot_table_is_absent_without_option() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        valuation_snapshots=build_valuation_snapshot_collection(base),
    )

    report = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))

    assert "VALUATION SNAPSHOTS" not in report


def test_batch_snapshot_table_is_present_with_option() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        valuation_snapshots=build_valuation_snapshot_collection(base),
    )

    report = format_batch_stock_analysis_report(
        batch_result((selected,), requested=("LITE",)),
        show_snapshots=True,
    )

    assert "VALUATION SNAPSHOTS" in report
    assert "AUTOMATIC_PER" in report
    assert "147.42 USD" in report
    assert "COMPLETE" in report
    assert "MEDIUM" in report
