from __future__ import annotations

from dataclasses import dataclass

from src.analysis.soxx_timing import (
    EMA50Trend,
    EMA50TurnEvent,
    SoxxTimingConfiguration,
    SoxxTimingResult,
    SoxxTimingSignal,
    SoxxTimingStatus,
    calculate_soxx_timing,
)
from src.config.soxx_timing import load_soxx_timing_configuration
from src.yahoo.prices import download_daily_price_history


class SoxxTimingServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoxxTimingServiceResult:
    timing: SoxxTimingResult


def analyze_soxx_timing(config: SoxxTimingConfiguration) -> SoxxTimingResult:
    try:
        history = download_daily_price_history(
            config.symbol,
            period=config.period,
            interval=config.interval,
        )
        return calculate_soxx_timing(history, config)
    except Exception as exc:
        return SoxxTimingResult(
            symbol=config.symbol,
            as_of_date=None,
            current_price=None,
            price_field=None,
            moving_average_type=config.moving_average_type,
            exponential_adjust=config.exponential_adjust,
            chart_trading_days=config.chart_trading_days,
            ma5=None,
            ma10=None,
            ma15=None,
            ma20=None,
            ma50=None,
            ema50_slope=None,
            previous_ema50_slope=None,
            ema50_trend=EMA50Trend.UNAVAILABLE,
            ema50_turn_event=EMA50TurnEvent.UNAVAILABLE,
            latest_ema50_turn_date=None,
            latest_ema50_turn_event=EMA50TurnEvent.UNAVAILABLE,
            prior_high_price=None,
            prior_high_date=None,
            drawdown_amount=None,
            drawdown_pct=None,
            short_ma_spread_amount=None,
            short_ma_spread_pct=None,
            short_ma_converged=False,
            ma5_ma10_cross=_unavailable_cross(5, 10),
            ma5_ma15_cross=_unavailable_cross(5, 15),
            ma5_ma20_cross=_unavailable_cross(5, 20),
            bullish_cross_levels=(),
            bearish_cross_levels=(),
            short_cluster_above_ma50=False,
            short_cluster_below_ma50=False,
            ma5_below_ma50=False,
            ma15_below_ma50=False,
            ma20_below_ma50=False,
            primary_signal=SoxxTimingSignal.ERROR,
            active_conditions=(),
            signal_direction=_unavailable_direction(),
            signal_strength=_unavailable_strength(),
            signal_color_key="ERROR_RED",
            status=SoxxTimingStatus.ERROR,
            confidence="LOW",
            rationale=("SOXX timing analysis failed.",),
            warnings=(str(exc),),
            observation_count=0,
            lookback_start=None,
            lookback_end=None,
        )


def analyze_soxx_timing_from_config_file(
    config_path: str = "config/soxx_timing.yaml",
) -> SoxxTimingResult:
    return analyze_soxx_timing(load_soxx_timing_configuration(config_path))


def _unavailable_cross(fast: int, slow: int):
    from src.analysis.soxx_timing import SoxxCrossDirection, SoxxMovingAverageCross

    return SoxxMovingAverageCross(fast, slow, SoxxCrossDirection.UNAVAILABLE, None, None, None, None, None)


def _unavailable_direction():
    from src.analysis.soxx_timing import SoxxSignalDirection

    return SoxxSignalDirection.UNAVAILABLE


def _unavailable_strength():
    from src.analysis.soxx_timing import SoxxSignalStrength

    return SoxxSignalStrength.UNAVAILABLE
