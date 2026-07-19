from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.analysis.eps_growth import EPSGrowthResult, EPSTransition
from src.analysis.eps_selection import EPSSelectionResult, EPSSelectionStatus
from src.analysis.fair_value_range import calculate_fair_value_range
from src.analysis.fair_value import FairValueResult
from src.analysis.momentum_reference import (
    MomentumPricePosition,
    MomentumReferenceStatus,
    PriceField,
    RsiCrossDirection,
    RsiMomentumReference,
)
from src.analysis.recommendation_v2 import (
    EvidenceQuality,
    MomentumCondition,
    RecommendationAlignment,
    RecommendationV2Decision,
    RecommendationV2Result,
    RecommendationV2Status,
    ValuationCondition,
)
from src.analysis.valuation_snapshot import (
    ValuationConfidenceLevel,
    ValuationModelType,
    ValuationSnapshot,
    ValuationSnapshotStatus,
    ValuationValueType,
)
from src.analysis.industry_policy import IndustryPolicyTargetPEResult
from src.analysis.macro_adjustment import MacroAdjustment, YieldTrend
from src.analysis.research_valuation import (
    ResearchValuationResult,
    ResearchValuationStatus,
    ValuationComparisonResult,
)
from src.analysis.stock_valuation import StockValuationResult, StockValuationStatus
from src.analysis.target_pe import (
    AdjustmentCategory,
    TargetPEAdjustment,
    TargetPERecommendation,
)
from src.analysis.valuation_decision import (
    ValuationDecisionResult,
    ValuationRecommendation,
)
from src.analysis.valuation_snapshot import build_valuation_snapshot_collection
from src.analysis.agreement_engine import analyze_agreement
from src.config.agreement_engine import AgreementEngineConfiguration
from src.config.fair_value_range import (
    ConservativeRangeMethod,
    FairValueRangeConfiguration,
    OptimisticRangeMethod,
    RangeBaseMethod,
)
from src.config.valuation_profiles import ValuationProfile, ValuationStyle
from src.config.eps_selection import EPSSelectionMethod
from src.config.industry_policies import TargetPEMode, ValuationStyle as IndustryValuationStyle
from src.reports.text_report import format_stock_analysis_report
from src.services.stock_analysis import (
    StockAnalysisServiceResult,
    StockAnalysisWithProfileResult,
)
from src.yahoo.company import CompanyFundamentals
from src.yahoo.treasury import TreasuryYieldSnapshot


def company(**overrides: object) -> CompanyFundamentals:
    values = {
        "symbol": "LITE",
        "company_name": "Lumentum Holdings Inc.",
        "currency": "USD",
        "current_price": 80.0,
        "previous_close": 79.5,
        "market_cap": 5_000_000_000.0,
        "sector": "Technology",
        "industry": "Communication Equipment",
        "trailing_eps": 5.0,
        "forward_eps": 6.0,
        "trailing_pe": 16.0,
        "forward_pe": 25.0,
        "peg_ratio": 0.95,
        "fifty_two_week_high": 100.0,
        "fifty_two_week_low": 40.0,
        "analyst_target_mean_price": 95.0,
        "analyst_target_high_price": 120.0,
        "analyst_target_low_price": 70.0,
    }
    values.update(overrides)
    return CompanyFundamentals(**values)


def treasury() -> TreasuryYieldSnapshot:
    return TreasuryYieldSnapshot(
        symbol="^TNX",
        yield_date="2026-07-17",
        current_yield_percent=4.6,
        sma_short_percent=4.5,
        sma_long_percent=4.4,
        observation_count=250,
    )


def eps_growth(
    transition: EPSTransition = EPSTransition.POSITIVE_GROWTH,
    growth_percent: float | None = 20.0,
) -> EPSGrowthResult:
    return EPSGrowthResult(
        trailing_eps=5.0,
        forward_eps=6.0,
        growth_percent=growth_percent,
        transition=transition,
        is_growth_rate_usable_for_target_pe=True,
        explanation="EPS explanation",
    )


