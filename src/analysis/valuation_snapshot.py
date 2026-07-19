from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any

from src.analysis.research_valuation import ResearchValuationStatus
from src.analysis.stock_valuation import StockValuationStatus


class ValuationModelType(str, Enum):
    AUTOMATIC_PER = "AUTOMATIC_PER"
    RESEARCH_PER = "RESEARCH_PER"
    DCF_REFERENCE = "DCF_REFERENCE"
    ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
    RELATIVE_VALUATION = "RELATIVE_VALUATION"
    UNKNOWN = "UNKNOWN"


class ValuationSnapshotStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class ValuationConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ValuationValueType(str, Enum):
    INTRINSIC_VALUE = "INTRINSIC_VALUE"
    MARKET_EXPECTATION = "MARKET_EXPECTATION"
    REFERENCE_VALUE = "REFERENCE_VALUE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ValuationSnapshotStep:
    name: str
    input_values: Mapping[str, object]
    formula: str | None
    result: float | None
    explanation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_values", _freeze_metadata(self.input_values))
        if self.result is not None:
            _require_number("calculation step result", self.result)


@dataclass(frozen=True)
class ValuationSnapshot:
    symbol: str
    model_type: ValuationModelType
    model_name: str
    value_type: ValuationValueType
    status: ValuationSnapshotStatus
    confidence: ValuationConfidenceLevel
    raw_fair_value: float | None
    adjusted_fair_value: float | None
    selected_fair_value: float | None
    currency: str | None
    valuation_date: date | None
    source_as_of: date | datetime | None
    generated_at: datetime
    methodology: str | None
    rationale: str | None
    assumptions: Mapping[str, object]
    metrics: Mapping[str, object]
    warnings: tuple[str, ...]
    calculation_steps: tuple[ValuationSnapshotStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        _require_enum("model_type", self.model_type, ValuationModelType)
        _require_enum("value_type", self.value_type, ValuationValueType)
        _require_enum("status", self.status, ValuationSnapshotStatus)
        _require_enum("confidence", self.confidence, ValuationConfidenceLevel)
        _require_aware_datetime("generated_at", self.generated_at)
        for field_name in (
            "raw_fair_value",
            "adjusted_fair_value",
            "selected_fair_value",
        ):
            _require_optional_positive_number(field_name, getattr(self, field_name))
        object.__setattr__(self, "assumptions", _freeze_metadata(self.assumptions))
        object.__setattr__(self, "metrics", _freeze_metadata(self.metrics))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "calculation_steps", tuple(self.calculation_steps))


@dataclass(frozen=True)
class ValuationSnapshotCollection:
    symbol: str
    snapshots: tuple[ValuationSnapshot, ...]
    generated_at: datetime

    def __post_init__(self) -> None:
        symbol = _normalize_symbol(self.symbol)
        _require_aware_datetime("generated_at", self.generated_at)
        ordered = tuple(
            sorted(
                self.snapshots,
                key=lambda item: _MODEL_ORDER.index(item.model_type),
            )
        )
        seen: set[ValuationModelType] = set()
        for snapshot in ordered:
            if snapshot.symbol != symbol:
                raise ValueError("all snapshots must use the collection symbol.")
            if snapshot.model_type in seen:
                raise ValueError(f"duplicate snapshot model_type: {snapshot.model_type.value}.")
            seen.add(snapshot.model_type)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "snapshots", ordered)

    def get(self, model_type: ValuationModelType) -> ValuationSnapshot | None:
        for snapshot in self.snapshots:
            if snapshot.model_type == model_type:
                return snapshot
        return None


_MODEL_ORDER = (
    ValuationModelType.AUTOMATIC_PER,
    ValuationModelType.RESEARCH_PER,
    ValuationModelType.DCF_REFERENCE,
    ValuationModelType.ANALYST_CONSENSUS,
    ValuationModelType.RELATIVE_VALUATION,
    ValuationModelType.UNKNOWN,
)

_DCF_REFERENCE_WARNING = (
    "This value is a supplied DCF reference, not a DCF calculation performed "
    "by this application."
)


