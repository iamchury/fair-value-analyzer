from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite

from src.yahoo.prices import HistoricalPriceSeries


class SoxxCrossDirection(str, Enum):
    CROSS_ABOVE = "CROSS_ABOVE"
    CROSS_BELOW = "CROSS_BELOW"
    NONE = "NONE"
    UNAVAILABLE = "UNAVAILABLE"


class SoxxSignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


class SoxxSignalStrength(str, Enum):
    INITIAL = "INITIAL"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"
    CAUTION = "CAUTION"
    NONE = "NONE"
    UNAVAILABLE = "UNAVAILABLE"


class SoxxTimingSignal(str, Enum):
    VERY_STRONG_BUY = "VERY_STRONG_BUY"
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL_CAUTION = "SELL_CAUTION"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    VERY_STRONG_SELL = "VERY_STRONG_SELL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


class SoxxTimingStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


SIGNAL_COLOR_KEYS = {
    SoxxTimingSignal.BUY: "BUY_LIGHT_GREEN",
    SoxxTimingSignal.STRONG_BUY: "BUY_MEDIUM_GREEN",
    SoxxTimingSignal.VERY_STRONG_BUY: "BUY_DARK_GREEN",
    SoxxTimingSignal.SELL_CAUTION: "SELL_WARNING_RED",
    SoxxTimingSignal.SELL: "SELL_LIGHT_RED",
    SoxxTimingSignal.STRONG_SELL: "SELL_MEDIUM_RED",
    SoxxTimingSignal.VERY_STRONG_SELL: "SELL_DARK_RED",
    SoxxTimingSignal.NEUTRAL: "NEUTRAL_GRAY",
    SoxxTimingSignal.INSUFFICIENT_DATA: "MUTED_GRAY",
    SoxxTimingSignal.ERROR: "ERROR_RED",
}


@dataclass(frozen=True)
class SoxxTimingConfiguration:
    symbol: str = "SOXX"
    period: str = "2y"
    interval: str = "1d"
    minimum_observations: int = 60
    price_field_preference: tuple[str, ...] = ("Adj Close", "Close")
    fast_period: int = 5
    initial_period: int = 10
    strong_period: int = 15
    very_strong_period: int = 20
    long_period: int = 50
    confirmation_days: int = 1
    completed_trading_day_only: bool = True
    convergence_enabled: bool = True
    convergence_periods: tuple[int, ...] = (5, 10, 15, 20)
    convergence_max_spread_pct: float = 1.5
    prior_high_lookback_trading_days: int = 252
    prior_high_exclude_current_day: bool = True
    sell_caution_drawdown_pct: float = -10.0
    strong_buy_drawdown_pct: float = -30.0
    display_enabled: bool = True
    show_chart: bool = True
    show_signal_history: bool = True
    signal_history_days: int = 120
    default_chart_period: str = "6m"
    show_prior_high: bool = True
    show_drawdown: bool = True
    show_moving_averages: bool = True
    show_all_crosses: bool = True


@dataclass(frozen=True)
class SoxxMovingAverageCross:
    fast_period: int
    slow_period: int
    direction: SoxxCrossDirection
    event_date: date | None
    fast_previous: float | None
    slow_previous: float | None
    fast_current: float | None
    slow_current: float | None


@dataclass(frozen=True)
class SoxxTimingDailyPoint:
    date: date
    close: float
    ma5: float | None
    ma10: float | None
    ma15: float | None
    ma20: float | None
    ma50: float | None
    prior_high_price: float | None
    prior_high_date: date | None
    drawdown_pct: float | None
    short_ma_spread_amount: float | None
    short_ma_spread_pct: float | None
    short_ma_converged: bool
    ma5_ma10_cross: SoxxMovingAverageCross
    ma5_ma15_cross: SoxxMovingAverageCross
    ma5_ma20_cross: SoxxMovingAverageCross
    primary_signal: SoxxTimingSignal
    active_conditions: tuple[SoxxTimingSignal, ...]


