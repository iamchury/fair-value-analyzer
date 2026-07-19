from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.config.stocks import load_stocks_configuration
from src.config.eps_selection import (
    EPSSelectionConfiguration,
    load_eps_selection_configuration,
)
from src.config.analyst_consensus import (
    AnalystConsensusConfiguration,
    load_analyst_consensus_configuration,
)
from src.config.agreement_engine import (
    AgreementEngineConfiguration,
    load_agreement_engine_configuration,
)
from src.config.fair_value_range import (
    FairValueRangeConfiguration,
    load_fair_value_range_configuration,
)
from src.config.recommendation_v2 import (
    RecommendationV2Configuration,
    load_recommendation_v2_configuration,
)
from src.analysis.ranking_engine import StockRankingResult, rank_stocks
from src.config.ranking_engine import (
    RankingEngineConfiguration,
    load_ranking_engine_configuration,
)
from src.config.momentum_reference import (
    MomentumReferenceConfiguration,
    load_momentum_reference_configuration,
)
from src.config.industry_policies import (
    IndustryPolicyConfiguration,
    load_industry_policy_configuration,
)
from src.config.valuation import (
    ValuationConfiguration,
    load_valuation_configuration,
)
from src.config.valuation_profiles import ValuationProfile, load_valuation_profiles
from src.services.stock_analysis import (
    StockAnalysisServiceError,
    StockAnalysisServiceResult,
    analyze_stock,
    analyze_stock_with_profile,
    build_resilient_treasury_snapshot,
)
from src.yahoo.treasury import TreasuryDataStatus, TreasuryYieldSnapshot


@dataclass(frozen=True)
class StockAnalysisFailure:
    symbol: str
    error_type: str
    message: str


@dataclass(frozen=True)
class BatchStockAnalysisResult:
    requested_symbols: tuple[str, ...]
    successful_results: tuple[StockAnalysisServiceResult, ...]
    failures: tuple[StockAnalysisFailure, ...]
    ranking_result: StockRankingResult | None = None
    treasury_status: TreasuryDataStatus | None = None
    treasury_yield_percent: float | None = None
    treasury_source_date: str | None = None
    treasury_trend: object | None = None
    treasury_warning: str | None = None
    treasury_used_fallback: bool = False

    @property
    def success_count(self) -> int:
        return len(self.successful_results)

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    @property
    def total_count(self) -> int:
        return len(self.requested_symbols)