def create_automatic_per_snapshot(
    result: Any,
    generated_at: datetime | None = None,
) -> ValuationSnapshot:
    valuation = getattr(result, "valuation", None)
    fair_value = getattr(valuation, "fair_value", None)
    decision = getattr(valuation, "valuation_decision", None)
    target_pe = getattr(valuation, "target_pe", None)
    macro = getattr(valuation, "macro_adjustment", None)
    eps_selection = getattr(result, "eps_selection", None)
    industry_policy = getattr(result, "industry_policy", None)
    company = getattr(result, "company", None)
    warnings = _combined_warnings(eps_selection, industry_policy)

    adjusted = _positive_or_none(_getattr(fair_value, "adjusted_fair_value"))
    raw = _positive_or_none(_getattr(fair_value, "base_fair_value"))
    valuation_eps = _getattr(valuation, "valuation_eps_used")
    if valuation_eps is None:
        valuation_eps = _getattr(fair_value, "forward_eps")
    valuation_eps_method = _getattr(valuation, "valuation_eps_method")
    if valuation_eps_method is None and valuation_eps is not None:
        valuation_eps_method = "LEGACY_FORWARD"
    status = _automatic_status(valuation, adjusted)
    if status == ValuationSnapshotStatus.PARTIAL:
        warnings += ("Automatic PER snapshot has incomplete supporting metadata.",)
    if status == ValuationSnapshotStatus.UNAVAILABLE:
        warnings += ("Automatic PER fair value is unavailable.",)

    return ValuationSnapshot(
        symbol=_getattr(valuation, "symbol") or _getattr(company, "symbol"),
        model_type=ValuationModelType.AUTOMATIC_PER,
        model_name="Automatic PER Model",
        value_type=ValuationValueType.INTRINSIC_VALUE,
        status=status,
        confidence=_automatic_confidence(status, warnings),
        raw_fair_value=raw,
        adjusted_fair_value=adjusted,
        selected_fair_value=adjusted,
        currency=_getattr(company, "currency"),
        valuation_date=None,
        source_as_of=_date_or_none(_getattr(getattr(result, "treasury", None), "yield_date")),
        generated_at=_generated_at(generated_at),
        methodology="Selected EPS * Applied Target PE * Treasury Multiplier",
        rationale=_getattr(valuation, "explanation"),
        assumptions=_without_none(
            {
                "valuation_eps": valuation_eps,
                "valuation_eps_method": valuation_eps_method,
                "original_target_pe": _getattr(target_pe, "recommended_target_pe"),
                "applied_target_pe": _getattr(valuation, "target_pe_used")
                or _getattr(fair_value, "recommended_target_pe"),
                "industry_policy_name": _getattr(industry_policy, "policy_name"),
                "treasury_multiplier": _getattr(macro, "total_adjustment_multiplier"),
                "buy_discount_percent": _getattr(decision, "buy_discount_percent"),
                "sell_premium_percent": _getattr(decision, "sell_premium_percent"),
            }
        ),
        metrics=_without_none(
            {
                "current_price": _getattr(company, "current_price"),
                "discount_to_fair_value_percent": _getattr(
                    decision, "discount_to_fair_value_percent"
                ),
                "upside_to_fair_value_percent": _getattr(
                    decision, "upside_to_fair_value_percent"
                ),
                "eps_growth_percent": _getattr(
                    _getattr(valuation, "eps_growth"), "growth_percent"
                ),
                "effective_eps_growth_percent": _getattr(
                    target_pe, "effective_eps_growth_percent"
                ),
                "current_forward_pe": _getattr(company, "forward_pe"),
            }
        ),
        warnings=warnings,
        calculation_steps=(),
    )


def create_research_per_snapshot(
    result: Any,
    generated_at: datetime | None = None,
) -> ValuationSnapshot:
    profile = getattr(result, "profile", None)
    research = getattr(result, "research_valuation", None)
    comparison = getattr(result, "valuation_comparison", None)
    company = getattr(result, "company", None)
    adjusted = _positive_or_none(_getattr(research, "research_adjusted_fair_value"))
    raw = _positive_or_none(_getattr(research, "research_base_fair_value"))
    status = _research_status(profile, research, adjusted)
    warnings = ()
    if status == ValuationSnapshotStatus.PARTIAL:
        warnings = ("Research PER snapshot has incomplete supporting metadata.",)

    return ValuationSnapshot(
        symbol=_getattr(profile, "symbol") or _getattr(company, "symbol"),
        model_type=ValuationModelType.RESEARCH_PER,
        model_name="Research PER Model",
        value_type=ValuationValueType.INTRINSIC_VALUE,
        status=status,
        confidence=_research_confidence(status, profile),
        raw_fair_value=raw,
        adjusted_fair_value=adjusted,
        selected_fair_value=adjusted,
        currency=_getattr(company, "currency"),
        valuation_date=None,
        source_as_of=None,
        generated_at=_generated_at(generated_at),
        methodology="Research EPS * Research Target PE * Treasury Multiplier",
        rationale=_getattr(profile, "source_note"),
        assumptions=_without_none(
            {
                "valuation_style": _enum_or_value(_getattr(profile, "valuation_style")),
                "research_eps": _getattr(profile, "valuation_eps"),
                "eps_fiscal_year": _getattr(profile, "eps_fiscal_year"),
                "research_target_pe": _getattr(profile, "target_pe"),
                "peg_adjustment_enabled": _getattr(profile, "use_peg_adjustment"),
                "treasury_multiplier": _getattr(
                    research, "macro_adjustment_multiplier"
                ),
                "source_note": _getattr(profile, "source_note"),
            }
        ),
        metrics=_without_none(
            {
                "difference_vs_automatic_percent": _getattr(
                    comparison, "automatic_vs_research_difference_percent"
                ),
                "difference_vs_dcf_percent": _getattr(
                    comparison, "research_vs_dcf_difference_percent"
                ),
            }
        ),
        warnings=warnings,
        calculation_steps=(),
    )


