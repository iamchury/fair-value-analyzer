from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path

from src.analysis.eps_selection import (
    EPSSelectionInputs,
    EPSSelectionResult,
    select_eps,
)
from src.analysis.eps_source_inspector import inspect_eps_source
from src.analysis.research_valuation import (
    ResearchValuationInputs,
    ResearchValuationResult,
    ValuationComparisonResult,
    calculate_research_valuation,
    compare_valuations,
)
from src.analysis.stock_valuation import (
    StockValuationConfig,
    StockValuationInputs,
    StockValuationResult,
    calculate_stock_valuation,
)
from src.config.valuation import (
    ValuationConfiguration,
    load_valuation_configuration,
)
from src.config.industry_policies import (
    IndustryPolicyConfiguration,
    load_industry_policy_configuration,
)
from src.config.eps_selection import (
    EPSSelectionConfiguration,
    get_eps_selection_rule,
    load_eps_selection_configuration,
)
from src.config.valuation_profiles import (
    ValuationProfile,
    load_valuation_profiles,
)
from src.yahoo.company import (
    CompanyFundamentals,
    YahooEPSRawSnapshot,
    download_company_fundamentals,
    download_company_fundamentals_with_eps_snapshot,
    normalize_symbol,
)
from src.yahoo.treasury import TreasuryYieldSnapshot, download_treasury_yield_snapshot


class StockAnalysisServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class StockAnalysisServiceResult:
    company: CompanyFundamentals
    treasury: TreasuryYieldSnapshot
    valuation: StockValuationResult
    eps_selection: EPSSelectionResult | None = None
    industry_policy: object | None = None


@dataclass(frozen=True)
class StockAnalysisWithProfileResult:
    company: CompanyFundamentals
    treasury: TreasuryYieldSnapshot
    valuation: StockValuationResult
    profile: ValuationProfile | None
    research_valuation: ResearchValuationResult | None
    valuation_comparison: ValuationComparisonResult | None
    eps_selection: EPSSelectionResult | None = None
    industry_policy: object | None = None


def normalize_service_symbol(symbol: str) -> str:
    return normalize_symbol(symbol)


def build_stock_valuation_inputs(
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
    eps_selection: EPSSelectionResult | None = None,
) -> StockValuationInputs:
    if company.current_price is None:
        _raise_missing_current_price(company.symbol)

    return StockValuationInputs(
        symbol=company.symbol,
        current_price=company.current_price,
        trailing_eps=company.trailing_eps,
        forward_eps=company.forward_eps,
        peg_ratio=company.peg_ratio,
        sector=company.sector,
        industry=company.industry,
        current_forward_pe=company.forward_pe,
        treasury_current_yield_percent=treasury.current_yield_percent,
        treasury_short_sma_percent=treasury.sma_short_percent,
        treasury_long_sma_percent=treasury.sma_long_percent,
        valuation_eps=(
            None if eps_selection is None else eps_selection.selected_eps
        ),
        valuation_eps_period=(
            None if eps_selection is None else eps_selection.selected_period_label
        ),
        valuation_eps_method=(
            None
            if eps_selection is None or eps_selection.applied_method is None
            else eps_selection.applied_method.value
        ),
    )


def build_stock_valuation_config(
    configuration: ValuationConfiguration,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
) -> StockValuationConfig:
    return StockValuationConfig(
        target_pe=configuration.target_pe,
        treasury_yield=configuration.treasury_yield,
        decision=configuration.decision,
        industry_policy=industry_policy_config,
    )


def analyze_stock(
    symbol: str,
    configuration: ValuationConfiguration,
    eps_selection_config: EPSSelectionConfiguration | None = None,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
) -> StockAnalysisServiceResult:
    normalized_symbol = normalize_service_symbol(symbol)
    eps_selection = None
    if eps_selection_config is None:
        company = download_company_fundamentals(normalized_symbol)
    else:
        downloaded = download_company_fundamentals_with_eps_snapshot(normalized_symbol)
        company = downloaded.fundamentals
        eps_selection = build_eps_selection_result(
            downloaded.eps_snapshot,
            eps_selection_config,
        )
    if company.current_price is None:
        _raise_missing_current_price(normalized_symbol)

    treasury = download_treasury_yield_snapshot(configuration.treasury_history)
    valuation = calculate_stock_valuation(
        build_stock_valuation_inputs(company, treasury, eps_selection),
        build_stock_valuation_config(configuration, industry_policy_config),
    )

    return StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=valuation,
        eps_selection=eps_selection,
        industry_policy=getattr(valuation, "industry_policy", None),
    )