def analyze_stocks(
    symbols: Sequence[str],
    configuration: ValuationConfiguration,
    eps_selection_config: EPSSelectionConfiguration | None = None,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
    analyst_consensus_config: AnalystConsensusConfiguration | None = None,
    agreement_config: AgreementEngineConfiguration | None = None,
    momentum_config: MomentumReferenceConfiguration | None = None,
    range_config: FairValueRangeConfiguration | None = None,
    recommendation_v2_config: RecommendationV2Configuration | None = None,
    ranking_config: RankingEngineConfiguration | None = None,
) -> BatchStockAnalysisResult:
    """Analyze stock symbols sequentially and retain per-symbol failures."""
    requested_symbols = _normalize_requested_symbols(symbols)
    successful_results: list[StockAnalysisServiceResult] = []
    failures: list[StockAnalysisFailure] = []
    shared_treasury = _shared_treasury_snapshot(configuration)

    for symbol in requested_symbols:
        try:
            if (
                eps_selection_config is None
                and industry_policy_config is None
                and analyst_consensus_config is None
                and agreement_config is None
                and momentum_config is None
                and range_config is None
                and recommendation_v2_config is None
            ):
                successful_results.append(
                    _analyze_stock_with_optional_treasury(
                        symbol,
                        configuration,
                        shared_treasury=shared_treasury,
                    )
                )
            else:
                args = (
                    symbol,
                    configuration,
                    eps_selection_config,
                    industry_policy_config,
                    analyst_consensus_config,
                    agreement_config,
                    momentum_config,
                    range_config,
                )
                if recommendation_v2_config is None:
                    successful_results.append(
                        _analyze_stock_with_optional_treasury(*args, shared_treasury=shared_treasury)
                    )
                else:
                    successful_results.append(
                        _analyze_stock_with_optional_treasury(
                            *args,
                            recommendation_v2_config,
                            shared_treasury=shared_treasury,
                        )
                    )
        except (StockAnalysisServiceError, ValueError, RuntimeError) as exc:
            failures.append(
                StockAnalysisFailure(
                    symbol=symbol,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )

    result = BatchStockAnalysisResult(
        requested_symbols=requested_symbols,
        successful_results=tuple(successful_results),
        failures=tuple(failures),
        **_treasury_batch_fields(shared_treasury, tuple(successful_results)),
    )
    return _attach_ranking(result, ranking_config)


def analyze_stocks_with_profiles(
    symbols: Sequence[str],
    configuration: ValuationConfiguration,
    profiles: Mapping[str, ValuationProfile],
    eps_selection_config: EPSSelectionConfiguration | None = None,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
    analyst_consensus_config: AnalystConsensusConfiguration | None = None,
    agreement_config: AgreementEngineConfiguration | None = None,
    momentum_config: MomentumReferenceConfiguration | None = None,
    range_config: FairValueRangeConfiguration | None = None,
    recommendation_v2_config: RecommendationV2Configuration | None = None,
    ranking_config: RankingEngineConfiguration | None = None,
) -> BatchStockAnalysisResult:
    """Analyze stock symbols sequentially using preloaded valuation profiles."""
    requested_symbols = _normalize_requested_symbols(symbols)
    successful_results = []
    failures: list[StockAnalysisFailure] = []
    shared_treasury = _shared_treasury_snapshot(configuration)

    for symbol in requested_symbols:
        try:
            if (
                eps_selection_config is None
                and industry_policy_config is None
                and analyst_consensus_config is None
                and agreement_config is None
                and momentum_config is None
                and range_config is None
                and recommendation_v2_config is None
            ):
                successful_results.append(
                    _analyze_profile_with_optional_treasury(
                        symbol,
                        configuration,
                        profiles,
                        shared_treasury=shared_treasury,
                    )
                )
            else:
                args = (
                    symbol,
                    configuration,
                    profiles,
                    eps_selection_config,
                    industry_policy_config,
                    analyst_consensus_config,
                    agreement_config,
                    momentum_config,
                    range_config,
                )
                if recommendation_v2_config is None:
                    successful_results.append(
                        _analyze_profile_with_optional_treasury(*args, shared_treasury=shared_treasury)
                    )
                else:
                    successful_results.append(
                        _analyze_profile_with_optional_treasury(
                            *args,
                            recommendation_v2_config,
                            shared_treasury=shared_treasury,
                        )
                    )
        except (StockAnalysisServiceError, ValueError, RuntimeError) as exc:
            failures.append(
                StockAnalysisFailure(
                    symbol=symbol,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )

    result = BatchStockAnalysisResult(
        requested_symbols=requested_symbols,
        successful_results=tuple(successful_results),
        failures=tuple(failures),
        **_treasury_batch_fields(shared_treasury, tuple(successful_results)),
    )
    return _attach_ranking(result, ranking_config)


def analyze_stocks_from_config_files(
    stocks_path: str | Path = "config/stocks.yaml",
    valuation_config_path: str | Path = "config/valuation.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
    agreement_config_path: str | Path | None = None,
    momentum_config_path: str | Path | None = None,
    range_config_path: str | Path | None = None,
    recommendation_v2_config_path: str | Path | None = None,
    ranking_config_path: str | Path | None = None,
) -> BatchStockAnalysisResult:
    """Load configuration files once, then run sequential batch analysis."""
    valuation_configuration = load_valuation_configuration(valuation_config_path)
    stocks_configuration = load_stocks_configuration(stocks_path)
    eps_selection_config = (
        None
        if eps_selection_path is None
        else load_eps_selection_configuration(eps_selection_path)
    )
    industry_policy_config = (
        None
        if industry_policies_path is None
        else load_industry_policy_configuration(industry_policies_path)
    )
    analyst_consensus_config = (
        None
        if analyst_consensus_path is None
        else load_analyst_consensus_configuration(analyst_consensus_path)
    )
    agreement_config = (
        None
        if agreement_config_path is None
        else load_agreement_engine_configuration(agreement_config_path)
    )
    momentum_config = (
        None
        if momentum_config_path is None
        else load_momentum_reference_configuration(momentum_config_path)
    )
    range_config = (
        None
        if range_config_path is None
        else load_fair_value_range_configuration(range_config_path)
    )
    recommendation_v2_config = (
        None
        if recommendation_v2_config_path is None
        else load_recommendation_v2_configuration(recommendation_v2_config_path)
    )
    ranking_config = (
        None
        if ranking_config_path is None
        else load_ranking_engine_configuration(ranking_config_path)
    )
    if (
        eps_selection_config is None
        and industry_policy_config is None
        and analyst_consensus_config is None
        and agreement_config is None
        and momentum_config is None
        and range_config is None
        and recommendation_v2_config is None
        and ranking_config is None
    ):
        return analyze_stocks(stocks_configuration.symbols, valuation_configuration)
    if (
        industry_policy_config is None
        and analyst_consensus_config is None
        and agreement_config is None
        and momentum_config is None
        and range_config is None
        and recommendation_v2_config is None
        and ranking_config is None
    ):
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
        )
    if analyst_consensus_config is None and agreement_config is None and momentum_config is None and range_config is None and recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
            industry_policy_config,
        )
    if momentum_config is None and range_config is None and recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
            industry_policy_config,
            analyst_consensus_config,
            agreement_config,
        )
    if recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
            industry_policy_config,
            analyst_consensus_config,
            agreement_config,
            momentum_config,
            range_config,
        )
    return analyze_stocks(
        stocks_configuration.symbols,
        valuation_configuration,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
        agreement_config,
        momentum_config,
        range_config,
        recommendation_v2_config,
        ranking_config,
    )


