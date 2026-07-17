from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import src.services.stock_analysis as stock_analysis
from src.analysis.macro_adjustment import TreasuryYieldConfig
from src.analysis.stock_valuation import (
    StockValuationResult,
    StockValuationStatus,
)
from src.analysis.target_pe import TargetPEConfig
from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    ValuationRecommendation,
)
from src.config.valuation import ValuationConfiguration, ValuationConfigurationError
from src.services.stock_analysis import (
    StockAnalysisServiceError,
    StockAnalysisServiceResult,
    analyze_stock,
    analyze_stock_from_config_file,
    build_stock_valuation_config,
    build_stock_valuation_inputs,
    normalize_service_symbol,
)
from src.yahoo.company import CompanyFundamentals
from src.yahoo.treasury import TreasuryHistoryConfig, TreasuryYieldSnapshot


@pytest.fixture
def treasury_history_config() -> TreasuryHistoryConfig:
    return TreasuryHistoryConfig(
        symbol="^TNX",
        value_scale="percent",
        short_window_observations=20,
        long_window_observations=60,
    )


@pytest.fixture
def treasury_yield_config() -> TreasuryYieldConfig:
    return TreasuryYieldConfig(
        threshold_yield_percent=4.3,
        maximum_discount_percent=25.0,
        trend_tolerance_percentage_points=0.05,
        rising_adjustment_percent=-10.0,
        neutral_adjustment_percent=0.0,
        falling_adjustment_percent=10.0,
    )


@pytest.fixture
def target_pe_config() -> TargetPEConfig:
    return TargetPEConfig(
        minimum_target_pe=15.0,
        maximum_target_pe=50.0,
        default_target_peg=1.0,
        low_peg_threshold=1.0,
        normal_peg_upper_threshold=1.5,
        high_peg_threshold=2.0,
        low_peg_adjustment=5.0,
        normal_peg_adjustment=0.0,
        elevated_peg_adjustment=-2.0,
        high_peg_adjustment=-5.0,
        preferred_sector_adjustment=5.0,
        ordinary_sector_adjustment=0.0,
        high_forward_pe_premium_threshold=1.5,
        high_forward_pe_adjustment=-2.0,
        preferred_sectors=("Technology", "Communication Equipment"),
    )


@pytest.fixture
def decision_config() -> ValuationDecisionConfig:
    return ValuationDecisionConfig(
        buy_discount_percent=20.0,
        sell_premium_percent=20.0,
    )


@pytest.fixture
def configuration(
    treasury_history_config: TreasuryHistoryConfig,
    treasury_yield_config: TreasuryYieldConfig,
    target_pe_config: TargetPEConfig,
    decision_config: ValuationDecisionConfig,
) -> ValuationConfiguration:
    return ValuationConfiguration(
        treasury_history=treasury_history_config,
        treasury_yield=treasury_yield_config,
        target_pe=target_pe_config,
        decision=decision_config,
    )


@pytest.fixture
def company() -> CompanyFundamentals:
    return CompanyFundamentals(
        symbol="LITE",
        company_name="Lumentum Holdings Inc.",
        currency="USD",
        current_price=80.0,
        previous_close=79.0,
        market_cap=5_000_000_000.0,
        sector="Technology",
        industry="Communication Equipment",
        trailing_eps=5.0,
        forward_eps=6.0,
        trailing_pe=16.0,
        forward_pe=25.0,
        peg_ratio=0.95,
        fifty_two_week_high=100.0,
        fifty_two_week_low=45.0,
        analyst_target_mean_price=90.0,
        analyst_target_high_price=120.0,
        analyst_target_low_price=70.0,
    )


@pytest.fixture
def treasury() -> TreasuryYieldSnapshot:
    return TreasuryYieldSnapshot(
        symbol="^TNX",
        yield_date="2026-07-17",
        current_yield_percent=4.6,
        sma_short_percent=4.5,
        sma_long_percent=4.4,
        observation_count=250,
    )


def test_normalize_service_symbol_reuses_yahoo_symbol_policy() -> None:
    assert normalize_service_symbol(" lite ") == "LITE"
    assert normalize_service_symbol("^tnx") == "^TNX"
    assert normalize_service_symbol("brk-b") == "BRK-B"

    with pytest.raises(ValueError, match="spaces"):
        normalize_service_symbol("BRK B")


