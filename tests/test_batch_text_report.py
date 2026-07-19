import pytest

from datetime import date, datetime, timezone
from src.analysis.momentum_reference import MomentumReferenceStatus, PriceField, RsiCrossDirection
from src.analysis.research_valuation import (
    ResearchValuationResult,
    ResearchValuationStatus,
    ValuationComparisonResult,
)
from src.analysis.eps_selection import EPSSelectionResult, EPSSelectionStatus
from src.analysis.fair_value_range import calculate_fair_value_range
from src.analysis.industry_policy import IndustryPolicyTargetPEResult
from tests.test_text_report import analyst_result
from src.config.eps_selection import EPSSelectionMethod
from src.config.industry_policies import TargetPEMode, ValuationStyle as IndustryValuationStyle
from src.config.valuation_profiles import ValuationProfile, ValuationStyle
from src.reports.batch_text_report import format_batch_stock_analysis_report
from src.services.batch_analysis import BatchStockAnalysisResult, StockAnalysisFailure
from src.services.stock_analysis import StockAnalysisWithProfileResult
from tests.test_text_report import (
    _agreement_config,
    _mu_agreement_collection,
    _range_config,
    momentum_result,
    recommendation_v2_result,
    service_result,
    valuation,
)
from src.analysis.valuation_decision import ValuationRecommendation
from src.analysis.valuation_snapshot import build_valuation_snapshot_collection
from src.analysis.agreement_engine import analyze_agreement
from src.analysis.ranking_engine import (
    MomentumSentimentPosition,
    RankingCategory,
    StockRankingEntry,
    StockRankingResult,
    StockRankingStatus,
)


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
    assert "MEDIUM" in report
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


def test_batch_agreement_table_is_present_with_option() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        agreement_result=analyze_agreement(_mu_agreement_collection(), _agreement_config()),
    )

    report = format_batch_stock_analysis_report(
        batch_result((selected,), requested=("LITE",)),
        show_agreement=True,
    )

    assert "MODEL AGREEMENT ANALYSIS" in report
    assert "Core" in report
    assert "Extended" in report
    assert "Overall" in report
    assert "STRONG" in report
    assert "MODERATE" in report
    assert "691.27 USD" in report
    assert "OUTLIER" in report


def test_batch_momentum_table_is_present_with_option() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        momentum_reference=momentum_result(),
    )

    plain = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))
    shown = format_batch_stock_analysis_report(
        batch_result((selected,), requested=("LITE",)),
        show_momentum=True,
    )

    assert "MARKET MOMENTUM REFERENCE" not in plain
    assert "MARKET MOMENTUM REFERENCE" in shown
    assert "Current RSI" in shown
    assert "CROSS_ABOVE" in shown
    assert "+14.29%" in shown


def test_batch_range_table_is_present_with_option() -> None:
    base = service_result()
    collection = _mu_agreement_collection()
    agreement = analyze_agreement(collection, _agreement_config())
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        fair_value_range=calculate_fair_value_range(
            collection,
            agreement,
            848.95,
            _range_config(),
            momentum_result(),
        ),
    )

    plain = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))
    shown = format_batch_stock_analysis_report(
        batch_result((selected,), requested=("LITE",)),
        show_range=True,
    )

    assert "FAIR VALUE RANGE" not in plain
    assert "FAIR VALUE RANGE" in shown
    assert "Conservative" in shown
    assert "618.10 USD" in shown
    assert "691.27 USD" in shown
    assert "SIGNIFICANTLY_OVERVALUED" in shown


def test_batch_recommendation_v2_table_is_present_with_option() -> None:
    base = service_result()
    selected = type(base)(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        recommendation_v2=recommendation_v2_result(),
    )

    plain = format_batch_stock_analysis_report(batch_result((selected,), requested=("LITE",)))
    shown = format_batch_stock_analysis_report(
        batch_result((selected,), requested=("LITE",)),
        show_recommendation_v2=True,
    )

    assert "RECOMMENDATION V2" not in plain
    assert "RECOMMENDATION V2" in shown
    assert "Decision" in shown
    assert "SELL" in shown
    assert "SIGNIFICANTLY_OVERVALUED" in shown
    assert "ALIGNED" in shown


