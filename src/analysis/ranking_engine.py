from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any

from src.analysis.agreement_engine import AgreementLevel
from src.analysis.fair_value_range import FairValueRangeStatus
from src.analysis.momentum_reference import (
    MomentumReferenceStatus,
    PriceField,
    RsiCrossDirection,
    RsiMomentumReference,
)
from src.analysis.recommendation_v2 import (
    EvidenceQuality,
    MomentumCondition,
    RecommendationV2Decision,
    RecommendationV2Result,
    RecommendationV2Status,
    ValuationCondition,
)
from src.config.ranking_engine import RankingEngineConfiguration


class RankingCategory(str, Enum):
    TOP_OPPORTUNITY = "TOP_OPPORTUNITY"
    ATTRACTIVE = "ATTRACTIVE"
    WATCHLIST = "WATCHLIST"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    AVOID = "AVOID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class StockRankingStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    DISABLED = "DISABLED"
    INSUFFICIENT = "INSUFFICIENT"


class MomentumSentimentPosition(str, Enum):
    WELL_ABOVE_NEUTRAL_REFERENCE = "WELL_ABOVE_NEUTRAL_REFERENCE"
    ABOVE_NEUTRAL_REFERENCE = "ABOVE_NEUTRAL_REFERENCE"
    NEAR_NEUTRAL_REFERENCE = "NEAR_NEUTRAL_REFERENCE"
    BELOW_NEUTRAL_REFERENCE = "BELOW_NEUTRAL_REFERENCE"
    WELL_BELOW_NEUTRAL_REFERENCE = "WELL_BELOW_NEUTRAL_REFERENCE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class StockRankingEntry:
    rank: int
    symbol: str
    company_name: str | None
    total_score: float
    normalized_score: float
    category: RankingCategory
    eligible: bool
    recommendation_v2: RecommendationV2Decision | None
    valuation_condition: ValuationCondition | None
    evidence_quality: EvidenceQuality | None
    agreement: AgreementLevel | None
    momentum: MomentumCondition | None
    current_price: float | None
    base_value: float | None
    current_vs_base_pct: float | None
    current_rsi: float | None
    rsi_reference_date: date | None
    rsi_reference_price: float | None
    rsi_reference_rsi: float | None
    rsi_cross_direction: RsiCrossDirection | None
    current_vs_rsi_reference_amount: float | None
    current_vs_rsi_reference_pct: float | None
    momentum_reference_status: MomentumReferenceStatus | None
    momentum_reference_price_field: PriceField | None
    momentum_reference_trading_days: int | None
    momentum_sentiment_position: MomentumSentimentPosition
    valuation_score: float
    recommendation_score: float
    agreement_score: float
    evidence_score: float
    momentum_score: float
    penalty: float
    warnings: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class StockRankingResult:
    status: StockRankingStatus
    entries: tuple[StockRankingEntry, ...]
    top_symbol: str | None
    top_score: float | None
    successful_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    generated_at: datetime


def rank_stocks(
    analysis_results: tuple[Any, ...],
    failures: tuple[Any, ...],
    configuration: RankingEngineConfiguration,
    generated_at: datetime | None = None,
) -> StockRankingResult:
    generated = datetime.now(timezone.utc) if generated_at is None else generated_at
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    successful_symbols = tuple(_symbol(result) for result in analysis_results)
    failed_symbols = tuple(getattr(failure, "symbol", "") for failure in failures)
    if not configuration.enabled:
        return StockRankingResult(
            status=StockRankingStatus.DISABLED,
            entries=(),
            top_symbol=None,
            top_score=None,
            successful_symbols=successful_symbols,
            failed_symbols=failed_symbols,
            generated_at=generated,
        )

    entries = tuple(
        entry
        for entry in (_entry(result, configuration) for result in analysis_results)
        if entry is not None
    )
    sorted_entries = sorted(entries, key=_sort_key)
    ranked = tuple(
        StockRankingEntry(**{**entry.__dict__, "rank": index})
        for index, entry in enumerate(sorted_entries, start=1)
    )
    eligible_entries = tuple(entry for entry in ranked if entry.eligible)
    status = StockRankingStatus.COMPLETE
    if not eligible_entries:
        status = StockRankingStatus.INSUFFICIENT
    elif failures:
        status = StockRankingStatus.PARTIAL
    return StockRankingResult(
        status=status,
        entries=ranked,
        top_symbol=None if not eligible_entries else eligible_entries[0].symbol,
        top_score=None if not eligible_entries else eligible_entries[0].normalized_score,
        successful_symbols=successful_symbols,
        failed_symbols=failed_symbols,
        generated_at=generated,
    )


