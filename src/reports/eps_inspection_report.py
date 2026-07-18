from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from src.services.eps_inspection import EPSInspectionServiceResult


_LINE = "=" * 60
_SECTION_LINE = "-" * 60
_LABEL_WIDTH = 24


def format_eps_inspection_report(result: EPSInspectionServiceResult) -> str:
    """Format an EPS source inspection result as deterministic plain text."""
    inspection = result.inspection
    snapshot = result.eps_snapshot
    lines = [
        _LINE,
        "EPS SOURCE INSPECTION",
        _LINE,
        _row("Symbol", inspection.symbol),
        _row("Status", inspection.status),
        _row("Ambiguity", inspection.ambiguity_level),
        _row("Source Timestamp", _format_datetime(inspection.source_timestamp)),
        "",
        "RAW EPS FIELDS",
        _SECTION_LINE,
        _row("Yahoo trailingEps", snapshot.trailing_eps),
        _row("Yahoo forwardEps", snapshot.forward_eps),
        _row("Yahoo trailingPE", snapshot.trailing_pe),
        _row("Yahoo forwardPE", snapshot.forward_pe),
        _row("Yahoo pegRatio", snapshot.peg_ratio),
        _row("Earnings Growth", snapshot.earnings_growth),
        _row("Quarterly Growth", snapshot.quarterly_earnings_growth),
        _row("Current-Year Estimate", inspection.current_year_eps_estimate),
        _row("Next-Year Estimate", inspection.next_year_eps_estimate),
        _row("Current-Quarter Estimate", inspection.current_quarter_eps_estimate),
        _row("Next-Quarter Estimate", inspection.next_quarter_eps_estimate),
        "",
        "PERIOD INFORMATION",
        _SECTION_LINE,
        _row("Last Fiscal Year End", _format_date(inspection.last_fiscal_year_end)),
        _row("Next Fiscal Year End", _format_date(inspection.next_fiscal_year_end)),
        _row("Most Recent Quarter", _format_date(inspection.most_recent_quarter)),
        _row("Inferred Forward Period", inspection.inferred_period_type),
        _row("Inferred Period Label", inspection.inferred_period_label),
        _row("Accounting Basis", inspection.basis_type),
        "",
        "MATCH ANALYSIS",
        _SECTION_LINE,
        _row("Match Current Year", _format_yes_no(inspection.forward_eps_matches_current_year)),
        _row(
            "Difference",
            _format_percent(inspection.forward_eps_current_year_difference_percent),
        ),
        _row("Match Next Year", _format_yes_no(inspection.forward_eps_matches_next_year)),
        _row(
            "Difference",
            _format_percent(inspection.forward_eps_next_year_difference_percent),
        ),
        _row("Match Tolerance", _format_percent(inspection.match_tolerance_percent)),
        "",
        "SOURCE TRACE",
        _SECTION_LINE,
    ]
    lines.extend(_source_trace_lines(inspection))

    lines.extend(["", "WARNINGS", _SECTION_LINE])
    if inspection.warnings:
        lines.extend(f"- {warning}" for warning in inspection.warnings)
    else:
        lines.append("None")

    lines.append(_LINE)
    return "\n".join(lines)


def _source_trace_lines(result: Any) -> list[str]:
    wanted = {
        "forward_eps": "Forward EPS",
        "current_year_estimate": "Current-Year Estimate",
        "next_year_estimate": "Next-Year Estimate",
        "current_quarter_estimate": "Current-Quarter Estimate",
        "next_quarter_estimate": "Next-Quarter Estimate",
    }
    lines = []
    for source in result.raw_field_sources:
        label = wanted.get(source.normalized_name)
        if label is None:
            continue
        lines.append(_row(label, f'{source.raw_source}["{source.raw_field}"]'))
    return lines or [_row("Source Trace", "N/A")]


def _row(label: str, value: Any) -> str:
    return f"{label:<{_LABEL_WIDTH}}: {_format_value(value)}"


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value).strip() or "N/A"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _format_yes_no(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "YES" if value else "NO"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.isoformat()


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()
