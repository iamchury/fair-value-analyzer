from datetime import datetime, timezone
from math import nan

import pytest

from src.yahoo.company import (
    YahooEPSEstimate,
    extract_eps_estimates,
    extract_eps_raw_snapshot,
    normalize_optional_date,
)


STAMP = datetime(2026, 7, 18, tzinfo=timezone.utc)


class LocAccessor:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, label):
        return self.rows[label]


class EstimateTable:
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns
        self.loc = LocAccessor(rows)
        self.empty = False


def table(rows=None, columns=None):
    return EstimateTable(
        rows
        or {
            "0q": {"avg": 1, "low": 0.8, "high": 1.2, "yearAgoEps": 0.7, "numberOfAnalysts": 5},
            "+1q": {"avg": 2.0, "low": 1.8, "high": 2.2, "yearAgoEps": 1.7, "numberOfAnalysts": 6},
            "0y": {"avg": 10.0, "low": 9.0, "high": 11.0, "yearAgoEps": 8.0, "numberOfAnalysts": 7},
            "+1y": {"avg": 12.0, "low": 11.0, "high": 13.0, "yearAgoEps": 10.0, "numberOfAnalysts": 8},
        },
        columns or ["avg", "low", "high", "yearAgoEps", "numberOfAnalysts"],
    )


def test_all_supported_estimate_rows_are_parsed() -> None:
    estimates, warnings, sources = extract_eps_estimates(table(), STAMP)

    assert isinstance(estimates["0q"], YahooEPSEstimate)
    assert estimates["0q"].estimate == 1.0
    assert estimates["+1q"].estimate == 2.0
    assert estimates["0y"].estimate == 10.0
    assert estimates["+1y"].estimate == 12.0
    assert estimates["+1y"].analyst_count == 8
    assert warnings == ()
    assert [source.raw_field for source in sources] == ["0q", "+1q", "0y", "+1y"]


def test_missing_row_and_missing_column_are_handled() -> None:
    estimates, warnings, _ = extract_eps_estimates(
        table(rows={"0y": {"avg": 10.0}}, columns=["avg"]),
        STAMP,
    )

    assert estimates["0y"].estimate == 10.0
    assert estimates["0y"].low_estimate is None
    assert estimates["+1y"] is None
    assert "row +1y unavailable" in " ".join(warnings)


def test_empty_none_and_unsupported_tables_do_not_crash() -> None:
    empty = table()
    empty.empty = True

    assert extract_eps_estimates(None, STAMP)[1] == ("earnings estimate table unavailable.",)
    assert extract_eps_estimates(empty, STAMP)[1] == ("earnings estimate table unavailable.",)
    assert "unsupported" in extract_eps_estimates(object(), STAMP)[1][0]
    assert "unsupported" in extract_eps_estimates(table(columns=["surprise"]), STAMP)[1][0]


def test_nan_is_converted_to_unavailable_and_bool_is_rejected() -> None:
    estimates, _, _ = extract_eps_estimates(
        table(rows={"0y": {"avg": nan}}, columns=["avg"]),
        STAMP,
    )
    assert estimates["0y"].estimate is None

    with pytest.raises(ValueError):
        extract_eps_estimates(table(rows={"0y": {"avg": True}}, columns=["avg"]), STAMP)


def test_date_normalization_and_invalid_date_warning() -> None:
    warnings = []

    assert normalize_optional_date(1_772_726_400, "date").year == 2026
    assert normalize_optional_date("2026-07-18", "date").isoformat() == "2026-07-18"
    assert normalize_optional_date("not-a-date", "bad", warnings) is None
    assert warnings == ["bad date value is invalid."]


def test_raw_snapshot_contains_plain_values_and_invalid_dates_warn() -> None:
    snapshot = extract_eps_raw_snapshot(
        "lite",
        {
            "trailingEps": 8.0,
            "forwardEps": 10.0,
            "lastFiscalYearEnd": "bad-date",
        },
        table(),
        STAMP,
    )

    assert snapshot.symbol == "LITE"
    assert snapshot.forward_eps == 10.0
    assert snapshot.current_year_estimate.estimate == 10.0
    assert snapshot.last_fiscal_year_end is None
    assert "lastFiscalYearEnd date value is invalid." in snapshot.warnings
