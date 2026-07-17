from dataclasses import dataclass
from pathlib import Path

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
from src.yahoo.company import (
    CompanyFundamentals,
    download_company_fundamentals,
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


def normalize_service_symbol(symbol: str) -> str:
    return normalize_symbol(symbol)


def build_stock_valuation_inputs(
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
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
    )


def build_stock_valuation_config(
    configuration: ValuationConfiguration,
) -> StockValuationConfig:
    return StockValuationConfig(
        target_pe=configuration.target_pe,
        treasury_yield=configuration.treasury_yield,
        decision=configuration.decision,
    )


def analyze_stock(
    symbol: str,
    configuration: ValuationConfiguration,
) -> StockAnalysisServiceResult:
    normalized_symbol = normalize_service_symbol(symbol)
    company = download_company_fundamentals(normalized_symbol)
    if company.current_price is None:
        _raise_missing_current_price(normalized_symbol)

    treasury = download_treasury_yield_snapshot(configuration.treasury_history)
    valuation = calculate_stock_valuation(
        build_stock_valuation_inputs(company, treasury),
        build_stock_valuation_config(configuration),
    )

    return StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=valuation,
    )


def analyze_stock_from_config_file(
    symbol: str,
    config_path: str | Path = "config/valuation.yaml",
) -> StockAnalysisServiceResult:
    configuration = load_valuation_configuration(config_path)
    return analyze_stock(symbol, configuration)


def _raise_missing_current_price(symbol: str) -> None:
    raise StockAnalysisServiceError(
        f"Cannot analyze {symbol} because Yahoo current price is unavailable."
    )
