from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


_LINE = "-" * 60


def format_soxx_timing_report(
    result: Any,
    show_chart_data: bool = False,
    show_event_audit: bool = False,
) -> str:
    lines = [
        "SOXX MARKET TIMING",
        _LINE,
        _row("As Of", _date(getattr(result, "as_of_date", None))),
        _row("Current Price", _number(getattr(result, "current_price", None))),
        _row("Price Field", getattr(result, "price_field", None)),
        _row("Moving Average Type", getattr(result, "moving_average_type", None)),
        _row("Prior High", _number(getattr(result, "prior_high_price", None))),
        _row("Prior High Date", _date(getattr(result, "prior_high_date", None))),
        _row("Drawdown", _percent(getattr(result, "drawdown_pct", None))),
        _row("EMA5", _number(getattr(result, "ma5", None))),
        _row("EMA10", _number(getattr(result, "ma10", None))),
        _row("EMA15", _number(getattr(result, "ma15", None))),
        _row("EMA20", _number(getattr(result, "ma20", None))),
        _row("EMA50", _number(getattr(result, "ma50", None))),
        _row("EMA50 Trend", _plain(getattr(result, "ema50_trend", None))),
        _row("EMA50 Daily Change", _signed_number(getattr(result, "ema50_slope", None))),
        _row("EMA50 Turning Point", _plain(getattr(result, "ema50_turn_event", None))),
        _row("Latest EMA50 Turn", _latest_turn(result)),
        "",
        _row("EMA5 / EMA10 Cross", _plain(getattr(getattr(result, "ma5_ma10_cross", None), "direction", None))),
        _row("EMA5 / EMA15 Cross", _plain(getattr(getattr(result, "ma5_ma15_cross", None), "direction", None))),
        _row("EMA5 / EMA20 Cross", _plain(getattr(getattr(result, "ma5_ma20_cross", None), "direction", None))),
        _row("Short EMA Converged", _yes_no(getattr(result, "short_ma_converged", None))),
        _row("Short EMA Spread", _percent(getattr(result, "short_ma_spread_pct", None))),
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
    events = tuple(getattr(result, "events", ()) or ())
    if events:
        lines.extend(["", "SIGNAL HISTORY", _LINE])
        for event in events:
            lines.append(
                f"{_date(getattr(event, 'date', None))} "
                f"{_plain(getattr(event, 'signal', None)):<18} "
                f"{_cross_basis(event)}"
            )
        if show_event_audit:
            lines.extend(["", "SOXX EVENT AUDIT", _LINE])
            for event in events:
                lines.extend(_event_audit_lines(event))
    turn_events = tuple(getattr(result, "ema50_turn_events", ()) or ())
    if turn_events:
        lines.extend(["", "EMA50 TURNING POINT HISTORY", _LINE])
        for event in turn_events:
            lines.append(
                f"{_date(getattr(event, 'date', None))} "
                f"{_plain(getattr(event, 'event', None)):<10} "
                f"{getattr(event, 'description', '')}"
            )
    if show_chart_data:
        lines.extend(["", "SOXX CHART DATA", _LINE])
        for point in tuple(getattr(result, "daily_points", ()) or ())[-10:]:
            lines.append(
                f"{point.date} close={_number(point.close)} ema5={_number(point.ma5)} "
                f"ema10={_number(point.ma10)} ema15={_number(point.ma15)} "
                f"ema20={_number(point.ma20)} ema50={_number(point.ma50)} "
                f"ema50_slope={_signed_number(getattr(point, 'ema50_slope', None))} "
                f"ema50_trend={_plain(getattr(point, 'ema50_trend', None))} "
                f"ema50_turn={_plain(getattr(point, 'ema50_turn_event', None))} "
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
        "moving_average_type",
        "ema5",
        "ema10",
        "ema15",
        "ema20",
        "ema50",
        "ema50_slope",
        "ema50_trend",
        "ema50_turn_event",
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
            "type": getattr(result, "moving_average_type", None),
            "adjust": getattr(result, "exponential_adjust", None),
            "ema5": getattr(result, "ma5", None),
            "ema10": getattr(result, "ma10", None),
            "ema15": getattr(result, "ma15", None),
            "ema20": getattr(result, "ma20", None),
            "ema50": getattr(result, "ma50", None),
            "ema50_slope": getattr(result, "ema50_slope", None),
            "previous_ema50_slope": getattr(result, "previous_ema50_slope", None),
            "ema50_trend": _plain(getattr(result, "ema50_trend", None)),
            "ema50_turn_event": _plain(getattr(result, "ema50_turn_event", None)),
            "latest_ema50_turn_date": _date(getattr(result, "latest_ema50_turn_date", None)),
            "latest_ema50_turn_event": _plain(getattr(result, "latest_ema50_turn_event", None)),
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
        "events": [_event_payload(event) for event in tuple(getattr(result, "events", ()) or ())],
        "ema50_turn_events": [_ema50_turn_payload(event) for event in tuple(getattr(result, "ema50_turn_events", ()) or ())],
        "status": _plain(getattr(result, "status", None)),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "date": _date(getattr(event, "date", None)),
        "signal": _plain(getattr(event, "signal", None)),
        "crossed_average": getattr(event, "crossed_average", None),
        "fast_average": getattr(event, "fast_average", None),
        "cross_direction": _plain(getattr(event, "cross_direction", None)),
        "previous_ema5": getattr(event, "previous_ma5", None),
        "previous_target_ema": getattr(event, "previous_target_ma", None),
        "current_ema5": getattr(event, "current_ma5", None),
        "current_target_ema": getattr(event, "current_target_ma", None),
    }


def _ema50_turn_payload(event: Any) -> dict[str, Any]:
    return {
        "date": _date(getattr(event, "date", None)),
        "event": _plain(getattr(event, "event", None)),
        "ema50": getattr(event, "ema50", None),
        "ema50_slope": getattr(event, "ema50_slope", None),
        "previous_ema50_slope": getattr(event, "previous_ema50_slope", None),
        "description": getattr(event, "description", None),
    }


def _cross_basis(event: Any) -> str:
    fast = getattr(event, "fast_average", None)
    slow = getattr(event, "crossed_average", None)
    direction = _plain(getattr(event, "cross_direction", None))
    if fast is None or slow is None:
        return direction
    direction_text = "above" if direction == "CROSS_ABOVE" else "below"
    return f"EMA{fast} crossed {direction_text} EMA{slow}"


def _event_audit_lines(event: Any) -> list[str]:
    slow = getattr(event, "crossed_average", None)
    target_label = f"EMA{slow}" if slow is not None else "Target EMA"
    valid = "YES" if not _event_invariant_errors(event) else "NO"
    return [
        _row("Date", _date(getattr(event, "date", None))),
        _row("Signal", _plain(getattr(event, "signal", None))),
        _row("Crossed Average", target_label if slow is not None else "N/A"),
        _row("Cross Direction", _plain(getattr(event, "cross_direction", None))),
        _row("Previous Date", _date(getattr(event, "previous_date", None))),
        _row("Current Date", _date(getattr(event, "current_date", None))),
        _row("Previous EMA5", _number(getattr(event, "previous_ma5", None))),
        _row(f"Previous {target_label}", _number(getattr(event, "previous_target_ma", None))),
        _row("Current EMA5", _number(getattr(event, "current_ma5", None))),
        _row(f"Current {target_label}", _number(getattr(event, "current_target_ma", None))),
        _row("Invariant Valid", valid),
        "",
    ]


def _event_invariant_errors(event: Any) -> tuple[str, ...]:
    try:
        from src.analysis.soxx_timing import soxx_event_invariant_errors

        return soxx_event_invariant_errors(event)
    except Exception:
        return ()


def _extract_csv(result: Any, field: str) -> Any:
    if field.endswith("_cross"):
        name = field.replace("_cross", "_cross")
        return _plain(getattr(getattr(result, name, None), "direction", None))
    ema_aliases = {
        "ema5": "ma5",
        "ema10": "ma10",
        "ema15": "ma15",
        "ema20": "ma20",
        "ema50": "ma50",
    }
    if field in ema_aliases:
        return getattr(result, ema_aliases[field], None)
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


def _signed_number(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):+.2f}"


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


def _latest_turn(result: Any) -> str:
    event = _plain(getattr(result, "latest_ema50_turn_event", None))
    event_date = _date(getattr(result, "latest_ema50_turn_date", None))
    if event in {"NONE", "N/A", "UNAVAILABLE"} or event_date == "N/A":
        return "None"
    return f"{event_date} {event}"
