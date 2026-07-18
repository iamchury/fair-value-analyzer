from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from math import inf, nan

import pytest

from src.analysis.eps_source_inspector import (
    EPSAmbiguityLevel,
    EPSBasisType,
    EPSInspectionStatus,
    EPSPeriodType,
    inspect_eps_source,
)
from src.yahoo.company import (
    EPSRawFieldSource,
    YahooEPSEstimate,
    YahooEPSRawSnapshot,
)


STAMP = datetime(2026, 7, 18, tzinfo=timezone.utc)


def estimate(label: str, value: float | None) -> YahooEPSEstimate:
    return YahooEPSEstimate(
        period_label=label,
        estimate=value,
        low_estimate=None,
        high_estimate=None,
        year_ago_eps=None,
        analyst_count=3,
    )


def source(name: str, field: str = "forwardEps") -> EPSRawFieldSource:
    return EPSRawFieldSource(
        normalized_name=name,
        raw_source="yfinance.Ticker.info",
        raw_field=field,
        value=10.0,
        period_label=None,
        source_timestamp=STAMP,
        warning=None,
    )


def snapshot(**overrides: object) -> YahooEPSRawSnapshot:
    values = {
        "symbol": "LITE",
        "trailing_eps": 8.0,
        "forward_eps": 10.0,
        "trailing_pe": 12.0,
        "forward_pe": 14.0,
        "peg_ratio": 1.2,
        "earnings_growth": None,
        "quarterly_earnings_growth": None,
        "most_recent_quarter": None,
        "last_fiscal_year_end": None,
        "next_fiscal_year_end": None,
        "last_split_date": None,
        "shares_outstanding": None,
        "implied_shares_outstanding": None,
        "price_to_book": None,
        "current_quarter_estimate": estimate("0q", 2.0),
        "next_quarter_estimate": estimate("+1q", 2.5),
        "current_year_estimate": estimate("0y", 10.0),
        "next_year_estimate": estimate("+1y", 12.0),
        "source_timestamp": STAMP,
        "raw_field_sources": (source("forward_eps"),),
        "warnings": (),
    }
    values.update(overrides)
    return YahooEPSRawSnapshot(**values)


def test_snapshot_and_trace_are_immutable() -> None:
    result = snapshot()

    with pytest.raises(FrozenInstanceError):
        result.forward_eps = 11.0
    with pytest.raises(FrozenInstanceError):
        result.raw_field_sources[0].raw_field = "changed"


@pytest.mark.parametrize("value", [-1.0, 0.0, 10.0])
def test_eps_values_accept_negative_zero_and_positive_numbers(value: float) -> None:
    assert snapshot(forward_eps=value).forward_eps == value


@pytest.mark.parametrize("value", [True, "10", nan, inf])
def test_numeric_fields_reject_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        snapshot(forward_eps=value)


def test_source_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        snapshot(source_timestamp=datetime(2026, 7, 18))


@pytest.mark.parametrize("analyst_count", [0, 3])
def test_analyst_count_valid_values(analyst_count: int) -> None:
    assert estimate("0y", 10.0).__class__(
        "0y",
        10.0,
        None,
        None,
        None,
        analyst_count,
    ).analyst_count == analyst_count


@pytest.mark.parametrize("analyst_count", [-1, True, 1.2])
def test_analyst_count_rejects_invalid_values(analyst_count: object) -> None:
    with pytest.raises(ValueError):
        YahooEPSEstimate("0y", 10.0, None, None, None, analyst_count)


def test_forward_eps_matches_current_year_only() -> None:
    result = inspect_eps_source(snapshot(current_year_estimate=estimate("0y", 10.0)))

    assert result.inferred_period_type == EPSPeriodType.CURRENT_FISCAL_YEAR
    assert result.inferred_period_label == "0y"
    assert result.forward_eps_matches_current_year is True
    assert result.forward_eps_matches_next_year is False
    assert result.ambiguity_level == EPSAmbiguityLevel.MEDIUM
    assert result.basis_type == EPSBasisType.UNKNOWN


def test_forward_eps_matches_next_year_only() -> None:
    result = inspect_eps_source(
        snapshot(
            current_year_estimate=estimate("0y", 8.0),
            next_year_estimate=estimate("+1y", 10.0),
        )
    )

    assert result.inferred_period_type == EPSPeriodType.NEXT_FISCAL_YEAR
    assert result.inferred_period_label == "+1y"


def test_forward_eps_matches_both_is_unknown_high_ambiguity() -> None:
    result = inspect_eps_source(
        snapshot(
            current_year_estimate=estimate("0y", 10.0),
            next_year_estimate=estimate("+1y", 10.0),
        )
    )

    assert result.inferred_period_type == EPSPeriodType.UNKNOWN
    assert result.ambiguity_level == EPSAmbiguityLevel.HIGH
    assert "matches both" in " ".join(result.warnings)


def test_forward_eps_matches_neither_is_unknown() -> None:
    result = inspect_eps_source(
        snapshot(
            current_year_estimate=estimate("0y", 8.0),
            next_year_estimate=estimate("+1y", 12.0),
        )
    )

    assert result.inferred_period_type == EPSPeriodType.UNKNOWN
    assert result.ambiguity_level == EPSAmbiguityLevel.HIGH
    assert "does not match" in " ".join(result.warnings)


def test_missing_estimates_and_forward_eps_are_handled() -> None:
    partial = inspect_eps_source(
        snapshot(current_year_estimate=None, next_year_estimate=None)
    )
    unavailable = inspect_eps_source(
        snapshot(
            trailing_eps=None,
            forward_eps=None,
            current_quarter_estimate=None,
            next_quarter_estimate=None,
            current_year_estimate=None,
            next_year_estimate=None,
        )
    )

    assert partial.status == EPSInspectionStatus.PARTIAL
    assert partial.inferred_period_type == EPSPeriodType.UNKNOWN
    assert unavailable.status == EPSInspectionStatus.UNAVAILABLE
    assert unavailable.ambiguity_level == EPSAmbiguityLevel.HIGH


def test_match_tolerance_exact_within_and_outside() -> None:
    exact = inspect_eps_source(snapshot(current_year_estimate=estimate("0y", 10.0)))
    within = inspect_eps_source(snapshot(current_year_estimate=estimate("0y", 9.91)))
    outside = inspect_eps_source(snapshot(current_year_estimate=estimate("0y", 9.8)))

    assert exact.forward_eps_matches_current_year is True
    assert within.forward_eps_matches_current_year is True
    assert outside.forward_eps_matches_current_year is False


def test_negative_and_zero_estimate_comparison_is_deterministic() -> None:
    negative = inspect_eps_source(
        snapshot(
            forward_eps=-10.0,
            current_year_estimate=estimate("0y", -10.0),
            next_year_estimate=None,
        )
    )
    zero = inspect_eps_source(
        snapshot(
            forward_eps=0.0,
            current_year_estimate=estimate("0y", 0.0),
            next_year_estimate=None,
        )
    )

    assert negative.forward_eps_matches_current_year is True
    assert zero.forward_eps_matches_current_year is True


def test_dates_alone_do_not_infer_period() -> None:
    result = inspect_eps_source(
        snapshot(
            current_year_estimate=None,
            next_year_estimate=None,
            last_fiscal_year_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
            next_fiscal_year_end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
    )

    assert result.inferred_period_type == EPSPeriodType.UNKNOWN
