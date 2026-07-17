from __future__ import annotations

import textwrap
from enum import Enum
from typing import Any

from src.services.stock_analysis import StockAnalysisServiceResult


_LINE = "=" * 60
_SECTION_LINE = "-" * 60
_LABEL_WIDTH = 24
_EXPLANATION_WIDTH = 76


def format_stock_analysis_report(result: StockAnalysisServiceResult) -> str:
    """Format a stock analysis service result as deterministic plain text."""
    company = result.company
    treasury = result.treasury
    valuation = result.valuation
    target_pe = valuation.target_pe
    macro = valuation.macro_adjustment
    fair_value = valuation.fair_value
    decision = valuation.valuation_decision
    currency = company.currency

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
        _row("Growth-Based PE", _getattr_or_none(target_pe, "growth_based_pe")),
        _row("Raw Target PE", _getattr_or_none(target_pe, "raw_target_pe")),
        _row(
            "Recommended Target PE",
            _getattr_or_none(target_pe, "recommended_target_pe"),
        ),
    ]

    _extend_adjustments(lines, target_pe)

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
    lines.append(_LINE)

    return "\n".join(lines)


def _extend_adjustments(lines: list[str], target_pe: Any) -> None:
    adjustments = _getattr_or_none(target_pe, "adjustments")
    if not adjustments:
        return

    lines.extend(["", "ADJUSTMENTS", _SECTION_LINE])
    for adjustment in adjustments:
        lines.append(_row(_enum_value(adjustment.label), _format_signed_number(adjustment.value)))


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


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