def create_dcf_reference_snapshot(
    result: Any,
    generated_at: datetime | None = None,
) -> ValuationSnapshot:
    profile = getattr(result, "profile", None)
    research = getattr(result, "research_valuation", None)
    company = getattr(result, "company", None)
    dcf_value = _getattr(profile, "dcf_fair_value")
    if dcf_value is None:
        dcf_value = _getattr(research, "dcf_fair_value")
    dcf_value = _positive_or_none(dcf_value)
    source_note = _getattr(profile, "source_note")
    status = (
        ValuationSnapshotStatus.UNAVAILABLE
        if dcf_value is None
        else ValuationSnapshotStatus.COMPLETE
        if source_note
        else ValuationSnapshotStatus.PARTIAL
    )

    return ValuationSnapshot(
        symbol=_getattr(profile, "symbol") or _getattr(company, "symbol"),
        model_type=ValuationModelType.DCF_REFERENCE,
        model_name="DCF Reference",
        value_type=ValuationValueType.REFERENCE_VALUE,
        status=status,
        confidence=_dcf_confidence(status, source_note),
        raw_fair_value=dcf_value,
        adjusted_fair_value=dcf_value,
        selected_fair_value=dcf_value,
        currency=_getattr(company, "currency"),
        valuation_date=None,
        source_as_of=None,
        generated_at=_generated_at(generated_at),
        methodology="Externally supplied DCF reference value",
        rationale=source_note,
        assumptions=_without_none(
            {
                "source_note": source_note,
                "valuation_style": _enum_or_value(_getattr(profile, "valuation_style")),
                "related_eps_fiscal_year": _getattr(profile, "eps_fiscal_year"),
            }
        ),
        metrics={},
        warnings=(_DCF_REFERENCE_WARNING,),
        calculation_steps=(),
    )


def build_valuation_snapshot_collection(
    stock_analysis_result: Any,
    generated_at: datetime | None = None,
) -> ValuationSnapshotCollection:
    generated = _generated_at(generated_at)
    candidates = (
        create_automatic_per_snapshot(stock_analysis_result, generated),
        create_research_per_snapshot(stock_analysis_result, generated),
        create_dcf_reference_snapshot(stock_analysis_result, generated),
        _getattr(stock_analysis_result, "analyst_consensus"),
    )
    snapshots = tuple(
        snapshot
        for snapshot in candidates
        if isinstance(snapshot, ValuationSnapshot)
        and snapshot.status != ValuationSnapshotStatus.UNAVAILABLE
    )
    symbol = (
        _getattr(_getattr(stock_analysis_result, "valuation"), "symbol")
        or _getattr(_getattr(stock_analysis_result, "company"), "symbol")
    )
    return ValuationSnapshotCollection(
        symbol=symbol,
        snapshots=snapshots,
        generated_at=generated,
    )


def valuation_snapshot_to_dict(snapshot: ValuationSnapshot) -> dict[str, object]:
    return {
        "symbol": snapshot.symbol,
        "model_type": snapshot.model_type.value,
        "model_name": snapshot.model_name,
        "value_type": snapshot.value_type.value,
        "status": snapshot.status.value,
        "confidence": snapshot.confidence.value,
        "raw_fair_value": snapshot.raw_fair_value,
        "adjusted_fair_value": snapshot.adjusted_fair_value,
        "selected_fair_value": snapshot.selected_fair_value,
        "currency": snapshot.currency,
        "valuation_date": _serialize(snapshot.valuation_date),
        "source_as_of": _serialize(snapshot.source_as_of),
        "generated_at": snapshot.generated_at.isoformat(),
        "methodology": snapshot.methodology,
        "rationale": snapshot.rationale,
        "assumptions": _serialize(snapshot.assumptions),
        "metrics": _serialize(snapshot.metrics),
        "warnings": list(snapshot.warnings),
        "calculation_steps": [_serialize_step(step) for step in snapshot.calculation_steps],
    }


def valuation_snapshot_collection_to_dict(
    collection: ValuationSnapshotCollection,
) -> dict[str, object]:
    return {
        "symbol": collection.symbol,
        "generated_at": collection.generated_at.isoformat(),
        "snapshots": [
            valuation_snapshot_to_dict(snapshot)
            for snapshot in collection.snapshots
        ],
    }


