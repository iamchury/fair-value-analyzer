from datetime import datetime, timezone

from src.analysis.eps_source_inspector import (
    EPSAmbiguityLevel,
    EPSBasisType,
    EPSInspectionResult,
    EPSInspectionStatus,
    EPSPeriodType,
)
from src.reports.eps_inspection_report import format_eps_inspection_report
from src.services.eps_inspection import EPSInspectionServiceResult
from src.yahoo.company import (
    CompanyFundamentals,
    EPSRawFieldSource,
    YahooEPSRawSnapshot,
)


STAMP = datetime(2026, 7, 18, tzinfo=timezone.utc)


def source() -> EPSRawFieldSource:
    return EPSRawFieldSource(
        "forward_eps",
        "yfinance.Ticker.info",
        "forwardEps",
        10.0,
        None,
        STAMP,
        None,
    )


def service_result(warnings=("GAAP/non-GAAP basis is unavailable.",)):
    company = CompanyFundamentals(
        symbol="LITE",
        company_name="Lumentum",
        currency="USD",
        current_price=80.0,
        previous_close=None,
        market_cap=None,
        sector=None,
        industry=None,
        trailing_eps=8.0,
        forward_eps=10.0,
        trailing_pe=None,
        forward_pe=None,
        peg_ratio=None,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        analyst_target_mean_price=None,
        analyst_target_high_price=None,
        analyst_target_low_price=None,
    )
    snapshot = YahooEPSRawSnapshot(
        symbol="LITE",
        trailing_eps=8.0,
        forward_eps=10.0,
        trailing_pe=12.0,
        forward_pe=14.0,
        peg_ratio=1.2,
        earnings_growth=None,
        quarterly_earnings_growth=None,
        most_recent_quarter=None,
        last_fiscal_year_end=None,
        next_fiscal_year_end=None,
        last_split_date=None,
        shares_outstanding=None,
        implied_shares_outstanding=None,
        price_to_book=None,
        current_quarter_estimate=None,
        next_quarter_estimate=None,
        current_year_estimate=None,
        next_year_estimate=None,
        source_timestamp=STAMP,
        raw_field_sources=(source(),),
        warnings=(),
    )
    inspection = EPSInspectionResult(
        symbol="LITE",
        status=EPSInspectionStatus.PARTIAL,
        selected_forward_eps=10.0,
        selected_forward_eps_raw_field='yfinance.Ticker.info["forwardEps"]',
        inferred_period_type=EPSPeriodType.UNKNOWN,
        inferred_period_label=None,
        basis_type=EPSBasisType.UNKNOWN,
        trailing_eps=8.0,
        current_year_eps_estimate=None,
        next_year_eps_estimate=None,
        current_quarter_eps_estimate=None,
        next_quarter_eps_estimate=None,
        last_fiscal_year_end=None,
        next_fiscal_year_end=None,
        most_recent_quarter=None,
        source_timestamp=STAMP,
        forward_eps_matches_current_year=None,
        forward_eps_current_year_difference_percent=None,
        forward_eps_matches_next_year=None,
        forward_eps_next_year_difference_percent=None,
        match_tolerance_percent=1.0,
        ambiguity_level=EPSAmbiguityLevel.HIGH,
        warnings=tuple(warnings),
        calculation_steps=(),
        raw_field_sources=(source(),),
    )
    return EPSInspectionServiceResult(company, snapshot, inspection)


def test_eps_inspection_report_displays_sections_and_values() -> None:
    report = format_eps_inspection_report(service_result())

    assert "EPS SOURCE INSPECTION" in report
    assert "Symbol                  : LITE" in report
    assert "Status                  : PARTIAL" in report
    assert "Ambiguity               : HIGH" in report
    assert "Yahoo trailingEps       : 8.00" in report
    assert "Yahoo forwardEps        : 10.00" in report
    assert "Inferred Forward Period : UNKNOWN" in report
    assert "Accounting Basis        : UNKNOWN" in report
    assert "Match Current Year      : N/A" in report
    assert "Match Tolerance         : 1.00%" in report
    assert 'Forward EPS             : yfinance.Ticker.info["forwardEps"]' in report
    assert "- GAAP/non-GAAP basis is unavailable." in report


def test_report_prints_none_when_no_warnings_and_is_deterministic() -> None:
    result = service_result(warnings=())

    first = format_eps_inspection_report(result)
    second = format_eps_inspection_report(result)

    assert first == second
    assert "WARNINGS" in first
    assert "None" in first
