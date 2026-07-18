from __future__ import annotations

import textwrap
from enum import Enum
from typing import Any

from src.services.stock_analysis import StockAnalysisServiceResult


_LINE = "=" * 60
_SECTION_LINE = "-" * 60
_LABEL_WIDTH = 24
_EXPLANATION_WIDTH = 76


def format_stock_analysis_report(
    result: StockAnalysisServiceResult,
    show_snapshots: bool = False,
) -> str:
    """Format a stock analysis service result as deterministic plain text."""
    company = result.company
    treasury = result.treasury
    valuation = result.valuation
    target_pe = valuation.target_pe
    macro = valuation.macro_adjustment
    fair_value = valuation.fair_value
    decision = valuation.valuation_decision
    currency = company.currency
    profile = getattr(result, "profile", None)
    research = getattr(result, "research_valuation", None)
    comparison = getattr(result, "valuation_comparison", None)
    eps_selection = getattr(result, "eps_selection", None)
    industry_policy = getattr(result, "industry_policy", None)
    analyst = getattr(result, "analyst_consensus", None)

    lines: list[str] = [
        _LINE,
        "STOCK VALUATION REPORT",
        _LINE,
        _row("Symbol", valuation.symbol),
        _row("Company", company.company_name),
        _row("Status", valuation.status),
        "",
        "MARKET DATA",
        _SECTION_LINE,
        _row("Current Price", _format_currency(company.current_price, currency)),
        _row("Previous Close", _format_currency(company.previous_close, currency)),
        _row(
            "52-Week Range",
            _format_currency_range(
                company.fifty_two_week_low,
                company.fifty_two_week_high,
                currency,
            ),
        ),
        _row(
            "Analyst Target Mean",
            _format_currency(company.analyst_target_mean_price, currency),
        ),
        _row("Analyst Target High", _format_currency(company.analyst_target_high_price, currency)),
        _row("Analyst Target Low", _format_currency(company.analyst_target_low_price, currency)),
        _row("Market Cap", _format_currency(company.market_cap, currency)),
        _row("Sector", company.sector),
        _row("Industry", company.industry),
        "",
        "EARNINGS",
        _SECTION_LINE,
        _row("Trailing EPS", valuation.trailing_eps),
        _row("Forward EPS", valuation.forward_eps),
        _row("EPS Transition", valuation.eps_growth.transition),
        _row("EPS Growth", _format_percent(valuation.eps_growth.growth_percent)),
        _row("PEG Ratio", company.peg_ratio),
        _row("Trailing PE", company.trailing_pe),
        _row("Current Forward PE", company.forward_pe),
        "",
        "TARGET PE",
        _SECTION_LINE,
        _row(
            "Actual EPS Growth",
            _format_percent(_getattr_or_none(target_pe, "actual_eps_growth_percent")),
        ),
        _row(
            "Effective EPS Growth",
            _format_percent(
                _getattr_or_none(target_pe, "effective_eps_growth_percent")
            ),
        ),
        _row(
            "EPS Growth Capped",
            _format_yes_no(_getattr_or_none(target_pe, "eps_growth_was_capped")),
        ),
        _row("Growth-Based PE", _getattr_or_none(target_pe, "growth_based_pe")),
        _row("Raw Target PE", _getattr_or_none(target_pe, "raw_target_pe")),
        _row(
            "Recommended Target PE",
            _getattr_or_none(target_pe, "recommended_target_pe"),
        ),
        *(
            [_row("Policy Target PE", industry_policy.policy_target_pe)]
            if industry_policy is not None
            else []
        ),
    ]

    _extend_adjustments(lines, target_pe)
    if industry_policy is not None:
        _extend_industry_policy(lines, industry_policy)

    if eps_selection is not None:
        lines.extend(
            [
                "",
                "VALUATION EPS SELECTION",
                _SECTION_LINE,
                _row("Requested Method", eps_selection.requested_method),
                _row("Applied Method", eps_selection.applied_method),
                _row("Selection Status", eps_selection.status),
                _row("Yahoo Forward EPS", eps_selection.legacy_forward_eps),
                _row("Current-Year EPS", eps_selection.current_year_eps),
                _row("Next-Year EPS", eps_selection.next_year_eps),
                _row("Selected Valuation EPS", eps_selection.selected_eps),
                _row("Selected Period", eps_selection.selected_period_label),
                _row(
                    "Difference vs Forward",
                    _format_signed_percent(
                        eps_selection.selected_vs_legacy_difference_percent
                    ),
                ),
                _row("Fallback Reason", eps_selection.fallback_reason),
                _row("Rationale", eps_selection.rationale),
            ]
        )
        if eps_selection.warnings:
            lines.append(_row("Selection Warning", eps_selection.warnings[0]))

    if analyst is not None:
        _extend_analyst_consensus(lines, analyst, currency)

    lines.extend(
        [
            "",
            "TREASURY MACRO",
            _SECTION_LINE,
            _row("Treasury Symbol", treasury.symbol),
            _row("Yield Date", treasury.yield_date),
            _row(
                "Current 10Y Yield",
                _format_percent(_getattr_or_none(macro, "current_yield_percent")),
            ),
            _row("Short SMA", _format_percent(_getattr_or_none(macro, "sma_short_percent"))),
            _row("Long SMA", _format_percent(_getattr_or_none(macro, "sma_long_percent"))),
            _row("Trend", _getattr_or_none(macro, "trend")),
            _row(
                "Yield Discount",
                _format_percent(_getattr_or_none(macro, "level_discount_percent")),
            ),
            _row(
                "Trend Adjustment",
                _format_percent(_getattr_or_none(macro, "trend_adjustment_percent")),
            ),
            _row(
                "Macro Multiplier",
                _format_number(
                    _getattr_or_none(macro, "total_adjustment_multiplier"),
                    decimal_places=4,
                ),
            ),
            "",
            "FAIR VALUE",
            _SECTION_LINE,
            *(
                [
                    *(
                        [
                            _row(
                                "Target PE Used",
                                _getattr_or_none(valuation, "target_pe_used"),
                            )
                        ]
                        if industry_policy is not None
                        else []
                    ),
                    _row(
                        "Valuation EPS Used",
                        _getattr_or_none(valuation, "valuation_eps_used"),
                    ),
                    _row(
                        "Valuation EPS Method",
                        _getattr_or_none(valuation, "valuation_eps_method"),
                    ),
                ]
                if eps_selection is not None
                else []
            ),
            *(
                [
                    _row(
                        "Target PE Used",
                        _getattr_or_none(valuation, "target_pe_used"),
                    )
                ]
                if industry_policy is not None and eps_selection is None
                else []
            ),
            _row(
                "Base Fair Value",
                _format_currency(_getattr_or_none(fair_value, "base_fair_value"), currency),
            ),
            _row(
                "Adjusted Fair Value",
                _format_currency(
                    _getattr_or_none(fair_value, "adjusted_fair_value"),
                    currency,
                ),
            ),
            _row("Buy Price", _format_currency(_getattr_or_none(decision, "buy_price"), currency)),
            _row("Sell Price", _format_currency(_getattr_or_none(decision, "sell_price"), currency)),
            _row(
                "Discount to Fair Value",
                _format_percent(
                    _getattr_or_none(decision, "discount_to_fair_value_percent")
                ),
            ),
            _row(
                "Upside to Fair Value",
                _format_percent(_getattr_or_none(decision, "upside_to_fair_value_percent")),
            ),
            "",
            "RECOMMENDATION",
            _SECTION_LINE,
            _row("Decision", _getattr_or_none(decision, "recommendation")),
            "",
            "EXPLANATION",
            _SECTION_LINE,
        ]
    )
    lines.extend(_wrap_explanation(valuation.explanation, width=_EXPLANATION_WIDTH))
    if profile is not None:
        lines.extend(
            [
                "",
                "RESEARCH VALUATION PROFILE",
                _SECTION_LINE,
                _row("Valuation Style", profile.valuation_style),
                _row("EPS Fiscal Year", profile.eps_fiscal_year),
                _row("Research EPS", profile.valuation_eps),
                _row("Research Target PE", profile.target_pe),
                _row(
                    "PEG Adjustment Enabled",
                    _format_yes_no(profile.use_peg_adjustment),
                ),
                _row("Source Note", profile.source_note),
                "",
                "RESEARCH FAIR VALUE",
                _SECTION_LINE,
                _row(
                    "Research Base Value",
                    _format_currency(
                        _getattr_or_none(research, "research_base_fair_value"),
                        currency,
                    ),
                ),
                _row(
                    "Research Adjusted Value",
                    _format_currency(
                        _getattr_or_none(research, "research_adjusted_fair_value"),
                        currency,
                    ),
                ),
                _row(
                    "DCF Reference",
                    _format_currency(_getattr_or_none(research, "dcf_fair_value"), currency),
                ),
                "",
                "MODEL COMPARISON",
                _SECTION_LINE,
                _row(
                    "Automatic Fair Value",
                    _format_currency(
                        _getattr_or_none(comparison, "automatic_fair_value"),
                        currency,
                    ),
                ),
                _row(
                    "Research Fair Value",
                    _format_currency(
                        _getattr_or_none(comparison, "research_fair_value"),
                        currency,
                    ),
                ),
                _row(
                    "Automatic - Research",
                    _format_currency(
                        _getattr_or_none(
                            comparison,
                            "automatic_vs_research_difference",
                        ),
                        currency,
                    ),
                ),
                _row(
                    "Difference",
                    _format_percent(
                        _getattr_or_none(
                            comparison,
                            "automatic_vs_research_difference_percent",
                        )
                    ),
                ),
                _row(
                    "Research - DCF",
                    _format_currency(
                        _getattr_or_none(comparison, "research_vs_dcf_difference"),
                        currency,
                    ),
                ),
                _row(
                    "Difference vs DCF",
                    _format_percent(
                        _getattr_or_none(
                            comparison,
                            "research_vs_dcf_difference_percent",
                        )
                    ),
                ),
                *(
                    [
                        _row(
                            "Analyst Fair Value",
                            _format_currency(
                                _getattr_or_none(
                                    analyst,
                                    "adjusted_analyst_fair_value",
                                ),
                                currency,
                            ),
                        ),
                        _row(
                            "Analyst Quality",
                            _getattr_or_none(analyst, "consensus_quality"),
                        ),
                        _row(
                            "Analyst - Automatic",
                            _format_currency(
                                _difference(
                                    _getattr_or_none(
                                        analyst,
                                        "adjusted_analyst_fair_value",
                                    ),
                                    _getattr_or_none(
                                        comparison,
                                        "automatic_fair_value",
                                    ),
                                ),
                                currency,
                            ),
                        ),
                        _row(
                            "Analyst - Research",
                            _format_currency(
                                _difference(
                                    _getattr_or_none(
                                        analyst,
                                        "adjusted_analyst_fair_value",
                                    ),
                                    _getattr_or_none(
                                        comparison,
                                        "research_fair_value",
                                    ),
                                ),
                                currency,
                            ),
                        ),
                    ]
                    if analyst is not None
                    else []
                ),
            ]
        )
    if show_snapshots:
        _extend_snapshot_report(
            lines,
            getattr(result, "valuation_snapshots", None),
            currency,
        )

    lines.append(_LINE)

    return "\n".join(lines)