def analyze_stocks_with_profiles_from_config_files(
    stocks_path: str | Path = "config/stocks.yaml",
    valuation_config_path: str | Path = "config/valuation.yaml",
    profiles_path: str | Path = "config/valuation_profiles.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
    agreement_config_path: str | Path | None = None,
    momentum_config_path: str | Path | None = None,
    range_config_path: str | Path | None = None,
    recommendation_v2_config_path: str | Path | None = None,
    ranking_config_path: str | Path | None = None,
) -> BatchStockAnalysisResult:
    """Load valuation, stock, and profile files once, then run batch analysis."""
    valuation_configuration = load_valuation_configuration(valuation_config_path)
    stocks_configuration = load_stocks_configuration(stocks_path)
    profiles = load_valuation_profiles(profiles_path)
    eps_selection_config = (
        None
        if eps_selection_path is None
        else load_eps_selection_configuration(eps_selection_path)
    )
    industry_policy_config = (
        None
        if industry_policies_path is None
        else load_industry_policy_configuration(industry_policies_path)
    )
    analyst_consensus_config = (
        None
        if analyst_consensus_path is None
        else load_analyst_consensus_configuration(analyst_consensus_path)
    )
    agreement_config = (
        None
        if agreement_config_path is None
        else load_agreement_engine_configuration(agreement_config_path)
    )
    momentum_config = (
        None
        if momentum_config_path is None
        else load_momentum_reference_configuration(momentum_config_path)
    )
    range_config = (
        None
        if range_config_path is None
        else load_fair_value_range_configuration(range_config_path)
    )
    recommendation_v2_config = (
        None
        if recommendation_v2_config_path is None
        else load_recommendation_v2_configuration(recommendation_v2_config_path)
    )
    ranking_config = (
        None
        if ranking_config_path is None
        else load_ranking_engine_configuration(ranking_config_path)
    )
    if (
        eps_selection_config is None
        and industry_policy_config is None
        and analyst_consensus_config is None
        and agreement_config is None
        and momentum_config is None
        and range_config is None
        and recommendation_v2_config is None
        and ranking_config is None
    ):
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
        )
    if (
        industry_policy_config is None
        and analyst_consensus_config is None
        and agreement_config is None
        and momentum_config is None
        and range_config is None
        and recommendation_v2_config is None
        and ranking_config is None
    ):
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
        )
    if analyst_consensus_config is None and agreement_config is None and momentum_config is None and range_config is None and recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
            industry_policy_config,
        )
    if momentum_config is None and range_config is None and recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
            industry_policy_config,
            analyst_consensus_config,
            agreement_config,
        )
    if recommendation_v2_config is None and ranking_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
            industry_policy_config,
            analyst_consensus_config,
            agreement_config,
            momentum_config,
            range_config,
        )
    return analyze_stocks_with_profiles(
        stocks_configuration.symbols,
        valuation_configuration,
        profiles,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
        agreement_config,
        momentum_config,
        range_config,
        recommendation_v2_config,
        ranking_config,
    )


def analyze_symbol_list_from_config_files(
    symbols: Sequence[str],
    valuation_config_path: str | Path = "config/valuation.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
    agreement_config_path: str | Path | None = None,
    momentum_config_path: str | Path | None = None,
    range_config_path: str | Path | None = None,
    recommendation_v2_config_path: str | Path | None = None,
    ranking_config_path: str | Path | None = None,
) -> BatchStockAnalysisResult:
    configuration = load_valuation_configuration(valuation_config_path)
    eps_selection_config = None if eps_selection_path is None else load_eps_selection_configuration(eps_selection_path)
    industry_policy_config = None if industry_policies_path is None else load_industry_policy_configuration(industry_policies_path)
    analyst_consensus_config = None if analyst_consensus_path is None else load_analyst_consensus_configuration(analyst_consensus_path)
    agreement_config = None if agreement_config_path is None else load_agreement_engine_configuration(agreement_config_path)
    momentum_config = None if momentum_config_path is None else load_momentum_reference_configuration(momentum_config_path)
    range_config = None if range_config_path is None else load_fair_value_range_configuration(range_config_path)
    recommendation_v2_config = None if recommendation_v2_config_path is None else load_recommendation_v2_configuration(recommendation_v2_config_path)
    ranking_config = None if ranking_config_path is None else load_ranking_engine_configuration(ranking_config_path)
    return analyze_stocks(
        symbols,
        configuration,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
        agreement_config,
        momentum_config,
        range_config,
        recommendation_v2_config,
        ranking_config,
    )