def _entry(result: Any, configuration: RankingEngineConfiguration) -> StockRankingEntry | None:
    recommendation = getattr(result, "recommendation_v2", None)
    if not isinstance(recommendation, RecommendationV2Result):
        return None
    valuation_score = _VALUATION_SCORES.get(recommendation.valuation_condition, -100)
    recommendation_score = _RECOMMENDATION_SCORES.get(recommendation.decision, -100)
    evidence_score = _EVIDENCE_SCORES.get(recommendation.evidence_quality, -100)
    agreement_score = _AGREEMENT_SCORES.get(recommendation.core_agreement, -75)
    momentum_score = _MOMENTUM_SCORES.get(recommendation.momentum_condition, -30)
    weighted_sum = (
        valuation_score * configuration.weights.valuation
        + recommendation_score * configuration.weights.recommendation
        + evidence_score * configuration.weights.evidence
        + agreement_score * configuration.weights.agreement
        + momentum_score * configuration.weights.momentum
    )
    normalized = weighted_sum / configuration.weights.total
    distance_bonus = _distance_bonus(recommendation.current_vs_base_pct)
    penalty, penalty_reasons = _penalty(result, recommendation)
    total = normalized + distance_bonus - penalty
    eligible, eligibility_reasons = _eligibility(result, recommendation)
    momentum_reference = getattr(result, "momentum_reference", None)
    momentum_fields = _momentum_fields(momentum_reference, configuration)
    return StockRankingEntry(
        rank=0,
        symbol=recommendation.symbol,
        company_name=getattr(getattr(result, "company", None), "company_name", None),
        total_score=total,
        normalized_score=total,
        category=_category(total, eligible),
        eligible=eligible,
        recommendation_v2=recommendation.decision,
        valuation_condition=recommendation.valuation_condition,
        evidence_quality=recommendation.evidence_quality,
        agreement=recommendation.core_agreement,
        momentum=recommendation.momentum_condition,
        current_price=recommendation.current_price,
        base_value=recommendation.base_value,
        current_vs_base_pct=recommendation.current_vs_base_pct,
        current_rsi=momentum_fields["current_rsi"],
        rsi_reference_date=momentum_fields["rsi_reference_date"],
        rsi_reference_price=momentum_fields["rsi_reference_price"],
        rsi_reference_rsi=momentum_fields["rsi_reference_rsi"],
        rsi_cross_direction=momentum_fields["rsi_cross_direction"],
        current_vs_rsi_reference_amount=momentum_fields["current_vs_rsi_reference_amount"],
        current_vs_rsi_reference_pct=momentum_fields["current_vs_rsi_reference_pct"],
        momentum_reference_status=momentum_fields["momentum_reference_status"],
        momentum_reference_price_field=momentum_fields["momentum_reference_price_field"],
        momentum_reference_trading_days=momentum_fields["momentum_reference_trading_days"],
        momentum_sentiment_position=momentum_fields["momentum_sentiment_position"],
        valuation_score=valuation_score,
        recommendation_score=recommendation_score,
        agreement_score=agreement_score,
        evidence_score=evidence_score,
        momentum_score=momentum_score,
        penalty=penalty,
        warnings=tuple(dict.fromkeys((*recommendation.warnings, *penalty_reasons, *eligibility_reasons))),
        rationale=_rationale(recommendation, total, distance_bonus, penalty),
    )


def _distance_bonus(value: float | None) -> float:
    if not _finite(value):
        return 0.0
    return min(15.0, max(-15.0, -float(value) * 0.20))


def _penalty(result: Any, recommendation: RecommendationV2Result) -> tuple[float, tuple[str, ...]]:
    penalty = 0.0
    reasons: list[str] = []
    if recommendation.status == RecommendationV2Status.PARTIAL:
        penalty += 8.0
        reasons.append("Recommendation V2 is partial.")
    if recommendation.momentum_condition == MomentumCondition.UNAVAILABLE:
        penalty += 5.0
        reasons.append("Momentum is missing.")
    if recommendation.core_agreement == AgreementLevel.CONFLICTED:
        penalty += 12.0
        reasons.append("Core agreement is conflicted.")
    minimum = 2
    if recommendation.intrinsic_model_count < minimum:
        penalty += 15.0
        reasons.append("Intrinsic model count is insufficient.")
    fair_range = getattr(result, "fair_value_range", None)
    if getattr(fair_range, "status", None) == FairValueRangeStatus.PARTIAL:
        penalty += 8.0
        reasons.append("Fair value range is partial.")
    return penalty, tuple(reasons)