def _extend_adjustments(lines: list[str], target_pe: Any) -> None:
    adjustments = _getattr_or_none(target_pe, "adjustments")
    if not adjustments:
        return

    lines.extend(["", "ADJUSTMENTS", _SECTION_LINE])
    cap_explanation = _getattr_or_none(target_pe, "eps_growth_cap_explanation")
    if cap_explanation:
        lines.append(_row("EPS growth cap", cap_explanation))
    for adjustment in adjustments:
        lines.append(_row(_enum_value(adjustment.label), _format_signed_number(adjustment.value)))


def _extend_industry_policy(lines: list[str], policy: Any) -> None:
    lines.extend(
        [
            "",
            "INDUSTRY VALUATION POLICY",
            _SECTION_LINE,
            _row("Policy Name", policy.policy_name),
            _row("Valuation Style", policy.valuation_style),
            _row("Target PE Mode", policy.target_pe_mode),
            _row("Original Target PE", policy.original_target_pe),
            _row("Policy Target PE", policy.policy_target_pe),
            _row(
                "Policy PE Range",
                _format_number_range(policy.minimum_target_pe, policy.maximum_target_pe),
            ),
            _row(
                "EPS Growth Adjustment",
                _format_enabled("EPS Growth Adjustment", policy.enabled_adjustments),
            ),
            _row(
                "PEG Adjustment",
                _format_enabled("PEG Adjustment", policy.enabled_adjustments),
            ),
            _row(
                "Sector Adjustment",
                _format_enabled("Sector Adjustment", policy.enabled_adjustments),
            ),
            _row(
                "Forward PE Penalty",
                _format_enabled("Forward PE Penalty", policy.enabled_adjustments),
            ),
            _row("Rationale", policy.rationale),
        ]
    )
    if policy.warnings:
        lines.append(_row("Policy Warning", policy.warnings[0]))
    for adjustment in getattr(policy, "adjustments", ()):
        lines.append(
            _row(
                _enum_value(adjustment.label),
                _format_signed_number(adjustment.value),
            )
        )