def target_pe() -> TargetPERecommendation:
    return TargetPERecommendation(
        actual_eps_growth_percent=20.0,
        effective_eps_growth_percent=20.0,
        eps_growth_was_capped=False,
        eps_growth_cap_explanation=None,
        growth_based_pe=20.0,
        raw_target_pe=30.0,
        recommended_target_pe=30.0,
        minimum_target_pe=15.0,
        maximum_target_pe=50.0,
        was_minimum_applied=False,
        was_maximum_applied=False,
        adjustments=(
            TargetPEAdjustment(
                category=AdjustmentCategory.GROWTH,
                label="EPS growth",
                value=20.0,
                explanation="growth",
            ),
            TargetPEAdjustment(
                category=AdjustmentCategory.PEG,
                label="PEG below 1.0",
                value=5.0,
                explanation="peg",
            ),
            TargetPEAdjustment(
                category=AdjustmentCategory.SECTOR,
                label="Preferred growth sector",
                value=5.0,
                explanation="sector",
            ),
        ),
    )


def macro() -> MacroAdjustment:
    return MacroAdjustment(
        current_yield_percent=4.6,
        sma_short_percent=4.5,
        sma_long_percent=4.4,
        trend=YieldTrend.RISING,
        level_discount_percent=9.0,
        trend_adjustment_percent=-10.0,
        total_adjustment_multiplier=0.819,
    )


def fair_value() -> FairValueResult:
    return FairValueResult(
        forward_eps=6.0,
        recommended_target_pe=30.0,
        macro_adjustment_multiplier=0.819,
        base_fair_value=180.0,
        adjusted_fair_value=147.42,
    )


def decision(
    recommendation: ValuationRecommendation = ValuationRecommendation.BUY,
    current_price: float = 80.0,
) -> ValuationDecisionResult:
    return ValuationDecisionResult(
        current_price=current_price,
        adjusted_fair_value=147.42,
        buy_discount_percent=20.0,
        sell_premium_percent=20.0,
        buy_price=117.936,
        sell_price=176.904,
        discount_to_fair_value_percent=45.7332790666124,
        upside_to_fair_value_percent=84.275,
        recommendation=recommendation,
        explanation="decision explanation",
    )


def valuation(
    status: StockValuationStatus = StockValuationStatus.COMPLETE,
    recommendation: ValuationRecommendation = ValuationRecommendation.BUY,
    **overrides: object,
) -> StockValuationResult:
    values = {
        "symbol": "LITE",
        "status": status,
        "current_price": 80.0,
        "trailing_eps": 5.0,
        "forward_eps": 6.0,
        "eps_growth": eps_growth(),
        "target_pe": target_pe(),
        "macro_adjustment": macro(),
        "fair_value": fair_value(),
        "valuation_decision": decision(recommendation=recommendation),
        "explanation": (
            "Valuation completed using usable EPS growth, recommended Target PE, "
            "Treasury macro adjustment, and the configured valuation thresholds."
        ),
    }
    values.update(overrides)
    return StockValuationResult(**values)


def service_result(**overrides: object) -> StockAnalysisServiceResult:
    values = {
        "company": company(),
        "treasury": treasury(),
        "valuation": valuation(),
    }
    values.update(overrides)
    return StockAnalysisServiceResult(**values)


def profile() -> ValuationProfile:
    return ValuationProfile(
        symbol="LITE",
        valuation_style=ValuationStyle.GROWTH,
        valuation_eps=18.30,
        eps_fiscal_year="FY2027",
        target_pe=40.0,
        use_peg_adjustment=True,
        dcf_fair_value=None,
        source_note="research note",
    )


def research_profile_result() -> StockAnalysisWithProfileResult:
    profiled = profile()
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
    return StockAnalysisWithProfileResult(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        profile=profiled,
        research_valuation=research,
        valuation_comparison=comparison,
    )


def eps_selection_result() -> EPSSelectionResult:
    return EPSSelectionResult(
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
        rationale="Use next fiscal-year EPS.",
        selected_vs_legacy_difference_percent=-0.4371584699453552,
        warnings=(),
        calculation_steps=(),
    )