def _automatic_status(valuation: Any, selected: float | None) -> ValuationSnapshotStatus:
    source_status = _getattr(valuation, "status")
    if source_status in (
        StockValuationStatus.TARGET_PE_UNAVAILABLE,
        StockValuationStatus.FAIR_VALUE_UNAVAILABLE,
    ):
        return ValuationSnapshotStatus.UNAVAILABLE
    if source_status == StockValuationStatus.COMPLETE and selected is not None:
        return ValuationSnapshotStatus.COMPLETE
    if selected is not None:
        return ValuationSnapshotStatus.PARTIAL
    return ValuationSnapshotStatus.UNAVAILABLE


def _automatic_confidence(
    status: ValuationSnapshotStatus,
    warnings: tuple[str, ...],
) -> ValuationConfidenceLevel:
    if status == ValuationSnapshotStatus.COMPLETE:
        return ValuationConfidenceLevel.LOW if warnings else ValuationConfidenceLevel.MEDIUM
    if status == ValuationSnapshotStatus.PARTIAL:
        return ValuationConfidenceLevel.LOW
    return ValuationConfidenceLevel.UNKNOWN


def _research_status(
    profile: Any,
    research: Any,
    selected: float | None,
) -> ValuationSnapshotStatus:
    if profile is None or selected is None:
        return ValuationSnapshotStatus.UNAVAILABLE
    if _getattr(research, "status") != ResearchValuationStatus.COMPLETE:
        return ValuationSnapshotStatus.PARTIAL
    required = (
        _getattr(profile, "valuation_eps"),
        _getattr(profile, "target_pe"),
        _getattr(profile, "eps_fiscal_year"),
        _getattr(profile, "source_note"),
    )
    return (
        ValuationSnapshotStatus.COMPLETE
        if all(value is not None and value != "" for value in required)
        else ValuationSnapshotStatus.PARTIAL
    )


def _research_confidence(
    status: ValuationSnapshotStatus,
    profile: Any,
) -> ValuationConfidenceLevel:
    if status == ValuationSnapshotStatus.COMPLETE:
        required = (
            _getattr(profile, "valuation_eps"),
            _getattr(profile, "target_pe"),
            _getattr(profile, "eps_fiscal_year"),
            _getattr(profile, "source_note"),
        )
        return (
            ValuationConfidenceLevel.HIGH
            if all(value is not None and value != "" for value in required)
            else ValuationConfidenceLevel.MEDIUM
        )
    if status == ValuationSnapshotStatus.PARTIAL:
        return ValuationConfidenceLevel.LOW
    return ValuationConfidenceLevel.UNKNOWN


def _dcf_confidence(
    status: ValuationSnapshotStatus,
    source_note: str | None,
) -> ValuationConfidenceLevel:
    if status == ValuationSnapshotStatus.COMPLETE and source_note:
        return ValuationConfidenceLevel.MEDIUM
    if status == ValuationSnapshotStatus.PARTIAL:
        return ValuationConfidenceLevel.LOW
    return ValuationConfidenceLevel.UNKNOWN


def _generated_at(value: datetime | None) -> datetime:
    generated = datetime.now(timezone.utc) if value is None else value
    _require_aware_datetime("generated_at", generated)
    return generated


def _date_or_none(value: Any) -> date | datetime | None:
    if value is None or isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _freeze_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_metadata(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(child) for child in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_metadata(child) for child in value))
    if isinstance(value, Enum):
        return value.value
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _serialize(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_serialize(child) for child in value]
    return value


def _serialize_step(step: ValuationSnapshotStep) -> dict[str, object]:
    return {
        "name": step.name,
        "input_values": _serialize(step.input_values),
        "formula": step.formula,
        "result": step.result,
        "explanation": step.explanation,
    }


def _without_none(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _getattr(value: Any, attribute_name: str) -> Any:
    if value is None:
        return None
    return getattr(value, attribute_name, None)


def _enum_or_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _combined_warnings(*sources: Any) -> tuple[str, ...]:
    warnings: list[str] = []
    for source in sources:
        warnings.extend(str(warning) for warning in _getattr(source, "warnings") or ())
    return tuple(warnings)


def _positive_or_none(value: Any) -> float | None:
    if value is None:
        return None
    _require_number("fair value", value)
    if value <= 0:
        return None
    return float(value)


def _require_optional_positive_number(field_name: str, value: Any) -> None:
    if value is None:
        return
    _require_number(field_name, value)
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


def _require_number(field_name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite.")


def _require_aware_datetime(field_name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _require_enum(field_name: str, value: Any, enum_type: type[Enum]) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field_name} must be a {enum_type.__name__}.")


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    if any(character.isspace() for character in normalized):
        raise ValueError("symbol must not contain whitespace.")
    return normalized