def _extend_analyst_consensus(lines: list[str], analyst: Any, currency: str | None) -> None:
    lines.extend(
        [
            "",
            "ANALYST CONSENSUS MODEL",
            _SECTION_LINE,
            _row("Status", analyst.status),
            _row("Fair Value Method", analyst.fair_value_method),
            _row("Analyst Count", analyst.analyst_count),
            _row("Target Mean", _format_currency(analyst.target_mean, currency)),
            _row("Target High", _format_currency(analyst.target_high, currency)),
            _row("Target Low", _format_currency(analyst.target_low, currency)),
            _row("Target Midpoint", _format_currency(analyst.target_midpoint, currency)),
            _row("Target Range", _format_currency(analyst.target_range, currency)),
            _row("Dispersion", _format_percent(analyst.dispersion_percent)),
            _row("Dispersion Level", analyst.dispersion_level),
            _row("Consensus Quality", analyst.consensus_quality),
            _row("Mean Upside", _format_percent(analyst.mean_upside_percent)),
            _row("Low Upside", _format_percent(analyst.low_upside_percent)),
            _row("High Upside", _format_percent(analyst.high_upside_percent)),
            _row(
                "Raw Analyst Fair Value",
                _format_currency(analyst.raw_analyst_fair_value, currency),
            ),
            _row("Treasury Applied", _format_yes_no(analyst.treasury_applied)),
            _row(
                "Analyst Fair Value",
                _format_currency(analyst.adjusted_analyst_fair_value, currency),
            ),
            _row("Analyst Target As Of", analyst.analyst_target_as_of),
            _row("Retrieved At", analyst.retrieved_at),
            _row("Rationale", analyst.rationale),
        ]
    )
    if analyst.warnings:
        lines.extend(["", "ANALYST WARNINGS", _SECTION_LINE])
        for warning in analyst.warnings:
            lines.append(f"- {warning}")