def industry_policy_result() -> IndustryPolicyTargetPEResult:
    return IndustryPolicyTargetPEResult(
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
        enabled_adjustments=(
            "EPS Growth Adjustment",
            "PEG Adjustment",
            "Sector Adjustment",
            "Forward PE Penalty",
        ),
        disabled_adjustments=(),
        rationale="Use capped growth.",
        warnings=(),
        calculation_steps=(),
    )


def analyst_result() -> ValuationSnapshot:
    return ValuationSnapshot(
        symbol="LITE",
        model_type=ValuationModelType.ANALYST_CONSENSUS,
        model_name="Analyst Consensus Model",
        value_type=ValuationValueType.MARKET_EXPECTATION,
        status=ValuationSnapshotStatus.COMPLETE,
        confidence=ValuationConfidenceLevel.MEDIUM,
        raw_fair_value=100.0,
        adjusted_fair_value=100.0,
        selected_fair_value=100.0,
        currency="USD",
        valuation_date=None,
        source_as_of=None,
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        methodology="Weighted Mean / Midpoint",
        rationale="analyst rationale",
        assumptions={
            "valuation_method": "WEIGHTED_MEAN_MIDPOINT",
            "mean_weight": 0.7,
            "midpoint_weight": 0.3,
            "apply_treasury": False,
        },
        metrics={
            "target_mean": 100.0,
            "target_high": 120.0,
            "target_low": 80.0,
            "target_midpoint": 100.0,
            "target_range": 40.0,
            "dispersion_percent": 40.0,
            "dispersion_classification": "MEDIUM",
            "treasury_applied": False,
        },
        warnings=("Yahoo did not provide a reliable analyst-target as-of date.",),
        calculation_steps=(),
    )


def momentum_result() -> RsiMomentumReference:
    return RsiMomentumReference(
        symbol="LITE",
        status=MomentumReferenceStatus.COMPLETE,
        rsi_period=14,
        neutral_level=50.0,
        reference_date=datetime(2026, 6, 18, tzinfo=timezone.utc).date(),
        reference_price=70.0,
        reference_rsi=51.07,
        cross_direction=RsiCrossDirection.CROSS_ABOVE,
        current_date=datetime(2026, 7, 17, tzinfo=timezone.utc).date(),
        current_price=80.0,
        current_rsi=63.42,
        price_field=PriceField.ADJUSTED_CLOSE,
        trading_days_since_reference=21,
        price_change_since_reference=10.0,
        price_change_since_reference_pct=14.2857142857,
        price_position=MomentumPricePosition.ABOVE_RSI50_REFERENCE,
        lookback_start=datetime(2025, 7, 18, tzinfo=timezone.utc).date(),
        lookback_end=datetime(2026, 7, 17, tzinfo=timezone.utc).date(),
        observation_count=250,
        methodology="Wilder RSI(14) neutral-line reference",
        rationale="The latest RSI(14) neutral-line event was an upward crossing.",
        warnings=(),
        calculation_steps=(),
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )


