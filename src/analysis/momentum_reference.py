from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from math import isclose, isfinite

from src.config.momentum_reference import MomentumReferenceConfiguration
from src.yahoo.prices import HistoricalPriceRow, HistoricalPriceSeries


class MomentumReferenceStatus(str, Enum):
    COMPLETE = "COMPLETE"
    FALLBACK = "FALLBACK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class RsiCrossDirection(str, Enum):
    CROSS_ABOVE = "CROSS_ABOVE"
    CROSS_BELOW = "CROSS_BELOW"
    NEAREST_TO_50 = "NEAREST_TO_50"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class PriceField(str, Enum):
    ADJUSTED_CLOSE = "ADJUSTED_CLOSE"
    CLOSE = "CLOSE"


class MomentumPricePosition(str, Enum):
    ABOVE_RSI50_REFERENCE = "ABOVE_RSI50_REFERENCE"
    BELOW_RSI50_REFERENCE = "BELOW_RSI50_REFERENCE"
    AT_RSI50_REFERENCE = "AT_RSI50_REFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RsiPoint:
    date: date
    close: float
    rsi: float


@dataclass(frozen=True)
class RsiMomentumReference:
    symbol: str
    status: MomentumReferenceStatus
    rsi_period: int
    neutral_level: float
    reference_date: date | None
    reference_price: float | None
    reference_rsi: float | None
    cross_direction: RsiCrossDirection
    current_date: date | None
    current_price: float | None
    current_rsi: float | None
    price_field: PriceField | None
    trading_days_since_reference: int | None
    price_change_since_reference: float | None
    price_change_since_reference_pct: float | None
    price_position: MomentumPricePosition
    lookback_start: date | None
    lookback_end: date | None
    observation_count: int
    methodology: str
    rationale: str | None
    warnings: tuple[str, ...]
    calculation_steps: tuple[str, ...]
    generated_at: datetime


def calculate_rsi_momentum_reference(
    series: HistoricalPriceSeries,
    configuration: MomentumReferenceConfiguration,
    generated_at: datetime | None = None,
) -> RsiMomentumReference:
    generated = datetime.now(timezone.utc) if generated_at is None else generated_at
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    if not configuration.enabled:
        return _unavailable(series.symbol, configuration, generated, "Momentum reference is disabled.")
    rows, price_field, warnings = _valid_rows(series.rows, configuration)
    if len(rows) < configuration.minimum_observations or len(rows) < configuration.rsi_period + 1:
        return _result(
            series.symbol,
            MomentumReferenceStatus.INSUFFICIENT_DATA,
            configuration,
            None,
            None,
            None,
            RsiCrossDirection.NOT_AVAILABLE,
            rows[-1].date if rows else None,
            rows[-1].close if rows else None,
            None,
            price_field,
            rows,
            generated,
            tuple(warnings + ["Insufficient valid price observations for RSI."]),
        )
    points = calculate_wilder_rsi(rows, configuration.rsi_period)
    if not points:
        return _unavailable(series.symbol, configuration, generated, "RSI calculation is unavailable.")
    reference = _latest_crossing(points, configuration.neutral_level)
    status = MomentumReferenceStatus.COMPLETE
    if reference is None:
        if not configuration.fallback_to_nearest:
            return _result(
                series.symbol,
                MomentumReferenceStatus.UNAVAILABLE,
                configuration,
                None,
                None,
                None,
                RsiCrossDirection.NOT_AVAILABLE,
                points[-1].date,
                points[-1].close,
                points[-1].rsi,
                price_field,
                rows,
                generated,
                tuple(warnings + ["No RSI neutral-line crossing was found."]),
            )
        reference = min(
            points,
            key=lambda point: (abs(point.rsi - configuration.neutral_level), -point.date.toordinal()),
        )
        direction = RsiCrossDirection.NEAREST_TO_50
        status = MomentumReferenceStatus.FALLBACK
    else:
        direction = reference[1]
        reference = reference[0]
    current = points[-1]
    days_since = sum(1 for point in points if point.date > reference.date)
    absolute_change = current.close - reference.close
    percent_change = absolute_change / reference.close * 100
    return _result(
        series.symbol,
        status,
        configuration,
        reference.date,
        reference.close,
        reference.rsi,
        direction,
        current.date,
        current.close,
        current.rsi,
        price_field,
        rows,
        generated,
        tuple(warnings),
        days_since,
        absolute_change,
        percent_change,
        _price_position(current.close, reference.close),
    )