def _extend_snapshot_report(lines: list[str], collection: Any, currency: str | None) -> None:
    snapshots = tuple(getattr(collection, "snapshots", ()) or ())
    if not snapshots:
        lines.extend(
            [
                "",
                "UNIFIED VALUATION SNAPSHOTS",
                _SECTION_LINE,
                "No valuation snapshots available.",
            ]
        )
        return

    lines.extend(
        [
            "",
            "UNIFIED VALUATION SNAPSHOTS",
            _SECTION_LINE,
            f"{'Model':<18} {'Selected Value':>16} {'Status':<10} "
            f"{'Confidence':<12} {'Value Type':<18}",
        ]
    )
    for snapshot in snapshots:
        lines.append(
            f"{_format_optional_text(snapshot.model_type):<18} "
            f"{_format_currency(snapshot.selected_fair_value, snapshot.currency or currency):>16} "
            f"{_format_optional_text(snapshot.status):<10} "
            f"{_format_optional_text(snapshot.confidence):<12} "
            f"{_format_optional_text(snapshot.value_type):<18}"
        )

    for snapshot in snapshots:
        lines.extend(
            [
                "",
                _row("Model", snapshot.model_type),
                _row("Status", snapshot.status),
                _row("Confidence", snapshot.confidence),
                _row("Value Type", snapshot.value_type),
                _row(
                    "Raw Fair Value",
                    _format_currency(snapshot.raw_fair_value, snapshot.currency or currency),
                ),
                _row(
                    "Adjusted Fair Value",
                    _format_currency(
                        snapshot.adjusted_fair_value,
                        snapshot.currency or currency,
                    ),
                ),
                _row(
                    "Selected Fair Value",
                    _format_currency(
                        snapshot.selected_fair_value,
                        snapshot.currency or currency,
                    ),
                ),
                _row("Methodology", snapshot.methodology),
            ]
        )
        if snapshot.warnings:
            lines.append(_row("Warnings", "; ".join(snapshot.warnings)))


def _row(label: str, value: Any) -> str:
    return f"{label:<{_LABEL_WIDTH}}: {_format_value(value)}"


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _format_number(value)
    return _format_optional_text(value)


def _format_number(value: Any, decimal_places: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimal_places}f}"


def _format_signed_number(value: Any, decimal_places: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.{decimal_places}f}"


def _format_percent(value: Any, decimal_places: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimal_places}f}%"


def _format_signed_percent(value: Any, decimal_places: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.{decimal_places}f}%"


def _format_yes_no(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "YES" if value else "NO"


def _format_currency(value: Any, currency: str | None) -> str:
    if value is None:
        return "N/A"
    return f"{_format_number(value)} {_format_optional_text(currency)}"


def _format_currency_range(
    low_value: Any,
    high_value: Any,
    currency: str | None,
) -> str:
    if low_value is None or high_value is None:
        return "N/A"
    currency_text = _format_optional_text(currency)
    return f"{_format_number(low_value)} - {_format_number(high_value)} {currency_text}"


def _format_number_range(low_value: Any, high_value: Any) -> str:
    if low_value is None or high_value is None:
        return "N/A"
    return f"{_format_number(low_value)} - {_format_number(high_value)}"


def _format_enabled(label: str, enabled_adjustments: Any) -> str:
    return "ENABLED" if label in enabled_adjustments else "DISABLED"


def _format_optional_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value).strip()
    return text or "N/A"


def _wrap_explanation(text: str | None, width: int = _EXPLANATION_WIDTH) -> list[str]:
    explanation = _format_optional_text(text)
    return textwrap.wrap(explanation, width=width) or ["N/A"]


def _getattr_or_none(value: Any, attribute_name: str) -> Any:
    if value is None:
        return None
    return getattr(value, attribute_name)


def _difference(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
