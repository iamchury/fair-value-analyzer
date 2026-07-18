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
)


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
) -> BatchStockAnalysisResult:
    """Analyze stock symbols sequentially and retain per-symbol failures."""
    requested_symbols = _normalize_requested_symbols(symbols)
    successful_results: list[StockAnalysisServiceResult] = []
    failures: list[StockAnalysisFailure] = []

    for symbol in requested_symbols:
        try:
            if eps_selection_config is None and industry_policy_config is None and analyst_consensus_config is None:
                successful_results.append(analyze_stock(symbol, configuration))
            else:
                successful_results.append(
                    analyze_stock(
                        symbol,
                        configuration,
                        eps_selection_config,
                        industry_policy_config,
                        analyst_consensus_config,
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

    return BatchStockAnalysisResult(
        requested_symbols=requested_symbols,
        successful_results=tuple(successful_results),
        failures=tuple(failures),
    )


def analyze_stocks_with_profiles(
    symbols: Sequence[str],
    configuration: ValuationConfiguration,
    profiles: Mapping[str, ValuationProfile],
    eps_selection_config: EPSSelectionConfiguration | None = None,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
    analyst_consensus_config: AnalystConsensusConfiguration | None = None,
) -> BatchStockAnalysisResult:
    """Analyze stock symbols sequentially using preloaded valuation profiles."""
    requested_symbols = _normalize_requested_symbols(symbols)
    successful_results = []
    failures: list[StockAnalysisFailure] = []

    for symbol in requested_symbols:
        try:
            if eps_selection_config is None and industry_policy_config is None and analyst_consensus_config is None:
                successful_results.append(
                    analyze_stock_with_profile(symbol, configuration, profiles)
                )
            else:
                successful_results.append(
                    analyze_stock_with_profile(
                        symbol,
                        configuration,
                        profiles,
                        eps_selection_config,
                        industry_policy_config,
                        analyst_consensus_config,
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

    return BatchStockAnalysisResult(
        requested_symbols=requested_symbols,
        successful_results=tuple(successful_results),
        failures=tuple(failures),
    )


def analyze_stocks_from_config_files(
    stocks_path: str | Path = "config/stocks.yaml",
    valuation_config_path: str | Path = "config/valuation.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
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
    if eps_selection_config is None and industry_policy_config is None and analyst_consensus_config is None:
        return analyze_stocks(stocks_configuration.symbols, valuation_configuration)
    if industry_policy_config is None and analyst_consensus_config is None:
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
        )
    if analyst_consensus_config is None:
        return analyze_stocks(
            stocks_configuration.symbols,
            valuation_configuration,
            eps_selection_config,
            industry_policy_config,
        )
    return analyze_stocks(
        stocks_configuration.symbols,
        valuation_configuration,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
    )


def analyze_stocks_with_profiles_from_config_files(
    stocks_path: str | Path = "config/stocks.yaml",
    valuation_config_path: str | Path = "config/valuation.yaml",
    profiles_path: str | Path = "config/valuation_profiles.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
    analyst_consensus_path: str | Path | None = None,
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
    if eps_selection_config is None and industry_policy_config is None and analyst_consensus_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
        )
    if industry_policy_config is None and analyst_consensus_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
        )
    if analyst_consensus_config is None:
        return analyze_stocks_with_profiles(
            stocks_configuration.symbols,
            valuation_configuration,
            profiles,
            eps_selection_config,
            industry_policy_config,
        )
    return analyze_stocks_with_profiles(
        stocks_configuration.symbols,
        valuation_configuration,
        profiles,
        eps_selection_config,
        industry_policy_config,
        analyst_consensus_config,
    )


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