def _eligibility(result: Any, recommendation: RecommendationV2Result) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if recommendation.decision == RecommendationV2Decision.INSUFFICIENT_DATA:
        reasons.append("Recommendation V2 is insufficient.")
    if recommendation.evidence_quality == EvidenceQuality.INSUFFICIENT:
        reasons.append("Evidence quality is insufficient.")
    if _analysis_status(result) == "ERROR":
        reasons.append("Analysis status is ERROR.")
    if not _finite(recommendation.base_value) or float(recommendation.base_value) <= 0:
        reasons.append("Fair value range base value is unavailable.")
    if recommendation.status not in (RecommendationV2Status.COMPLETE, RecommendationV2Status.PARTIAL):
        reasons.append("Recommendation V2 status is not usable.")
    if recommendation.intrinsic_model_count < _MINIMUM_INTRINSIC_MODELS:
        reasons.append("Intrinsic model count is below the required minimum.")
    return not reasons, tuple(reasons)


def _analysis_status(result: Any) -> str | None:
    status = getattr(getattr(result, "valuation", None), "status", None)
    if isinstance(status, Enum):
        return status.value
    return None if status is None else str(status)


def _category(score: float, eligible: bool) -> RankingCategory:
    if not eligible:
        return RankingCategory.INSUFFICIENT_DATA
    if score >= 70:
        return RankingCategory.TOP_OPPORTUNITY
    if score >= 45:
        return RankingCategory.ATTRACTIVE
    if score >= 20:
        return RankingCategory.WATCHLIST
    if score >= -10:
        return RankingCategory.NEUTRAL
    if score >= -40:
        return RankingCategory.CAUTION
    return RankingCategory.AVOID


def _rationale(
    recommendation: RecommendationV2Result,
    score: float,
    distance_bonus: float,
    penalty: float,
) -> tuple[str, ...]:
    lines = [
        f"{recommendation.symbol} ranks from reused Recommendation V2, fair-value range, agreement, and momentum results.",
        f"Final score is {score:.2f} after a valuation-distance adjustment of {distance_bonus:+.2f} and reliability penalty of {penalty:.2f}.",
    ]
    if recommendation.current_vs_base_pct is not None:
        lines.append(f"Current price is {recommendation.current_vs_base_pct:+.2f}% versus base intrinsic value.")
    return tuple(lines)


def momentum_reference_interpretation(entry: StockRankingEntry) -> tuple[str, ...]:
    if entry.momentum_sentiment_position == MomentumSentimentPosition.UNAVAILABLE:
        return (
            f"{entry.symbol} does not have a usable RSI 50 momentum neutral reference.",
            _REFERENCE_LIMITATION,
        )
    pct = entry.current_vs_rsi_reference_pct
    direction = entry.rsi_cross_direction
    percent_text = "an unknown amount" if pct is None else f"{abs(pct):.2f}%"
    if entry.momentum_sentiment_position == MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE:
        text = (
            f"{entry.symbol} is trading {percent_text} from its most recent RSI 50 "
            "neutral-reference price."
        )
    elif direction == RsiCrossDirection.CROSS_ABOVE and pct is not None and pct > 0:
        text = (
            f"{entry.symbol} remains {percent_text} above the price where RSI most recently crossed "
            "above the neutral 50 level."
        )
    elif direction == RsiCrossDirection.CROSS_ABOVE:
        text = (
            f"{entry.symbol}'s prior positive RSI transition has failed because price is now "
            f"{percent_text} below its momentum neutral reference price."
        )
    elif direction == RsiCrossDirection.CROSS_BELOW and pct is not None and pct < 0:
        text = (
            f"{entry.symbol} remains {percent_text} below the price where RSI most recently crossed "
            "below the neutral 50 level."
        )
    elif direction == RsiCrossDirection.CROSS_BELOW:
        text = (
            f"{entry.symbol} has recovered {percent_text} above the most recent negative RSI "
            "transition reference."
        )
    elif direction == RsiCrossDirection.NEAREST_TO_50:
        text = (
            f"{entry.symbol} uses the nearest RSI-to-50 observation as a fallback momentum neutral reference."
        )
    else:
        text = f"{entry.symbol} has an RSI 50 momentum neutral reference."
    return (
        text,
        "This reference is a technical sentiment and momentum benchmark.",
        _REFERENCE_LIMITATION,
    )