def ranking_result() -> StockRankingResult:
    return StockRankingResult(
        status=StockRankingStatus.COMPLETE,
        entries=(
            StockRankingEntry(
                rank=1,
                symbol="LITE",
                company_name="Lumentum",
                total_score=82.5,
                normalized_score=82.5,
                category=RankingCategory.TOP_OPPORTUNITY,
                eligible=True,
                recommendation_v2=recommendation_v2_result().decision,
                valuation_condition=recommendation_v2_result().valuation_condition,
                evidence_quality=recommendation_v2_result().evidence_quality,
                agreement=recommendation_v2_result().core_agreement,
                momentum=recommendation_v2_result().momentum_condition,
                current_price=80.0,
                base_value=100.0,
                current_vs_base_pct=-20.0,
                current_rsi=55.0,
                rsi_reference_date=date(2026, 7, 2),
                rsi_reference_price=76.0,
                rsi_reference_rsi=49.5,
                rsi_cross_direction=RsiCrossDirection.CROSS_ABOVE,
                current_vs_rsi_reference_amount=4.0,
                current_vs_rsi_reference_pct=5.0,
                momentum_reference_status=MomentumReferenceStatus.COMPLETE,
                momentum_reference_price_field=PriceField.CLOSE,
                momentum_reference_trading_days=10,
                momentum_sentiment_position=MomentumSentimentPosition.ABOVE_NEUTRAL_REFERENCE,
                valuation_score=100.0,
                recommendation_score=80.0,
                agreement_score=100.0,
                evidence_score=100.0,
                momentum_score=60.0,
                penalty=0.0,
                warnings=("sample warning",),
                rationale=("sample rationale",),
            ),
        ),
        top_symbol="LITE",
        top_score=82.5,
        successful_symbols=("LITE",),
        failed_symbols=(),
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_batch_ranking_table_and_details_are_present_with_option() -> None:
    result = BatchStockAnalysisResult(
        requested_symbols=("LITE",),
        successful_results=(service_result(),),
        failures=(),
        ranking_result=ranking_result(),
    )

    plain = format_batch_stock_analysis_report(result)
    shown = format_batch_stock_analysis_report(result, show_ranking=True, show_ranking_details=True)

    assert "MULTI STOCK RANKING" not in plain
    assert "MULTI STOCK RANKING" in shown
    assert "TOP_OPPORTUNITY" in shown
    assert "ELIGIBLE" in shown
    assert "RSI 50 MOMENTUM REFERENCE" in shown
    assert "ABOVE" in shown
    assert "RANKING DETAILS" in shown
    assert "sample rationale" in shown


def test_ranking_csv_output() -> None:
    result = BatchStockAnalysisResult(("LITE",), (service_result(),), (), ranking_result())

    report = format_batch_stock_analysis_report(result, show_ranking=True, ranking_format="csv")

    assert report.splitlines()[0].startswith("rank,symbol,score")
    assert "1,LITE,82.5,TOP_OPPORTUNITY,ELIGIBLE" in report
    assert "2026-07-02" in report
    assert "ABOVE_NEUTRAL_REFERENCE" in report


def test_ranking_json_output() -> None:
    result = BatchStockAnalysisResult(("LITE",), (service_result(),), (), ranking_result())

    report = format_batch_stock_analysis_report(result, show_ranking=True, ranking_format="json")

    assert '"top_symbol": "LITE"' in report
    assert '"category": "TOP_OPPORTUNITY"' in report
    assert '"eligibility": "ELIGIBLE"' in report
    assert '"momentum_reference"' in report
    assert '"sentiment_position": "ABOVE_NEUTRAL_REFERENCE"' in report