def recommendation_v2_result() -> RecommendationV2Result:
    return RecommendationV2Result(
        symbol="LITE",
        status=RecommendationV2Status.COMPLETE,
        decision=RecommendationV2Decision.SELL,
        valuation_condition=ValuationCondition.SIGNIFICANTLY_OVERVALUED,
        momentum_condition=MomentumCondition.WEAK,
        evidence_quality=EvidenceQuality.HIGH,
        current_price=80.0,
        conservative_value=60.0,
        base_value=65.0,
        optimistic_intrinsic_value=65.0,
        current_vs_base_pct=23.08,
        core_agreement=None,
        extended_agreement=None,
        intrinsic_model_count=2,
        reference_model_count=1,
        current_rsi=41.01,
        rsi_reference_price=90.0,
        current_vs_rsi_reference_pct=-11.11,
        analyst_expectation=100.0,
        analyst_outlier_status=None,
        analyst_confidence=ValuationConfidenceLevel.LOW,
        legacy_recommendation=ValuationRecommendation.SELL,
        alignment=RecommendationAlignment.ALIGNED,
        rationale=("Recommendation V2 is SELL.",),
        warnings=(),
        calculation_steps=(),
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("recommendation", "expected_line"),
    [
        (ValuationRecommendation.BUY, "Decision                : BUY"),
        (ValuationRecommendation.HOLD, "Decision                : HOLD"),
        (ValuationRecommendation.SELL, "Decision                : SELL"),
    ],
)
def test_complete_report_for_buy_hold_and_sell(
    recommendation: ValuationRecommendation,
    expected_line: str,
) -> None:
    report = format_stock_analysis_report(
        service_result(valuation=valuation(recommendation=recommendation))
    )

    assert expected_line in report
    assert "Symbol                  : LITE" in report
    assert "Company                 : Lumentum Holdings Inc." in report
    assert "Current Price           : 80.00 USD" in report
    assert "Trailing EPS            : 5.00" in report
    assert "Forward EPS             : 6.00" in report
    assert "EPS Transition          : POSITIVE_GROWTH" in report
    assert "EPS Growth              : 20.00%" in report
    assert "Actual EPS Growth       : 20.00%" in report
    assert "Effective EPS Growth    : 20.00%" in report
    assert "EPS Growth Capped       : NO" in report
    assert "Recommended Target PE   : 30.00" in report
    assert "Current 10Y Yield       : 4.60%" in report
    assert "Short SMA               : 4.50%" in report
    assert "Long SMA                : 4.40%" in report
    assert "Macro Multiplier        : 0.8190" in report
    assert "Base Fair Value         : 180.00 USD" in report
    assert "Adjusted Fair Value     : 147.42 USD" in report
    assert "Buy Price               : 117.94 USD" in report
    assert "Sell Price              : 176.90 USD" in report
    assert "Valuation completed using usable EPS growth" in report


def test_report_includes_company_optional_data() -> None:
    report = format_stock_analysis_report(service_result())

    assert "Previous Close          : 79.50 USD" in report
    assert "52-Week Range           : 40.00 - 100.00 USD" in report
    assert "Analyst Target Mean     : 95.00 USD" in report
    assert "Market Cap              : 5000000000.00 USD" in report
    assert "Sector                  : Technology" in report
    assert "Industry                : Communication Equipment" in report
    assert "PEG Ratio               : 0.95" in report
    assert "Trailing PE             : 16.00" in report
    assert "Current Forward PE      : 25.00" in report


def test_report_prints_na_for_missing_company_optional_data() -> None:
    missing_company = company(
        company_name=None,
        currency=None,
        previous_close=None,
        market_cap=None,
        sector=None,
        industry=None,
        analyst_target_mean_price=None,
        analyst_target_high_price=None,
        analyst_target_low_price=None,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
    )

    report = format_stock_analysis_report(service_result(company=missing_company))

    assert "Company                 : N/A" in report
    assert "Current Price           : 80.00 N/A" in report
    assert "Previous Close          : N/A" in report
    assert "52-Week Range           : N/A" in report
    assert "Analyst Target Mean     : N/A" in report
    assert "Sector                  : N/A" in report
    assert "Industry                : N/A" in report


def test_incomplete_target_pe_unavailable_report_does_not_crash() -> None:
    incomplete = valuation(
        status=StockValuationStatus.TARGET_PE_UNAVAILABLE,
        target_pe=None,
        macro_adjustment=None,
        fair_value=None,
        valuation_decision=None,
        eps_growth=eps_growth(EPSTransition.LOSS_TO_PROFIT, 150.0),
        explanation="Target PE unavailable explanation.",
    )

    report = format_stock_analysis_report(service_result(valuation=incomplete))

    assert "Status                  : TARGET_PE_UNAVAILABLE" in report
    assert "EPS Transition          : LOSS_TO_PROFIT" in report
    assert "Actual EPS Growth       : N/A" in report
    assert "Effective EPS Growth    : N/A" in report
    assert "EPS Growth Capped       : N/A" in report
    assert "Recommended Target PE   : N/A" in report
    assert "Macro Multiplier        : N/A" in report
    assert "Adjusted Fair Value     : N/A" in report
    assert "Decision                : N/A" in report
    assert "Target PE unavailable explanation." in report