@dataclass(frozen=True)
class SoxxTimingEvent:
    date: date
    close: float
    ma5: float | None
    ma10: float | None
    ma15: float | None
    ma20: float | None
    ma50: float | None
    prior_high: float | None
    drawdown_pct: float | None
    crossed_average: int | None
    cross_direction: SoxxCrossDirection
    signal: SoxxTimingSignal
    active_conditions: tuple[SoxxTimingSignal, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class SoxxTimingResult:
    symbol: str
    as_of_date: date | None
    current_price: float | None
    price_field: str | None
    ma5: float | None
    ma10: float | None
    ma15: float | None
    ma20: float | None
    ma50: float | None
    prior_high_price: float | None
    prior_high_date: date | None
    drawdown_amount: float | None
    drawdown_pct: float | None
    short_ma_spread_amount: float | None
    short_ma_spread_pct: float | None
    short_ma_converged: bool
    ma5_ma10_cross: SoxxMovingAverageCross
    ma5_ma15_cross: SoxxMovingAverageCross
    ma5_ma20_cross: SoxxMovingAverageCross
    bullish_cross_levels: tuple[int, ...]
    bearish_cross_levels: tuple[int, ...]
    short_cluster_above_ma50: bool
    short_cluster_below_ma50: bool
    ma5_below_ma50: bool
    ma15_below_ma50: bool
    ma20_below_ma50: bool
    primary_signal: SoxxTimingSignal
    active_conditions: tuple[SoxxTimingSignal, ...]
    signal_direction: SoxxSignalDirection
    signal_strength: SoxxSignalStrength
    signal_color_key: str
    status: SoxxTimingStatus
    confidence: str
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    observation_count: int
    lookback_start: date | None
    lookback_end: date | None
    daily_points: tuple[SoxxTimingDailyPoint, ...] = ()
    events: tuple[SoxxTimingEvent, ...] = ()


def validate_soxx_timing_config(config: SoxxTimingConfiguration) -> None:
    if config.symbol != "SOXX":
        raise ValueError("symbol must be SOXX for SOXX Timing V1.")
    periods = (
        config.fast_period,
        config.initial_period,
        config.strong_period,
        config.very_strong_period,
        config.long_period,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in periods):
        raise ValueError("moving-average periods must be positive integers.")
    if not periods == tuple(sorted(periods)) or len(set(periods)) != len(periods):
        raise ValueError("moving-average periods must satisfy 5 < 10 < 15 < 20 < 50.")
    if config.confirmation_days < 1:
        raise ValueError("confirmation_days must be at least 1.")
    if config.minimum_observations < config.long_period:
        raise ValueError("minimum_observations must be at least the long moving average period.")
    if config.prior_high_lookback_trading_days < config.long_period:
        raise ValueError("prior-high lookback must be at least the long moving average period.")
    _finite_non_negative("convergence_max_spread_pct", config.convergence_max_spread_pct)
    _finite_percent("sell_caution_drawdown_pct", config.sell_caution_drawdown_pct)
    _finite_percent("strong_buy_drawdown_pct", config.strong_buy_drawdown_pct)
    if config.strong_buy_drawdown_pct >= config.sell_caution_drawdown_pct:
        raise ValueError("strong-buy drawdown threshold must be more negative than sell-caution threshold.")
    if config.default_chart_period not in {"3m", "6m", "1y", "2y"}:
        raise ValueError("default_chart_period must be one of 3m, 6m, 1y, 2y.")


def calculate_soxx_timing(
    series: HistoricalPriceSeries,
    config: SoxxTimingConfiguration = SoxxTimingConfiguration(),
) -> SoxxTimingResult:
    validate_soxx_timing_config(config)
    if series.symbol != config.symbol:
        raise ValueError("SOXX Timing V1 requires SOXX price history.")
    prices, price_field, warnings = _select_prices(series, config)
    if len(prices) < config.minimum_observations:
        return _insufficient_result(config, len(prices), price_field, warnings)

    dates = [item[0] for item in prices]
    closes = [item[1] for item in prices]
    ma_by_period = {
        period: _moving_average(closes, period)
        for period in (
            config.fast_period,
            config.initial_period,
            config.strong_period,
            config.very_strong_period,
            config.long_period,
        )
    }
    prior_highs = _prior_highs(dates, closes, config.prior_high_lookback_trading_days)
    daily: list[SoxxTimingDailyPoint] = []
    events: list[SoxxTimingEvent] = []
    previous_sell_caution = False
    for index, (point_date, close) in enumerate(prices):
        point = _classify_point(index, dates, closes, ma_by_period, prior_highs, config)
        daily.append(point)
        if _is_event(point, previous_sell_caution):
            events.append(_event_from_point(point, config))
        previous_sell_caution = SoxxTimingSignal.SELL_CAUTION in point.active_conditions

    latest = daily[-1]
    result = _result_from_latest(config, latest, len(prices), dates[0], dates[-1], price_field, warnings)
    return SoxxTimingResult(
        **{
            **result.__dict__,
            "daily_points": tuple(daily),
            "events": tuple(
                event
                for event in events
                if (dates[-1] - event.date).days <= config.signal_history_days * 2
            ),
        }
    )


def _classify_point(
    index: int,
    dates: list[date],
    closes: list[float],
    ma_by_period: dict[int, list[float | None]],
    prior_highs: list[tuple[float | None, date | None]],
    config: SoxxTimingConfiguration,
) -> SoxxTimingDailyPoint:
    values = {period: ma_by_period[period][index] for period in ma_by_period}
    prior_high, prior_high_date = prior_highs[index]
    drawdown_pct = None if prior_high is None else (closes[index] / prior_high - 1.0) * 100
    crosses = {
        period: _cross(index, config.fast_period, period, ma_by_period, dates)
        for period in (config.initial_period, config.strong_period, config.very_strong_period)
    }
    short_values = [values[period] for period in config.convergence_periods]
    complete = all(value is not None for value in [*short_values, values[config.long_period]])
    spread_amount = None
    spread_pct = None
    converged = False
    if complete:
        spread_amount = max(short_values) - min(short_values)  # type: ignore[arg-type]
        spread_pct = spread_amount / closes[index] * 100
        converged = config.convergence_enabled and spread_pct <= config.convergence_max_spread_pct
    active, primary = _signals(
        crosses,
        values,
        drawdown_pct,
        converged,
        config,
    )
    return SoxxTimingDailyPoint(
        date=dates[index],
        close=closes[index],
        ma5=values[5],
        ma10=values[10],
        ma15=values[15],
        ma20=values[20],
        ma50=values[50],
        prior_high_price=prior_high,
        prior_high_date=prior_high_date,
        drawdown_pct=drawdown_pct,
        short_ma_spread_amount=spread_amount,
        short_ma_spread_pct=spread_pct,
        short_ma_converged=converged,
        ma5_ma10_cross=crosses[config.initial_period],
        ma5_ma15_cross=crosses[config.strong_period],
        ma5_ma20_cross=crosses[config.very_strong_period],
        primary_signal=primary,
        active_conditions=tuple(active),
    )


def _signals(
    crosses: dict[int, SoxxMovingAverageCross],
    values: dict[int, float | None],
    drawdown_pct: float | None,
    converged: bool,
    config: SoxxTimingConfiguration,
) -> tuple[list[SoxxTimingSignal], SoxxTimingSignal]:
    bullish = [period for period, cross in crosses.items() if cross.direction == SoxxCrossDirection.CROSS_ABOVE]
    bearish = [period for period, cross in crosses.items() if cross.direction == SoxxCrossDirection.CROSS_BELOW]
    if bullish and bearish:
        return [SoxxTimingSignal.ERROR], SoxxTimingSignal.ERROR
    active: list[SoxxTimingSignal] = []
    if drawdown_pct is not None and drawdown_pct <= config.sell_caution_drawdown_pct + 1e-9:
        active.append(SoxxTimingSignal.SELL_CAUTION)
    if bullish:
        active.extend(_buy_signals(bullish))
        if _deep_drawdown_recovery(values, drawdown_pct, bullish, config):
            if SoxxTimingSignal.STRONG_BUY not in active:
                active.append(SoxxTimingSignal.STRONG_BUY)
        return active, _strongest_buy(active)
    if bearish:
        active.extend(_sell_signals(bearish))
        if _convergence_sell(values, converged, bearish):
            if SoxxTimingSignal.STRONG_SELL not in active:
                active.append(SoxxTimingSignal.STRONG_SELL)
        return active, _strongest_sell(active)
    if active:
        return active, SoxxTimingSignal.SELL_CAUTION
    return active, SoxxTimingSignal.NEUTRAL


def _buy_signals(levels: list[int]) -> list[SoxxTimingSignal]:
    signals = []
    if 10 in levels:
        signals.append(SoxxTimingSignal.BUY)
    if 15 in levels:
        signals.append(SoxxTimingSignal.STRONG_BUY)
    if 20 in levels:
        signals.append(SoxxTimingSignal.VERY_STRONG_BUY)
    return signals


def _sell_signals(levels: list[int]) -> list[SoxxTimingSignal]:
    signals = []
    if 10 in levels:
        signals.append(SoxxTimingSignal.SELL)
    if 15 in levels:
        signals.append(SoxxTimingSignal.STRONG_SELL)
    if 20 in levels:
        signals.append(SoxxTimingSignal.VERY_STRONG_SELL)
    return signals


def _strongest_buy(active: list[SoxxTimingSignal]) -> SoxxTimingSignal:
    for signal in (SoxxTimingSignal.VERY_STRONG_BUY, SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.BUY):
        if signal in active:
            return signal
    return SoxxTimingSignal.NEUTRAL


def _strongest_sell(active: list[SoxxTimingSignal]) -> SoxxTimingSignal:
    for signal in (SoxxTimingSignal.VERY_STRONG_SELL, SoxxTimingSignal.STRONG_SELL, SoxxTimingSignal.SELL):
        if signal in active:
            return signal
    return SoxxTimingSignal.SELL_CAUTION if SoxxTimingSignal.SELL_CAUTION in active else SoxxTimingSignal.NEUTRAL


def _deep_drawdown_recovery(
    values: dict[int, float | None],
    drawdown_pct: float | None,
    bullish: list[int],
    config: SoxxTimingConfiguration,
) -> bool:
    required = [values[5], values[15], values[20], values[50]]
    return (
        drawdown_pct is not None
        and drawdown_pct <= config.strong_buy_drawdown_pct + 1e-9
        and all(value is not None for value in required)
        and values[5] < values[50]
        and values[15] < values[50]
        and values[20] < values[50]
        and 15 in bullish
    )


def _convergence_sell(values: dict[int, float | None], converged: bool, bearish: list[int]) -> bool:
    short_values = [values[5], values[10], values[15], values[20]]
    return (
        converged
        and all(value is not None for value in [*short_values, values[50]])
        and values[50] < min(short_values)  # type: ignore[arg-type]
        and 15 in bearish
    )


def _cross(
    index: int,
    fast_period: int,
    slow_period: int,
    ma_by_period: dict[int, list[float | None]],
    dates: list[date],
) -> SoxxMovingAverageCross:
    if index == 0:
        return _unavailable_cross(fast_period, slow_period)
    fast_previous = ma_by_period[fast_period][index - 1]
    slow_previous = ma_by_period[slow_period][index - 1]
    fast_current = ma_by_period[fast_period][index]
    slow_current = ma_by_period[slow_period][index]
    if None in (fast_previous, slow_previous, fast_current, slow_current):
        return _unavailable_cross(fast_period, slow_period)
    if fast_previous <= slow_previous and fast_current > slow_current:  # type: ignore[operator]
        direction = SoxxCrossDirection.CROSS_ABOVE
    elif fast_previous >= slow_previous and fast_current < slow_current:  # type: ignore[operator]
        direction = SoxxCrossDirection.CROSS_BELOW
    else:
        direction = SoxxCrossDirection.NONE
    return SoxxMovingAverageCross(
        fast_period,
        slow_period,
        direction,
        dates[index] if direction != SoxxCrossDirection.NONE else None,
        fast_previous,
        slow_previous,
        fast_current,
        slow_current,
    )


def _unavailable_cross(fast_period: int, slow_period: int) -> SoxxMovingAverageCross:
    return SoxxMovingAverageCross(fast_period, slow_period, SoxxCrossDirection.UNAVAILABLE, None, None, None, None, None)


def _result_from_latest(
    config: SoxxTimingConfiguration,
    latest: SoxxTimingDailyPoint,
    observation_count: int,
    lookback_start: date,
    lookback_end: date,
    price_field: str,
    warnings: tuple[str, ...],
) -> SoxxTimingResult:
    crosses = {
        10: latest.ma5_ma10_cross,
        15: latest.ma5_ma15_cross,
        20: latest.ma5_ma20_cross,
    }
    values = [latest.ma5, latest.ma10, latest.ma15, latest.ma20]
    short_cluster_above = all(value is not None and latest.ma50 is not None and value > latest.ma50 for value in values)
    short_cluster_below = all(value is not None and latest.ma50 is not None and value < latest.ma50 for value in values)
    drawdown_amount = None if latest.prior_high_price is None else latest.close - latest.prior_high_price
    return SoxxTimingResult(
        symbol=config.symbol,
        as_of_date=latest.date,
        current_price=latest.close,
        price_field=price_field,
        ma5=latest.ma5,
        ma10=latest.ma10,
        ma15=latest.ma15,
        ma20=latest.ma20,
        ma50=latest.ma50,
        prior_high_price=latest.prior_high_price,
        prior_high_date=latest.prior_high_date,
        drawdown_amount=drawdown_amount,
        drawdown_pct=latest.drawdown_pct,
        short_ma_spread_amount=latest.short_ma_spread_amount,
        short_ma_spread_pct=latest.short_ma_spread_pct,
        short_ma_converged=latest.short_ma_converged,
        ma5_ma10_cross=crosses[10],
        ma5_ma15_cross=crosses[15],
        ma5_ma20_cross=crosses[20],
        bullish_cross_levels=tuple(period for period, cross in crosses.items() if cross.direction == SoxxCrossDirection.CROSS_ABOVE),
        bearish_cross_levels=tuple(period for period, cross in crosses.items() if cross.direction == SoxxCrossDirection.CROSS_BELOW),
        short_cluster_above_ma50=short_cluster_above,
        short_cluster_below_ma50=short_cluster_below,
        ma5_below_ma50=latest.ma5 is not None and latest.ma50 is not None and latest.ma5 < latest.ma50,
        ma15_below_ma50=latest.ma15 is not None and latest.ma50 is not None and latest.ma15 < latest.ma50,
        ma20_below_ma50=latest.ma20 is not None and latest.ma50 is not None and latest.ma20 < latest.ma50,
        primary_signal=latest.primary_signal,
        active_conditions=latest.active_conditions,
        signal_direction=_direction(latest.primary_signal),
        signal_strength=_strength(latest.primary_signal),
        signal_color_key=SIGNAL_COLOR_KEYS[latest.primary_signal],
        status=SoxxTimingStatus.ERROR if latest.primary_signal == SoxxTimingSignal.ERROR else SoxxTimingStatus.COMPLETE,
        confidence="HIGH" if latest.primary_signal != SoxxTimingSignal.ERROR else "LOW",
        rationale=_rationale(latest.primary_signal, latest.active_conditions),
        warnings=warnings,
        observation_count=observation_count,
        lookback_start=lookback_start,
        lookback_end=lookback_end,
    )

def _direction(signal: SoxxTimingSignal) -> SoxxSignalDirection:
    if signal in {SoxxTimingSignal.BUY, SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.VERY_STRONG_BUY}:
        return SoxxSignalDirection.BUY
    if signal in {SoxxTimingSignal.SELL, SoxxTimingSignal.STRONG_SELL, SoxxTimingSignal.VERY_STRONG_SELL, SoxxTimingSignal.SELL_CAUTION}:
        return SoxxSignalDirection.SELL
    if signal == SoxxTimingSignal.NEUTRAL:
        return SoxxSignalDirection.NEUTRAL
    return SoxxSignalDirection.UNAVAILABLE


def _strength(signal: SoxxTimingSignal) -> SoxxSignalStrength:
    if signal in {SoxxTimingSignal.BUY, SoxxTimingSignal.SELL}:
        return SoxxSignalStrength.INITIAL
    if signal in {SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.STRONG_SELL}:
        return SoxxSignalStrength.STRONG
    if signal in {SoxxTimingSignal.VERY_STRONG_BUY, SoxxTimingSignal.VERY_STRONG_SELL}:
        return SoxxSignalStrength.VERY_STRONG
    if signal == SoxxTimingSignal.SELL_CAUTION:
        return SoxxSignalStrength.CAUTION
    if signal == SoxxTimingSignal.NEUTRAL:
        return SoxxSignalStrength.NONE
    return SoxxSignalStrength.UNAVAILABLE


def _rationale(signal: SoxxTimingSignal, active: tuple[SoxxTimingSignal, ...]) -> tuple[str, ...]:
    text = {
        SoxxTimingSignal.BUY: "MA5 crossed above MA10. This is an initial SOXX buy-timing signal.",
        SoxxTimingSignal.STRONG_BUY: "MA5 crossed above MA15. This is a strong SOXX buy-timing signal.",
        SoxxTimingSignal.VERY_STRONG_BUY: "MA5 crossed above MA20. This is a very strong SOXX buy-timing signal.",
        SoxxTimingSignal.SELL: "MA5 crossed below MA10. This is an initial SOXX sell-timing signal.",
        SoxxTimingSignal.STRONG_SELL: "MA5 crossed below MA15. This is a strong SOXX sell-timing signal.",
        SoxxTimingSignal.VERY_STRONG_SELL: "MA5 crossed below MA20. This is a very strong SOXX sell-timing signal.",
        SoxxTimingSignal.SELL_CAUTION: "SOXX is at least 10% below its rolling prior high. Risk reduction and sell discipline should be reviewed.",
        SoxxTimingSignal.NEUTRAL: "No new SOXX moving-average crossover signal is active.",
        SoxxTimingSignal.ERROR: "Conflicting SOXX timing signals were detected.",
        SoxxTimingSignal.INSUFFICIENT_DATA: "SOXX timing has insufficient completed daily observations.",
    }
    result = [text[signal]]
    if SoxxTimingSignal.SELL_CAUTION in active and signal != SoxxTimingSignal.SELL_CAUTION:
        result.append(text[SoxxTimingSignal.SELL_CAUTION])
    if signal in {SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.VERY_STRONG_BUY} and SoxxTimingSignal.SELL_CAUTION in active:
        result.append("Deep-drawdown recovery conditions are active.")
    return tuple(result)


def _event_from_point(point: SoxxTimingDailyPoint, config: SoxxTimingConfiguration) -> SoxxTimingEvent:
    crossed = None
    direction = SoxxCrossDirection.NONE
    if point.primary_signal in {SoxxTimingSignal.BUY, SoxxTimingSignal.SELL}:
        crossed = 10
    elif point.primary_signal in {SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.STRONG_SELL}:
        crossed = 15
    elif point.primary_signal in {SoxxTimingSignal.VERY_STRONG_BUY, SoxxTimingSignal.VERY_STRONG_SELL}:
        crossed = 20
    if point.primary_signal in {SoxxTimingSignal.BUY, SoxxTimingSignal.STRONG_BUY, SoxxTimingSignal.VERY_STRONG_BUY}:
        direction = SoxxCrossDirection.CROSS_ABOVE
    if point.primary_signal in {SoxxTimingSignal.SELL, SoxxTimingSignal.STRONG_SELL, SoxxTimingSignal.VERY_STRONG_SELL}:
        direction = SoxxCrossDirection.CROSS_BELOW
    return SoxxTimingEvent(
        date=point.date,
        close=point.close,
        ma5=point.ma5,
        ma10=point.ma10,
        ma15=point.ma15,
        ma20=point.ma20,
        ma50=point.ma50,
        prior_high=point.prior_high_price,
        drawdown_pct=point.drawdown_pct,
        crossed_average=crossed,
        cross_direction=direction,
        signal=point.primary_signal,
        active_conditions=point.active_conditions,
        rationale=_rationale(point.primary_signal, point.active_conditions),
    )


def _is_event(point: SoxxTimingDailyPoint, previous_sell_caution: bool) -> bool:
    event_signals = {
        SoxxTimingSignal.BUY,
        SoxxTimingSignal.STRONG_BUY,
        SoxxTimingSignal.VERY_STRONG_BUY,
        SoxxTimingSignal.SELL,
        SoxxTimingSignal.STRONG_SELL,
        SoxxTimingSignal.VERY_STRONG_SELL,
    }
    return point.primary_signal in event_signals or (
        point.primary_signal == SoxxTimingSignal.SELL_CAUTION and not previous_sell_caution
    )


def _moving_average(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
        else:
            window = values[index + 1 - period : index + 1]
            result.append(sum(window) / period)
    return result


def _prior_highs(
    dates: list[date],
    closes: list[float],
    lookback: int,
) -> list[tuple[float | None, date | None]]:
    result = []
    for index in range(len(closes)):
        start = max(0, index - lookback)
        prior = closes[start:index]
        prior_dates = dates[start:index]
        if not prior:
            result.append((None, None))
            continue
        high = max(prior)
        high_index = len(prior) - 1 - prior[::-1].index(high)
        result.append((high, prior_dates[high_index]))
    return result


def _select_prices(
    series: HistoricalPriceSeries,
    config: SoxxTimingConfiguration,
) -> tuple[list[tuple[date, float]], str, tuple[str, ...]]:
    warnings: list[str] = []
    for field in config.price_field_preference:
        selected = []
        for row in series.rows:
            value = row.adjusted_close if field == "Adj Close" else row.close
            if value is not None and isfinite(value) and value > 0:
                selected.append((row.date, float(value)))
        if selected:
            if len(selected) != len(series.rows):
                warnings.append(f"{field} skipped invalid or missing rows.")
            return selected, field, tuple(warnings)
    return [], config.price_field_preference[0], ("No valid SOXX price rows were available.",)


def _insufficient_result(
    config: SoxxTimingConfiguration,
    observation_count: int,
    price_field: str | None,
    warnings: tuple[str, ...],
) -> SoxxTimingResult:
    cross = _unavailable_cross(config.fast_period, config.initial_period)
    return SoxxTimingResult(
        symbol=config.symbol,
        as_of_date=None,
        current_price=None,
        price_field=price_field,
        ma5=None,
        ma10=None,
        ma15=None,
        ma20=None,
        ma50=None,
        prior_high_price=None,
        prior_high_date=None,
        drawdown_amount=None,
        drawdown_pct=None,
        short_ma_spread_amount=None,
        short_ma_spread_pct=None,
        short_ma_converged=False,
        ma5_ma10_cross=cross,
        ma5_ma15_cross=_unavailable_cross(config.fast_period, config.strong_period),
        ma5_ma20_cross=_unavailable_cross(config.fast_period, config.very_strong_period),
        bullish_cross_levels=(),
        bearish_cross_levels=(),
        short_cluster_above_ma50=False,
        short_cluster_below_ma50=False,
        ma5_below_ma50=False,
        ma15_below_ma50=False,
        ma20_below_ma50=False,
        primary_signal=SoxxTimingSignal.INSUFFICIENT_DATA,
        active_conditions=(),
        signal_direction=SoxxSignalDirection.UNAVAILABLE,
        signal_strength=SoxxSignalStrength.UNAVAILABLE,
        signal_color_key=SIGNAL_COLOR_KEYS[SoxxTimingSignal.INSUFFICIENT_DATA],
        status=SoxxTimingStatus.INSUFFICIENT_DATA,
        confidence="LOW",
        rationale=_rationale(SoxxTimingSignal.INSUFFICIENT_DATA, ()),
        warnings=warnings,
        observation_count=observation_count,
        lookback_start=None,
        lookback_end=None,
    )


def _finite_percent(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def _finite_non_negative(name: str, value: float) -> None:
    _finite_percent(name, value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
