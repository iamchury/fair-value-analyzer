from dataclasses import replace

import pytest

from src.analysis.eps_growth import EPSGrowthResult, EPSTransition
from src.analysis.eps_selection import EPSSelectionResult, EPSSelectionStatus
from src.analysis.fair_value import FairValueResult
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