def test_incomplete_fair_value_unavailable_report_does_not_crash() -> None:
    incomplete = valuation(
        status=StockValuationStatus.FAIR_VALUE_UNAVAILABLE,
        fair_value=None,
        valuation_decision=None,
        explanation="Fair value unavailable explanation.",
    )

    report = format_stock_analysis_report(service_result(valuation=incomplete))

    assert "Status                  : FAIR_VALUE_UNAVAILABLE" in report
    assert "Recommended Target PE   : 30.00" in report
    assert "Current 10Y Yield       : 4.60%" in report
    assert "Base Fair Value         : N/A" in report
    assert "Decision                : N/A" in report


def test_decision_not_applicable_report_does_not_crash() -> None:
    not_applicable = valuation(
        status=StockValuationStatus.DECISION_NOT_APPLICABLE,
        valuation_decision=replace(
            decision(ValuationRecommendation.NOT_APPLICABLE),
            buy_price=None,
            sell_price=None,
            discount_to_fair_value_percent=None,
            upside_to_fair_value_percent=None,
        ),
    )

    report = format_stock_analysis_report(service_result(valuation=not_applicable))

    assert "Status                  : DECISION_NOT_APPLICABLE" in report
    assert "Buy Price               : N/A" in report
    assert "Sell Price              : N/A" in report
    assert "Decision                : NOT_APPLICABLE" in report


def test_adjustments_are_included_when_present() -> None:
    report = format_stock_analysis_report(service_result())

    assert "ADJUSTMENTS" in report
    assert "EPS growth              : +20.00" in report
    assert "PEG below 1.0           : +5.00" in report
    assert "Preferred growth sector : +5.00" in report


def test_capped_eps_growth_report_lines() -> None:
    capped_target_pe = replace(
        target_pe(),
        actual_eps_growth_percent=223.92,
        effective_eps_growth_percent=40.0,
        eps_growth_was_capped=True,
        eps_growth_cap_explanation="EPS growth cap: 223.92% -> 40.00%",
        growth_based_pe=40.0,
        raw_target_pe=50.0,
        recommended_target_pe=50.0,
    )
    capped_result = service_result(
        valuation=valuation(
            eps_growth=eps_growth(growth_percent=223.92),
            target_pe=capped_target_pe,
        )
    )

    report = format_stock_analysis_report(capped_result)

    assert "EPS Growth              : 223.92%" in report
    assert "Actual EPS Growth       : 223.92%" in report
    assert "Effective EPS Growth    : 40.00%" in report
    assert "EPS Growth Capped       : YES" in report
    assert "EPS growth cap          : EPS growth cap: 223.92% -> 40.00%" in report


def test_formatter_is_pure_returns_str_and_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    result = service_result()

    first_report = format_stock_analysis_report(result)
    second_report = format_stock_analysis_report(result)

    assert isinstance(first_report, str)
    assert first_report == second_report
    assert result.company.current_price == 80.0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_report_section_order() -> None:
    report = format_stock_analysis_report(service_result())

    sections = [
        "STOCK VALUATION REPORT",
        "MARKET DATA",
        "EARNINGS",
        "TARGET PE",
        "ADJUSTMENTS",
        "TREASURY MACRO",
        "FAIR VALUE",
        "RECOMMENDATION",
        "EXPLANATION",
    ]
    positions = [report.index(section) for section in sections]
    assert positions == sorted(positions)


def test_profiled_report_includes_research_sections_without_recalculation() -> None:
    report = format_stock_analysis_report(research_profile_result())

    assert "RESEARCH VALUATION PROFILE" in report
    assert "Valuation Style         : GROWTH" in report
    assert "EPS Fiscal Year         : FY2027" in report
    assert "Research EPS            : 18.30" in report
    assert "Research Target PE      : 40.00" in report
    assert "PEG Adjustment Enabled  : YES" in report
    assert "Source Note             : research note" in report
    assert "RESEARCH FAIR VALUE" in report
    assert "Research Base Value     : 732.00 USD" in report
    assert "Research Adjusted Value : 599.51 USD" in report
    assert "DCF Reference           : N/A" in report
    assert "MODEL COMPARISON" in report
    assert "Automatic Fair Value    : 147.42 USD" in report
    assert "Research Fair Value     : 599.51 USD" in report
    assert "Automatic - Research    : -452.09 USD" in report
    assert "Difference              : -75.41%" in report