def test_build_stock_valuation_inputs_maps_company_and_treasury_fields(
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    inputs = build_stock_valuation_inputs(company, treasury)

    assert inputs.symbol == "LITE"
    assert inputs.current_price == 80.0
    assert inputs.trailing_eps == 5.0
    assert inputs.forward_eps == 6.0
    assert inputs.peg_ratio == 0.95
    assert inputs.sector == "Technology"
    assert inputs.industry == "Communication Equipment"
    assert inputs.current_forward_pe == 25.0
    assert inputs.treasury_current_yield_percent == 4.6
    assert inputs.treasury_short_sma_percent == 4.5
    assert inputs.treasury_long_sma_percent == 4.4


def test_build_stock_valuation_inputs_rejects_missing_current_price(
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    with pytest.raises(StockAnalysisServiceError, match="Cannot analyze LITE"):
        build_stock_valuation_inputs(
            replace(company, current_price=None),
            treasury,
        )


def test_build_stock_valuation_config_maps_existing_configuration_objects(
    configuration: ValuationConfiguration,
) -> None:
    config = build_stock_valuation_config(configuration)

    assert config.target_pe is configuration.target_pe
    assert config.treasury_yield is configuration.treasury_yield
    assert config.decision is configuration.decision
    assert not hasattr(config, "treasury_history")


def test_analyze_stock_calls_downloads_then_valuation_in_order(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    calls = []
    valuation = object()

    def fake_download_company(symbol: str) -> CompanyFundamentals:
        calls.append(("company", symbol))
        return company

    def fake_download_treasury(config: TreasuryHistoryConfig) -> TreasuryYieldSnapshot:
        calls.append(("treasury", config))
        return treasury

    def fake_calculate(inputs, config):
        calls.append(("valuation", inputs, config))
        return valuation

    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        fake_download_company,
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        fake_download_treasury,
    )
    monkeypatch.setattr(stock_analysis, "calculate_stock_valuation", fake_calculate)

    result = analyze_stock(" lite ", configuration)

    assert result == StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=valuation,
    )
    assert calls[0] == ("company", "LITE")
    assert calls[1] == ("treasury", configuration.treasury_history)
    assert calls[2][0] == "valuation"
    assert calls[2][1].symbol == "LITE"
    assert calls[2][2].target_pe is configuration.target_pe


def test_analyze_stock_uses_real_pure_valuation_calculation(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: company,
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: treasury,
    )

    result = analyze_stock("lite", configuration)

    assert isinstance(result.valuation, StockValuationResult)
    assert result.valuation.status == StockValuationStatus.COMPLETE
    assert result.valuation.target_pe.recommended_target_pe == 30.0
    assert result.valuation.macro_adjustment.total_adjustment_multiplier == (
        pytest.approx(0.819)
    )
    assert result.valuation.fair_value.adjusted_fair_value == pytest.approx(147.42)
    assert result.valuation.valuation_decision.recommendation == (
        ValuationRecommendation.BUY
    )


def test_analyze_stock_rejects_missing_current_price_before_treasury_download(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
) -> None:
    calls = []
    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: replace(company, current_price=None),
    )

    def fail_treasury(config):
        calls.append("treasury")
        raise AssertionError("Treasury should not be downloaded.")

    monkeypatch.setattr(stock_analysis, "download_treasury_yield_snapshot", fail_treasury)

    with pytest.raises(
        StockAnalysisServiceError,
        match="Cannot analyze LITE because Yahoo current price is unavailable.",
    ):
        analyze_stock("lite", configuration)

    assert calls == []


def test_analyze_stock_propagates_company_download_error(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    def fail_company(symbol: str) -> CompanyFundamentals:
        raise RuntimeError("company unavailable")

    monkeypatch.setattr(stock_analysis, "download_company_fundamentals", fail_company)

    with pytest.raises(RuntimeError, match="company unavailable"):
        analyze_stock("LITE", configuration)


def test_analyze_stock_propagates_treasury_download_error(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
) -> None:
    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: company,
    )

    def fail_treasury(config: TreasuryHistoryConfig) -> TreasuryYieldSnapshot:
        raise RuntimeError("treasury unavailable")

    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        fail_treasury,
    )

    with pytest.raises(RuntimeError, match="treasury unavailable"):
        analyze_stock("LITE", configuration)


def test_analyze_stock_propagates_nested_valuation_config_error(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    bad_configuration = replace(
        configuration,
        target_pe=replace(configuration.target_pe, maximum_target_pe=10.0),
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: company,
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: treasury,
    )

    with pytest.raises(ValueError, match="maximum_target_pe"):
        analyze_stock("LITE", bad_configuration)


def test_analyze_stock_from_config_file_loads_config_then_delegates(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    calls = []
    expected = StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=object(),
    )
    config_path = Path("custom.yaml")

    def fake_load(path):
        calls.append(("load", path))
        return configuration

    def fake_analyze(symbol, loaded_configuration):
        calls.append(("analyze", symbol, loaded_configuration))
        return expected

    monkeypatch.setattr(stock_analysis, "load_valuation_configuration", fake_load)
    monkeypatch.setattr(stock_analysis, "analyze_stock", fake_analyze)

    assert analyze_stock_from_config_file("lite", config_path) is expected
    assert calls == [
        ("load", config_path),
        ("analyze", "lite", configuration),
    ]


def test_analyze_stock_from_config_file_uses_default_config_path(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    paths = []
    expected = StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=object(),
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: paths.append(path) or configuration,
    )
    monkeypatch.setattr(stock_analysis, "analyze_stock", lambda symbol, config: expected)

    assert analyze_stock_from_config_file("LITE") is expected
    assert paths == ["config/valuation.yaml"]


def test_analyze_stock_from_config_file_propagates_loader_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_load(path):
        raise ValuationConfigurationError("config unavailable")

    monkeypatch.setattr(stock_analysis, "load_valuation_configuration", fail_load)

    with pytest.raises(ValuationConfigurationError, match="config unavailable"):
        analyze_stock_from_config_file("LITE")


def test_service_result_dataclass_is_immutable(
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    result = StockAnalysisServiceResult(
        company=company,
        treasury=treasury,
        valuation=object(),
    )

    with pytest.raises(FrozenInstanceError):
        result.company = company