def calculate_wilder_rsi(rows: tuple[HistoricalPriceRow, ...], period: int) -> tuple[RsiPoint, ...]:
    closes = tuple((row.date, row.close) for row in rows if _positive(row.close))
    if len(closes) < period + 1:
        return ()
    gains = []
    losses = []
    for index in range(1, period + 1):
        delta = closes[index][1] - closes[index - 1][1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    points = [RsiPoint(closes[period][0], closes[period][1], _rsi(average_gain, average_loss))]
    for index in range(period + 1, len(closes)):
        delta = closes[index][1] - closes[index - 1][1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
        points.append(RsiPoint(closes[index][0], closes[index][1], _rsi(average_gain, average_loss)))
    return tuple(points)


def _latest_crossing(
    points: tuple[RsiPoint, ...],
    neutral: float,
) -> tuple[RsiPoint, RsiCrossDirection] | None:
    crossings: list[tuple[RsiPoint, RsiCrossDirection]] = []
    last_non_neutral: float | None = None
    for previous, current in zip(points, points[1:]):
        direction = None
        if previous.rsi < neutral and current.rsi >= neutral:
            direction = RsiCrossDirection.CROSS_ABOVE
        elif previous.rsi > neutral and current.rsi <= neutral:
            direction = RsiCrossDirection.CROSS_BELOW
        elif isclose(previous.rsi, neutral, abs_tol=1e-12):
            if current.rsi > neutral and last_non_neutral is not None and last_non_neutral < neutral:
                direction = RsiCrossDirection.CROSS_ABOVE
            elif current.rsi < neutral and last_non_neutral is not None and last_non_neutral > neutral:
                direction = RsiCrossDirection.CROSS_BELOW
        if direction is not None:
            crossings.append((current, direction))
        if not isclose(current.rsi, neutral, abs_tol=1e-12):
            last_non_neutral = current.rsi
        elif not isclose(previous.rsi, neutral, abs_tol=1e-12):
            last_non_neutral = previous.rsi
    return crossings[-1] if crossings else None


def _valid_rows(
    rows: tuple[HistoricalPriceRow, ...],
    configuration: MomentumReferenceConfiguration,
) -> tuple[tuple[HistoricalPriceRow, ...], PriceField | None, list[str]]:
    adjusted_count = sum(1 for row in rows if _positive(row.adjusted_close))
    close_count = sum(1 for row in rows if _positive(row.close))
    use_adjusted = configuration.prefer_adjusted_close and adjusted_count >= configuration.minimum_observations
    field = PriceField.ADJUSTED_CLOSE if use_adjusted else PriceField.CLOSE
    warnings = [] if use_adjusted else ["Adjusted close was unavailable or insufficient; Close was used."]
    selected = []
    for row in rows:
        value = row.adjusted_close if use_adjusted else row.close
        if _positive(value):
            selected.append(HistoricalPriceRow(row.date, float(value), float(value)))
    if not selected and close_count == 0:
        field = None
    return tuple(sorted(selected, key=lambda item: item.date)), field, warnings


def _result(
    symbol: str,
    status: MomentumReferenceStatus,
    config: MomentumReferenceConfiguration,
    reference_date: date | None,
    reference_price: float | None,
    reference_rsi: float | None,
    direction: RsiCrossDirection,
    current_date: date | None,
    current_price: float | None,
    current_rsi: float | None,
    price_field: PriceField | None,
    rows: tuple[HistoricalPriceRow, ...],
    generated_at: datetime,
    warnings: tuple[str, ...],
    trading_days_since_reference: int | None = None,
    price_change_since_reference: float | None = None,
    price_change_since_reference_pct: float | None = None,
    price_position: MomentumPricePosition = MomentumPricePosition.UNKNOWN,
) -> RsiMomentumReference:
    return RsiMomentumReference(
        symbol=symbol,
        status=status,
        rsi_period=config.rsi_period,
        neutral_level=config.neutral_level,
        reference_date=reference_date,
        reference_price=reference_price,
        reference_rsi=reference_rsi,
        cross_direction=direction,
        current_date=current_date,
        current_price=current_price,
        current_rsi=current_rsi,
        price_field=price_field,
        trading_days_since_reference=trading_days_since_reference,
        price_change_since_reference=price_change_since_reference,
        price_change_since_reference_pct=price_change_since_reference_pct,
        price_position=price_position,
        lookback_start=rows[0].date if rows else None,
        lookback_end=rows[-1].date if rows else None,
        observation_count=len(rows),
        methodology=f"Wilder RSI({config.rsi_period}) neutral-line reference",
        rationale=_rationale(status, direction, price_change_since_reference_pct, price_position),
        warnings=warnings,
        calculation_steps=("Wilder RSI", "Latest neutral-line crossing", "Nearest-to-50 fallback"),
        generated_at=generated_at,
    )


def _unavailable(symbol: str, config: MomentumReferenceConfiguration, generated: datetime, warning: str) -> RsiMomentumReference:
    return _result(
        symbol,
        MomentumReferenceStatus.UNAVAILABLE,
        config,
        None,
        None,
        None,
        RsiCrossDirection.NOT_AVAILABLE,
        None,
        None,
        None,
        None,
        (),
        generated,
        (warning,),
    )


def _rsi(average_gain: float, average_loss: float) -> float:
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    rs = average_gain / average_loss
    return 100 - 100 / (1 + rs)


def _price_position(current: float | None, reference: float | None) -> MomentumPricePosition:
    if not _positive(current) or not _positive(reference):
        return MomentumPricePosition.UNKNOWN
    if isclose(float(current), float(reference), rel_tol=0.0, abs_tol=1e-9):
        return MomentumPricePosition.AT_RSI50_REFERENCE
    return (
        MomentumPricePosition.ABOVE_RSI50_REFERENCE
        if float(current) > float(reference)
        else MomentumPricePosition.BELOW_RSI50_REFERENCE
    )


def _rationale(
    status: MomentumReferenceStatus,
    direction: RsiCrossDirection,
    change_pct: float | None,
    position: MomentumPricePosition,
) -> str | None:
    if status == MomentumReferenceStatus.COMPLETE:
        event = "an upward crossing" if direction == RsiCrossDirection.CROSS_ABOVE else "a downward crossing"
        prefix = f"The latest RSI neutral-line event was {event}."
    elif status == MomentumReferenceStatus.FALLBACK:
        prefix = "No RSI neutral-line crossing was found; the nearest RSI-to-50 row was used."
    else:
        return None
    if change_pct is None:
        return prefix
    relation = "above" if position == MomentumPricePosition.ABOVE_RSI50_REFERENCE else "below"
    return f"{prefix} The current price is {abs(change_pct):.2f}% {relation} the price recorded on that date."


def _positive(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and value > 0
    )
