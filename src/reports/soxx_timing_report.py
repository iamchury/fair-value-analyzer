from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


_LINE = "-" * 60


def format_soxx_timing_report(
    result: Any,
    show_chart_data: bool = False,
) -> str:
    lines = [
        "SOXX MARKET TIMING",
        _LINE,
        _row("As Of", _date(getattr(result, "as_of_date", None))),
        _row("Current Price", _number(getattr(result, "current_price", None))),
        _row("Price Field", getattr(result, "price_field", None)),
        _row("Prior High", _number(getattr(result, "prior_high_price", None))),
        _row("Prior High Date", _date(getattr(result, "prior_high_date", None))),
        _row("Drawdown", _percent(getattr(result, "drawdown_pct", None))),
        _row("MA5", _number(getattr(result, "ma5", None))),
        _row("MA10", _number(getattr(result, "ma10", None))),
        _row("MA15", _number(getattr(result, "ma15", None))),
        _row("MA20", _number(getattr(result, "ma20", None))),
        _row("MA50", _number(getattr(result, "ma50", None))),
        "",
        _row("MA5 / MA10 Cross", _plain(getattr(getattr(result, "ma5_ma10_cross", None), "direction", None))),
        _row("MA5 / MA15 Cross", _plain(getattr(getattr(result, "ma5_ma15_cross", None), "direction", None))),
        _row("MA5 / MA20 Cross", _plain(getattr(getattr(result, "ma5_ma20_cross", None), "direction", None))),
        _row("Short MA Converged", _yes_no(getattr(result, "short_ma_converged", None))),
        _row("Short MA Spread", _percent(getattr(result, "short_ma_spread_pct", None))),
        _row("Primary Signal", _plain(getattr(result, "primary_signal", None))),
        _row("Signal Strength", _plain(getattr(result, "signal_strength", None))),
        _row("Signal Direction", _plain(getattr(result, "signal_direction", None))),
        _row("Color Key", getattr(result, "signal_color_key", None)),
        _row("Status", _plain(getattr(result, "status", None))),
        "",
        "ACTIVE CONDITIONS",
        _LINE,
    ]
    conditions = tuple(getattr(result, "active_conditions", ()) or ())
    lines.extend([_plain(item) for item in conditions] or ["None"])
    lines.extend(["", "RATIONALE", _LINE])
    lines.extend(tuple(getattr(result, "rationale", ()) or ("None",)))
    warnings = tuple(getattr(result, "warnings", ()) or ())
    if warnings:
        lines.extend(["", "WARNINGS", _LINE, *warnings])
    if show_chart_data:
        lines.extend(["", "SOXX CHART DATA", _LINE])
        for point in tuple(getattr(result, "daily_points", ()) or ())[-10:]:
            lines.append(
                f"{point.date} close={_number(point.close)} ma5={_number(point.ma5)} "
                f"ma10={_number(point.ma10)} ma15={_number(point.ma15)} "
                f"ma20={_number(point.ma20)} ma50={_number(point.ma50)} "
                f"signal={_plain(point.primary_signal)}"
            )
    return "\n".join(lines)


def soxx_timing_csv(result: Any) -> str:
    output = StringIO()
    fields = [
        "symbol",
        "as_of_date",
        "current_price",
        "price_field",
        "ma5",
        "ma10",
        "ma15",
        "ma20",
        "ma50",
        "prior_high_price",
        "prior_high_date",
        "drawdown_pct",
        "short_ma_spread_pct",
        "short_ma_converged",
        "ma5_ma10_cross",
        "ma5_ma15_cross",
        "ma5_ma20_cross",
        "primary_signal",
        "signal_direction",
        "signal_strength",
        "status",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: _csv_value(_extract_csv(result, field)) for field in fields})
    return output.getvalue()


def soxx_timing_json(result: Any) -> str:
    payload = {
        "symbol": getattr(result, "symbol", None),
        "as_of_date": _date(getattr(result, "as_of_date", None)),
        "price": {
            "current": getattr(result, "current_price", None),
            "field": getattr(result, "price_field", None),
            "prior_high": getattr(result, "prior_high_price", None),
            "prior_high_date": _date(getattr(result, "prior_high_date", None)),
            "drawdown_pct": getattr(result, "drawdown_pct", None),
        },
        "moving_averages": {
            "ma5": getattr(result, "ma5", None),
            "ma10": getattr(result, "ma10", None),
            "ma15": getattr(result, "ma15", None),
            "ma20": getattr(result, "ma20", None),
            "ma50": getattr(result, "ma50", None),
        },
        "crosses": {
            "ma5_ma10": _plain(getattr(getattr(result, "ma5_ma10_cross", None), "direction", None)),
            "ma5_ma15": _plain(getattr(getattr(result, "ma5_ma15_cross", None), "direction", None)),
            "ma5_ma20": _plain(getattr(getattr(result, "ma5_ma20_cross", None), "direction", None)),
        },
        "convergence": {
            "is_converged": getattr(result, "short_ma_converged", None),
            "spread_pct": getattr(result, "short_ma_spread_pct", None),
        },
        "signal": {
            "primary": _plain(getattr(result, "primary_signal", None)),
            "direction": _plain(getattr(result, "signal_direction", None)),
            "strength": _plain(getattr(result, "signal_strength", None)),
            "active_conditions": [_plain(item) for item in tuple(getattr(result, "active_conditions", ()) or ())],
            "color_key": getattr(result, "signal_color_key", None),
            "rationale": list(getattr(result, "rationale", ()) or ()),
        },
        "status": _plain(getattr(result, "status", None)),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _extract_csv(result: Any, field: str) -> Any:
    if field.endswith("_cross"):
        name = field.replace("_cross", "_cross")
        return _plain(getattr(getattr(result, name, None), "direction", None))
    return getattr(result, field, None)


def _csv_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _row(label: str, value: Any) -> str:
    return f"{label:<24}: {value if value not in (None, '') else 'N/A'}"


def _number(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.2f}"


def _percent(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):+.2f}%"


def _yes_no(value: Any) -> str:
    if value is None:
        return "N/A"
    return "YES" if bool(value) else "NO"


def _plain(value: Any) -> str:
    if value is None:
        return "N/A"
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _date(value: Any) -> str:
    if value is None:
        return "N/A"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