def classify_momentum_sentiment_position(
    current_vs_reference_pct: object,
    configuration: RankingEngineConfiguration,
) -> MomentumSentimentPosition:
    if not configuration.momentum_reference_display.enabled or not _finite(current_vs_reference_pct):
        return MomentumSentimentPosition.UNAVAILABLE
    value = float(current_vs_reference_pct)
    display = configuration.momentum_reference_display
    if value >= display.well_above_reference_pct:
        return MomentumSentimentPosition.WELL_ABOVE_NEUTRAL_REFERENCE
    if value > display.near_reference_pct:
        return MomentumSentimentPosition.ABOVE_NEUTRAL_REFERENCE
    if value >= -display.near_reference_pct:
        return MomentumSentimentPosition.NEAR_NEUTRAL_REFERENCE
    if value > display.well_below_reference_pct:
        return MomentumSentimentPosition.BELOW_NEUTRAL_REFERENCE
    return MomentumSentimentPosition.WELL_BELOW_NEUTRAL_REFERENCE


def _momentum_fields(
    momentum: object,
    configuration: RankingEngineConfiguration,
) -> dict[str, object]:
    if not isinstance(momentum, RsiMomentumReference):
        sentiment = classify_momentum_sentiment_position(None, configuration)
        return {
            "current_rsi": None,
            "rsi_reference_date": None,
            "rsi_reference_price": None,
            "rsi_reference_rsi": None,
            "rsi_cross_direction": None,
            "current_vs_rsi_reference_amount": None,
            "current_vs_rsi_reference_pct": None,
            "momentum_reference_status": None,
            "momentum_reference_price_field": None,
            "momentum_reference_trading_days": None,
            "momentum_sentiment_position": sentiment,
        }
    pct = momentum.price_change_since_reference_pct
    return {
        "current_rsi": momentum.current_rsi,
        "rsi_reference_date": momentum.reference_date,
        "rsi_reference_price": momentum.reference_price,
        "rsi_reference_rsi": momentum.reference_rsi,
        "rsi_cross_direction": momentum.cross_direction,
        "current_vs_rsi_reference_amount": momentum.price_change_since_reference,
        "current_vs_rsi_reference_pct": pct,
        "momentum_reference_status": momentum.status,
        "momentum_reference_price_field": momentum.price_field,
        "momentum_reference_trading_days": momentum.trading_days_since_reference,
        "momentum_sentiment_position": classify_momentum_sentiment_position(pct, configuration),
    }


def _sort_key(entry: StockRankingEntry) -> tuple[int, float, float, float, float, float, float, str]:
    return (
        0 if entry.eligible else 1,
        -entry.normalized_score,
        -entry.valuation_score,
        -entry.evidence_score,
        -entry.agreement_score,
        -entry.recommendation_score,
        -entry.momentum_score,
        entry.symbol,
    )


def _symbol(result: Any) -> str:
    return getattr(getattr(result, "valuation", None), "symbol", getattr(getattr(result, "company", None), "symbol", ""))


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


_VALUATION_SCORES = {
    ValuationCondition.DEEPLY_UNDERVALUED: 100,
    ValuationCondition.UNDERVALUED: 75,
    ValuationCondition.SLIGHTLY_UNDERVALUED: 50,
    ValuationCondition.NEAR_FAIR_VALUE: 20,
    ValuationCondition.MODERATELY_OVERVALUED: -20,
    ValuationCondition.SIGNIFICANTLY_OVERVALUED: -60,
    ValuationCondition.EXTREMELY_OVERVALUED: -100,
}

_RECOMMENDATION_SCORES = {
    RecommendationV2Decision.STRONG_BUY: 100,
    RecommendationV2Decision.BUY: 80,
    RecommendationV2Decision.ACCUMULATE: 55,
    RecommendationV2Decision.HOLD: 10,
    RecommendationV2Decision.REDUCE: -35,
    RecommendationV2Decision.SELL: -75,
    RecommendationV2Decision.AVOID: -100,
}

_EVIDENCE_SCORES = {
    EvidenceQuality.HIGH: 100,
    EvidenceQuality.MEDIUM: 55,
    EvidenceQuality.LOW: 10,
    EvidenceQuality.INSUFFICIENT: -100,
}

_AGREEMENT_SCORES = {
    AgreementLevel.STRONG: 100,
    AgreementLevel.MODERATE: 50,
    AgreementLevel.WEAK: 0,
    AgreementLevel.CONFLICTED: -75,
}

_MOMENTUM_SCORES = {
    MomentumCondition.STRONG_POSITIVE: 100,
    MomentumCondition.POSITIVE: 60,
    MomentumCondition.NEUTRAL: 10,
    MomentumCondition.WEAK: -30,
    MomentumCondition.STRONG_NEGATIVE: -70,
}

_MINIMUM_INTRINSIC_MODELS = 2
_REFERENCE_LIMITATION = (
    "It is not an intrinsic-value estimate or an investor cost-basis measure."
)