def test_plain_report_does_not_include_research_sections() -> None:
    report = format_stock_analysis_report(service_result())

    assert "RESEARCH VALUATION PROFILE" not in report
    assert "RESEARCH FAIR VALUE" not in report
    assert "MODEL COMPARISON" not in report


def test_selection_report_section_shown_only_when_selection_exists() -> None:
    selected_valuation = valuation(
        fair_value=FairValueResult(
            forward_eps=18.22,
            recommended_target_pe=30.0,
            macro_adjustment_multiplier=0.819,
            base_fair_value=546.6,
            adjusted_fair_value=447.6654,
        ),
        valuation_eps_used=18.22,
        valuation_eps_period="+1y",
        valuation_eps_method="NEXT_YEAR",
    )
    result = service_result(
        valuation=selected_valuation,
    )
    result = StockAnalysisServiceResult(
        company=result.company,
        treasury=result.treasury,
        valuation=result.valuation,
        eps_selection=eps_selection_result(),
    )

    report = format_stock_analysis_report(result)

    assert "VALUATION EPS SELECTION" in report
    assert "Requested Method        : NEXT_YEAR" in report
    assert "Applied Method          : NEXT_YEAR" in report
    assert "Selected Valuation EPS  : 18.22" in report
    assert "Difference vs Forward   : -0.44%" in report
    assert "Valuation EPS Used      : 18.22" in report
    assert "Valuation EPS Method    : NEXT_YEAR" in report
    assert "Forward EPS             : 6.00" in report


def test_selection_report_section_absent_without_selection() -> None:
    report = format_stock_analysis_report(service_result())

    assert "VALUATION EPS SELECTION" not in report
    assert "Valuation EPS Used" not in report


def test_industry_policy_section_shown_only_when_policy_exists() -> None:
    policy = industry_policy_result()
    selected_valuation = valuation(
        fair_value=FairValueResult(
            forward_eps=6.0,
            recommended_target_pe=45.0,
            macro_adjustment_multiplier=0.819,
            base_fair_value=270.0,
            adjusted_fair_value=221.13,
        ),
        target_pe_used=45.0,
        industry_policy=policy,
    )
    result = StockAnalysisServiceResult(
        company=company(),
        treasury=treasury(),
        valuation=selected_valuation,
        industry_policy=policy,
    )

    report = format_stock_analysis_report(result)

    assert "INDUSTRY VALUATION POLICY" in report
    assert "Recommended Target PE   : 30.00" in report
    assert "Policy Target PE        : 45.00" in report
    assert "Target PE Used          : 45.00" in report
    assert "Valuation Style         : GROWTH" in report
    assert "Forward PE Penalty      : ENABLED" in report
    assert "Rationale               : Use capped growth." in report


def test_industry_policy_section_absent_without_policy() -> None:
    report = format_stock_analysis_report(service_result())

    assert "INDUSTRY VALUATION POLICY" not in report
    assert "Policy Target PE" not in report
    assert "Target PE Used" not in report


def test_analyst_consensus_section_present_only_when_enabled() -> None:
    result = StockAnalysisServiceResult(
        company=company(),
        treasury=treasury(),
        valuation=valuation(),
        analyst_consensus=analyst_result(),
    )

    report = format_stock_analysis_report(result)

    assert "ANALYST CONSENSUS MODEL" in report
    assert "Mean Target             : 100.00 USD" in report
    assert "High Target             : 120.00 USD" in report
    assert "Low Target              : 80.00 USD" in report
    assert "Midpoint                : 100.00 USD" in report
    assert "Dispersion              : 40.00%" in report
    assert "Classification          : MEDIUM" in report
    assert "Confidence              : MEDIUM" in report
    assert "Selected Analyst FV     : 100.00 USD" in report
    assert "ANALYST WARNINGS" in report