def analyze_stock_from_config_file(
    symbol: str,
    config_path: str | Path = "config/valuation.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
) -> StockAnalysisServiceResult:
    configuration = load_valuation_configuration(config_path)
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
    if eps_selection_config is None and industry_policy_config is None:
        return analyze_stock(symbol, configuration)
    if industry_policy_config is None:
        return analyze_stock(symbol, configuration, eps_selection_config)
    return analyze_stock(
        symbol,
        configuration,
        eps_selection_config,
        industry_policy_config,
    )


def analyze_stock_with_profile(
    symbol: str,
    configuration: ValuationConfiguration,
    profiles: Mapping[str, ValuationProfile] | None = None,
    eps_selection_config: EPSSelectionConfiguration | None = None,
    industry_policy_config: IndustryPolicyConfiguration | None = None,
) -> StockAnalysisWithProfileResult:
    """Analyze one stock and attach optional configured research valuation."""
    result = analyze_stock(
        symbol,
        configuration,
        eps_selection_config,
        industry_policy_config,
    )
    profile = None
    research = None
    comparison = None
    if profiles is not None:
        profile = profiles.get(result.valuation.symbol)
    if profile is not None:
        multiplier = (
            result.valuation.macro_adjustment.total_adjustment_multiplier
            if result.valuation.macro_adjustment is not None
            else 1.0
        )
        research = calculate_research_valuation(
            ResearchValuationInputs(
                profile=profile,
                macro_adjustment_multiplier=multiplier,
            )
        )
        automatic_fair_value = (
            result.valuation.fair_value.adjusted_fair_value
            if result.valuation.fair_value is not None
            else None
        )
        comparison = compare_valuations(automatic_fair_value, research)

    return StockAnalysisWithProfileResult(
        company=result.company,
        treasury=result.treasury,
        valuation=result.valuation,
        profile=profile,
        research_valuation=research,
        valuation_comparison=comparison,
        eps_selection=result.eps_selection,
        industry_policy=result.industry_policy,
    )


def analyze_stock_with_profile_from_config_files(
    symbol: str,
    config_path: str | Path = "config/valuation.yaml",
    profiles_path: str | Path = "config/valuation_profiles.yaml",
    eps_selection_path: str | Path | None = None,
    industry_policies_path: str | Path | None = None,
) -> StockAnalysisWithProfileResult:
    configuration = load_valuation_configuration(config_path)
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
    if eps_selection_config is None and industry_policy_config is None:
        return analyze_stock_with_profile(symbol, configuration, profiles)
    if industry_policy_config is None:
        return analyze_stock_with_profile(
            symbol,
            configuration,
            profiles,
            eps_selection_config,
        )
    return analyze_stock_with_profile(
        symbol,
        configuration,
        profiles,
        eps_selection_config,
        industry_policy_config,
    )


def build_eps_selection_result(
    snapshot: YahooEPSRawSnapshot,
    configuration: EPSSelectionConfiguration,
) -> EPSSelectionResult:
    """Build EPS selection inputs from a normalized Yahoo EPS snapshot."""
    inspection = inspect_eps_source(snapshot)
    rule = get_eps_selection_rule(configuration, snapshot.symbol)
    return select_eps(
        EPSSelectionInputs(
            symbol=snapshot.symbol,
            legacy_forward_eps=snapshot.forward_eps,
            legacy_forward_period_label=inspection.inferred_period_label
            or "Yahoo forwardEps",
            current_year_eps=(
                None
                if snapshot.current_year_estimate is None
                else snapshot.current_year_estimate.estimate
            ),
            current_year_period_label=(
                None
                if snapshot.current_year_estimate is None
                else snapshot.current_year_estimate.period_label
            ),
            next_year_eps=(
                None
                if snapshot.next_year_estimate is None
                else snapshot.next_year_estimate.estimate
            ),
            next_year_period_label=(
                None
                if snapshot.next_year_estimate is None
                else snapshot.next_year_estimate.period_label
            ),
            rule=rule,
        )
    )


def _raise_missing_current_price(symbol: str) -> None:
    raise StockAnalysisServiceError(
        f"Cannot analyze {symbol} because Yahoo current price is unavailable."
    )