def analyze_symbol_list_with_profiles_from_config_files(
    symbols: Sequence[str],
    valuation_config_path: str | Path = "config/valuation.yaml",
    profiles_path: str | Path = "config/valuation_profiles.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
    agreement_config_path: str | Path | None = None,
    momentum_config_path: str | Path | None = None,
    range_config_path: str | Path | None = None,
    recommendation_v2_config_path: str | Path | None = None,
    ranking_config_path: str | Path | None = None,
) -> BatchStockAnalysisResult:
    configuration = load_valuation_configuration(valuation_config_path)
    profiles = load_valuation_profiles(profiles_path)
    eps_selection_config = None if eps_selection_path is None else load_eps_selection_configuration(eps_selection_path)
    industry_policy_config = None if industry_policies_path is None else load_industry_policy_configuration(industry_policies_path)
    analyst_consensus_config = None if analyst_consensus_path is None else load_analyst_consensus_configuration(analyst_consensus_path)
    agreement_config = None if agreement_config_path is None else load_agreement_engine_configuration(agreement_config_path)
    momentum_config = None if momentum_config_path is None else load_momentum_reference_configuration(momentum_config_path)
    range_config = None if range_config_path is None else load_fair_value_range_configuration(range_config_path)
    recommendation_v2_config = None if recommendation_v2_config_path is None else load_recommendation_v2_configuration(recommendation_v2_config_path)
    ranking_config = None if ranking_config_path is None else load_ranking_engine_configuration(ranking_config_path)
    return analyze_stocks_with_profiles(
        symbols,
        configuration,
        profiles,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
        agreement_config,
        momentum_config,
        range_config,
        recommendation_v2_config,
        ranking_config,
    )


def _attach_ranking(
    result: BatchStockAnalysisResult,
    configuration: RankingEngineConfiguration | None,
) -> BatchStockAnalysisResult:
    if configuration is None:
        return result
    return BatchStockAnalysisResult(
        requested_symbols=result.requested_symbols,
        successful_results=result.successful_results,
        failures=result.failures,
        ranking_result=rank_stocks(result.successful_results, result.failures, configuration),
        treasury_status=result.treasury_status,
        treasury_yield_percent=result.treasury_yield_percent,
        treasury_source_date=result.treasury_source_date,
        treasury_trend=result.treasury_trend,
        treasury_warning=result.treasury_warning,
        treasury_used_fallback=result.treasury_used_fallback,
    )


def _shared_treasury_snapshot(configuration: object) -> TreasuryYieldSnapshot | None:
    if not isinstance(configuration, ValuationConfiguration):
        return None
    return build_resilient_treasury_snapshot(configuration)


def _analyze_stock_with_optional_treasury(*args: object, shared_treasury: TreasuryYieldSnapshot | None):
    if shared_treasury is None:
        return analyze_stock(*args)
    return analyze_stock(*args, treasury_snapshot=shared_treasury)


def _analyze_profile_with_optional_treasury(*args: object, shared_treasury: TreasuryYieldSnapshot | None):
    if shared_treasury is None:
        return analyze_stock_with_profile(*args)
    return analyze_stock_with_profile(*args, treasury_snapshot=shared_treasury)


def _treasury_batch_fields(
    treasury: TreasuryYieldSnapshot | None,
    successful_results: tuple[object, ...] = (),
) -> dict[str, object]:
    if treasury is None:
        return {}
    trend = None
    for result in successful_results:
        trend = getattr(getattr(getattr(result, "valuation", None), "macro_adjustment", None), "trend", None)
        if trend is not None:
            break
    return {
        "treasury_status": treasury.data_status,
        "treasury_yield_percent": treasury.current_yield_percent,
        "treasury_source_date": treasury.yield_date,
        "treasury_trend": trend,
        "treasury_warning": None if not treasury.warnings else treasury.warnings[0],
        "treasury_used_fallback": treasury.used_fallback,
    }


def _normalize_requested_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    if isinstance(symbols, (str, bytes)):
        raise ValueError("symbols must be a sequence of strings.")
    if not symbols:
        raise ValueError("symbols must not be empty.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, symbol in enumerate(symbols):
        if isinstance(symbol, bool) or not isinstance(symbol, str):
            raise ValueError(f"symbols[{index}] must be a string.")
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError(f"symbols[{index}] must not be empty.")
        if any(character.isspace() for character in normalized_symbol):
            raise ValueError(f"symbols[{index}] must not contain whitespace.")
        if normalized_symbol in seen:
            raise ValueError(f"{normalized_symbol} is duplicated.")
        seen.add(normalized_symbol)
        normalized.append(normalized_symbol)
    return tuple(normalized)