def test_analyst_consensus_section_absent_without_model() -> None:
    report = format_stock_analysis_report(service_result())

    assert "ANALYST CONSENSUS MODEL" not in report


def test_snapshot_section_is_absent_without_show_snapshots() -> None:
    result = service_result(
        valuation_snapshots=build_valuation_snapshot_collection(service_result())
    )

    report = format_stock_analysis_report(result)

    assert "UNIFIED VALUATION SNAPSHOTS" not in report


def test_snapshot_section_is_present_with_show_snapshots() -> None:
    base = research_profile_result()
    result = StockAnalysisWithProfileResult(
        company=base.company,
        treasury=base.treasury,
        valuation=base.valuation,
        profile=base.profile,
        research_valuation=base.research_valuation,
        valuation_comparison=base.valuation_comparison,
        valuation_snapshots=build_valuation_snapshot_collection(base),
    )

    report = format_stock_analysis_report(result, show_snapshots=True)

    assert "UNIFIED VALUATION SNAPSHOTS" in report
    assert "Model                Selected Value" in report
    assert "AUTOMATIC_PER" in report
    assert "RESEARCH_PER" in report
    assert "147.42 USD" in report
    assert "599.51 USD" in report
    assert "COMPLETE" in report
    assert "MEDIUM" in report
    assert "HIGH" in report
    assert "INTRINSIC_VALUE" in report
    assert "Selected EPS * Applied Target PE * Treasury Multiplier" in report


def test_agreement_section_is_present_only_with_show_agreement() -> None:
    result = service_result(
        agreement_result=analyze_agreement(_mu_agreement_collection(), _agreement_config()),
    )

    plain = format_stock_analysis_report(result)
    shown = format_stock_analysis_report(result, show_agreement=True)

    assert "MODEL AGREEMENT ANALYSIS" not in plain
    assert "MODEL AGREEMENT ANALYSIS" in shown
    assert "Core Intrinsic Agreement: STRONG" in shown
    assert "Extended Agreement      : MODERATE" in shown
    assert "Overall Agreement       : STRONG" in shown
    assert "Intrinsic Cluster Median: 691.27 USD" in shown
    assert "ANALYST_CONSENSUS" in shown
    assert "ABOVE_INTRINSIC" in shown
    assert "OUTLIER" in shown


def test_momentum_section_is_present_only_with_show_momentum() -> None:
    result = service_result(momentum_reference=momentum_result())

    plain = format_stock_analysis_report(result)
    shown = format_stock_analysis_report(result, show_momentum=True)

    assert "MARKET MOMENTUM REFERENCE" not in plain
    assert "MARKET MOMENTUM REFERENCE" in shown
    assert "Current RSI             : 63.42" in shown
    assert "Reference Type          : CROSS_ABOVE" in shown
    assert "RSI 50 Reference Date   : 2026-06-18" in shown
    assert "RSI 50 Reference Price  : 70.00 USD" in shown
    assert "Change vs Reference     : +14.29%" in shown
    assert "Price Field Used        : ADJUSTED_CLOSE" in shown


def test_range_section_is_present_only_with_show_range() -> None:
    collection = _mu_agreement_collection()
    agreement = analyze_agreement(collection, _agreement_config())
    fair_range = calculate_fair_value_range(
        collection,
        agreement,
        848.95,
        _range_config(),
        momentum_result(),
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )
    result = service_result(fair_value_range=fair_range)

    plain = format_stock_analysis_report(result)
    shown = format_stock_analysis_report(result, show_range=True)

    assert "FAIR VALUE RANGE" not in plain
    assert "FAIR VALUE RANGE" in shown
    assert "Conservative Value      : 618.10 USD" in shown
    assert "Base Value              : 691.27 USD" in shown
    assert "Optimistic Intrinsic    : 691.27 USD" in shown
    assert "Market Position         : SIGNIFICANTLY_OVERVALUED" in shown
    assert "Analyst Expectation     : 1428.52 USD" in shown
    assert "Analyst Outlier         : OUTLIER" in shown
    assert "Current RSI             : 63.42" in shown
    assert "RSI 50 Cross Direction  : CROSS_ABOVE" in shown


