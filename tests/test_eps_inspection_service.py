from datetime import datetime, timezone

import pytest

import src.services.eps_inspection as eps_service
from src.analysis.eps_source_inspector import EPSInspectionStatus
from src.services.eps_inspection import (
    EPSInspectionServiceError,
    EPSInspectionServiceResult,
    inspect_stock_eps,
)
from src.yahoo.company import (
    CompanyFundamentals,
    CompanyFundamentalsWithEPSRawSnapshot,
    EPSRawFieldSource,
    YahooEPSEstimate,
    YahooEPSRawSnapshot,
)


STAMP = datetime(2026, 7, 18, tzinfo=timezone.utc)


def company() -> CompanyFundamentals:
    return CompanyFundamentals(
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


def estimate(label: str, value: float | None) -> YahooEPSEstimate:
    return YahooEPSEstimate(label, value, None, None, None, 3)


def snapshot(forward_eps: float | None = 10.0) -> YahooEPSRawSnapshot:
    return YahooEPSRawSnapshot(
        symbol="LITE",
        trailing_eps=8.0,
        forward_eps=forward_eps,
        trailing_pe=None,
        forward_pe=None,
        peg_ratio=None,
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
        current_year_estimate=estimate("0y", 10.0),
        next_year_estimate=estimate("+1y", 12.0),
        source_timestamp=STAMP,
        raw_field_sources=(
            EPSRawFieldSource(
                "forward_eps",
                "yfinance.Ticker.info",
                "forwardEps",
                forward_eps,
                None,
                STAMP,
                None,
            ),
        ),
        warnings=(),
    )


def test_inspect_stock_eps_downloads_company_once_and_runs_no_valuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_download(symbol: str):
        calls.append(("download", symbol))
        return CompanyFundamentalsWithEPSRawSnapshot(company(), snapshot())

    monkeypatch.setattr(
        eps_service,
        "download_company_fundamentals_with_eps_snapshot",
        fake_download,
    )

    result = inspect_stock_eps(" lite ")

    assert isinstance(result, EPSInspectionServiceResult)
    assert calls == [("download", "LITE")]
    assert result.company.symbol == "LITE"
    assert result.inspection.status == EPSInspectionStatus.COMPLETE


def test_inspect_stock_eps_can_return_partial_and_unavailable_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        eps_service,
        "download_company_fundamentals_with_eps_snapshot",
        lambda symbol: CompanyFundamentalsWithEPSRawSnapshot(
            company(),
            snapshot(forward_eps=None),
        ),
    )

    result = inspect_stock_eps("LITE")

    assert result.inspection.status == EPSInspectionStatus.COMPLETE
    assert result.inspection.selected_forward_eps is None


def test_yahoo_exception_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        eps_service,
        "download_company_fundamentals_with_eps_snapshot",
        lambda symbol: (_ for _ in ()).throw(RuntimeError("Yahoo failed")),
    )

    with pytest.raises(EPSInspectionServiceError, match="Yahoo failed"):
        inspect_stock_eps("LITE")