def test_recommendation_v2_section_is_present_only_with_show_flag() -> None:
    result = service_result(recommendation_v2=recommendation_v2_result())

    plain = format_stock_analysis_report(result)
    shown = format_stock_analysis_report(result, show_recommendation_v2=True)

    assert "RECOMMENDATION V2" not in plain
    assert "RECOMMENDATION V2" in shown
    assert "Decision                : SELL" in shown
    assert "Valuation Condition     : SIGNIFICANTLY_OVERVALUED" in shown
    assert "Momentum Condition      : WEAK" in shown
    assert "Evidence Quality        : HIGH" in shown
    assert "Legacy Recommendation   : SELL" in shown
    assert "Alignment               : ALIGNED" in shown


def _agreement_config() -> AgreementEngineConfiguration:
    return AgreementEngineConfiguration(
        enabled=True,
        strong_threshold_pct=10.0,
        moderate_threshold_pct=20.0,
        weak_threshold_pct=35.0,
        outlier_threshold_pct=50.0,
        extreme_outlier_threshold_pct=80.0,
        minimum_primary_models=2,
        include_reference_in_intrinsic_cluster=True,
        market_expectation_affects_overall_agreement=False,
    )


def _range_config() -> FairValueRangeConfiguration:
    return FairValueRangeConfiguration(
        enabled=True,
        include_reference_values=True,
        include_low_confidence_intrinsic=True,
        exclude_outliers=True,
        base_method=RangeBaseMethod.CONFIDENCE_WEIGHTED_MEDIAN,
        conservative_method=ConservativeRangeMethod.LOWER_SUPPORT,
        optimistic_method=OptimisticRangeMethod.UPPER_INTRINSIC_SUPPORT,
        high_confidence_weight=1.0,
        medium_confidence_weight=0.75,
        low_confidence_weight=0.5,
        unknown_confidence_weight=0.25,
        minimum_intrinsic_models=2,
        reference_value_weight=0.5,
        market_expectation_in_intrinsic_range=False,
        show_market_expectation_separately=True,
        show_momentum_reference_separately=True,
        deep_undervalued_pct=-30.0,
        undervalued_pct=-10.0,
        near_fair_upper_pct=10.0,
        above_fair_pct=20.0,
    )


def _mu_agreement_collection():
    from src.analysis.valuation_snapshot import ValuationSnapshotCollection

    generated_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return ValuationSnapshotCollection(
        "MU",
        (
            _agreement_snapshot(
                ValuationModelType.AUTOMATIC_PER,
                691.27,
                ValuationValueType.INTRINSIC_VALUE,
                ValuationConfidenceLevel.LOW,
            ),
            _agreement_snapshot(
                ValuationModelType.RESEARCH_PER,
                691.27,
                ValuationValueType.INTRINSIC_VALUE,
                ValuationConfidenceLevel.HIGH,
            ),
            _agreement_snapshot(
                ValuationModelType.DCF_REFERENCE,
                618.10,
                ValuationValueType.REFERENCE_VALUE,
                ValuationConfidenceLevel.MEDIUM,
            ),
            _agreement_snapshot(
                ValuationModelType.ANALYST_CONSENSUS,
                1428.52,
                ValuationValueType.MARKET_EXPECTATION,
                ValuationConfidenceLevel.LOW,
            ),
        ),
        generated_at,
    )


def _agreement_snapshot(model_type, value, value_type, confidence):
    return ValuationSnapshot(
        symbol="MU",
        model_type=model_type,
        model_name=model_type.value,
        value_type=value_type,
        status=ValuationSnapshotStatus.COMPLETE,
        confidence=confidence,
        raw_fair_value=value,
        adjusted_fair_value=value,
        selected_fair_value=value,
        currency="USD",
        valuation_date=None,
        source_as_of=None,
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        methodology="method",
        rationale=None,
        assumptions={},
        metrics={},
        warnings=(
            ("Analyst target dispersion is extreme.",)
            if model_type == ValuationModelType.ANALYST_CONSENSUS
            else ()
        ),
        calculation_steps=(),
    )
