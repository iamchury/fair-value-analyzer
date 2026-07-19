from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.services.stock_analysis as stock_analysis
from src.config.eps_selection import (
    EPSSelectionConfiguration,
    EPSSelectionMethod,
    EPSSelectionRule,
)
from src.config.analyst_consensus import (
    AnalystConsensusConfiguration,
    AnalystConsensusRule,
    AnalystValuationMethod,
)
from src.config.agreement_engine import AgreementEngineConfiguration
from src.config.fair_value_range import (
    ConservativeRangeMethod,
    FairValueRangeConfiguration,
    OptimisticRangeMethod,
    RangeBaseMethod,
)
from src.config.momentum_reference import MomentumReferenceConfiguration
from src.config.industry_policies import (
    IndustryPolicyConfiguration,
    IndustryValuationPolicy,
    TargetPEMode,
    ValuationStyle as IndustryValuationStyle,
)
from src.analysis.macro_adjustment import TreasuryYieldConfig
from src.analysis.stock_valuation import (
    StockValuationResult,
    StockValuationStatus,
)
from src.analysis.valuation_snapshot import ValuationModelType
from src.analysis.agreement_engine import AgreementLevel
from src.analysis.target_pe import TargetPEConfig
from src.analysis.valuation_decision import (
    ValuationDecisionConfig,
    ValuationRecommendation,
)
from src.config.valuation import ValuationConfiguration, ValuationConfigurationError
from src.config.valuation_profiles import ValuationProfile, ValuationStyle
from src.services.stock_analysis import (
    StockAnalysisServiceError,
    StockAnalysisServiceResult,
    StockAnalysisWithProfileResult,
    analyze_stock,
    analyze_stock_from_config_file,
    analyze_stock_with_profile,
    analyze_stock_with_profile_from_config_files,
    build_resilient_treasury_snapshot,
    build_stock_valuation_config,
    build_stock_valuation_inputs,
    normalize_service_symbol,
)
from src.yahoo.company import CompanyFundamentals
from src.yahoo.company import (
    CompanyFundamentalsWithEPSRawSnapshot,
    EPSRawFieldSource,
    YahooEPSEstimate,
    YahooEPSRawSnapshot,
)
from src.yahoo.treasury import TreasuryDataStatus, TreasuryHistoryConfig, TreasuryYieldSnapshot
from src.yahoo.prices import HistoricalPriceRow, HistoricalPriceSeries


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
        maximum_eps_growth_percent=40.0,
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
    assert result.valuation_snapshots is not None
    assert result.valuation_snapshots.get(ValuationModelType.AUTOMATIC_PER) is not None


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


def test_analyze_stock_uses_configured_fallback_when_treasury_download_fails(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
) -> None:
    stock_analysis._TREASURY_CACHE.clear()
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

    result = analyze_stock("LITE", configuration)

    assert result.treasury.data_status == TreasuryDataStatus.CONFIG_FALLBACK
    assert result.treasury.current_yield_percent == pytest.approx(4.3)
    assert result.valuation.status == StockValuationStatus.COMPLETE


def test_analyze_stock_can_fail_fast_on_treasury_download_error(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
) -> None:
    fail_fast_configuration = replace(
        configuration,
        treasury_history=replace(
            configuration.treasury_history,
            fail_analysis_on_download_error=True,
        ),
    )
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
        analyze_stock("LITE", fail_fast_configuration)


def test_build_resilient_treasury_snapshot_uses_recent_cache(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    treasury: TreasuryYieldSnapshot,
) -> None:
    now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
    stock_analysis._TREASURY_CACHE.clear()
    stock_analysis._TREASURY_CACHE["^TNX"] = replace(treasury, fetched_at=now)
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    snapshot = build_resilient_treasury_snapshot(configuration, now=now)

    assert snapshot.data_status == TreasuryDataStatus.CACHED
    assert snapshot.current_yield_percent == treasury.current_yield_percent
    assert snapshot.used_fallback is True
    assert "Using cached Treasury data" in snapshot.warnings[0]


def test_build_resilient_treasury_snapshot_marks_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    treasury: TreasuryYieldSnapshot,
) -> None:
    now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
    stock_analysis._TREASURY_CACHE.clear()
    stock_analysis._TREASURY_CACHE["^TNX"] = replace(
        treasury,
        fetched_at=now - timedelta(hours=25),
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    snapshot = build_resilient_treasury_snapshot(configuration, now=now)

    assert snapshot.data_status == TreasuryDataStatus.STALE_FALLBACK
    assert snapshot.used_fallback is True


def test_build_resilient_treasury_snapshot_uses_neutral_fallback_without_configured_yield(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    stock_analysis._TREASURY_CACHE.clear()
    neutral_configuration = replace(
        configuration,
        treasury_history=replace(
            configuration.treasury_history,
            fallback_yield_percent=None,
            allow_config_fallback=False,
        ),
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    snapshot = build_resilient_treasury_snapshot(neutral_configuration)

    assert snapshot.data_status == TreasuryDataStatus.UNAVAILABLE
    assert snapshot.current_yield_percent == pytest.approx(
        neutral_configuration.treasury_yield.threshold_yield_percent
    )
    assert snapshot.used_fallback is True


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


def test_analyze_stock_with_profile_downloads_once_and_adds_research_valuation(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    calls = []
    profile = ValuationProfile(
        symbol="LITE",
        valuation_style=ValuationStyle.GROWTH,
        valuation_eps=18.30,
        eps_fiscal_year="FY2027",
        target_pe=40.0,
        use_peg_adjustment=True,
        dcf_fair_value=None,
        source_note="research note",
    )

    def fake_download_company(symbol: str) -> CompanyFundamentals:
        calls.append(("company", symbol))
        return company

    def fake_download_treasury(config: TreasuryHistoryConfig) -> TreasuryYieldSnapshot:
        calls.append(("treasury", config))
        return treasury

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

    result = analyze_stock_with_profile("lite", configuration, {"LITE": profile})

    assert isinstance(result, StockAnalysisWithProfileResult)
    assert calls == [("company", "LITE"), ("treasury", configuration.treasury_history)]
    assert result.profile is profile
    assert result.research_valuation is not None
    assert result.research_valuation.research_base_fair_value == pytest.approx(732.0)
    assert result.research_valuation.research_adjusted_fair_value == pytest.approx(
        599.508
    )
    assert result.valuation_comparison is not None
    assert result.valuation_comparison.automatic_fair_value == pytest.approx(147.42)
    assert result.valuation_snapshots is not None
    assert result.valuation_snapshots.get(ValuationModelType.AUTOMATIC_PER) is not None
    assert result.valuation_snapshots.get(ValuationModelType.RESEARCH_PER) is not None
    assert result.valuation_snapshots.get(ValuationModelType.DCF_REFERENCE) is None


def test_analyze_stock_with_profile_returns_no_research_for_unmatched_symbol(
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

    result = analyze_stock_with_profile("lite", configuration, {})

    assert result.profile is None
    assert result.research_valuation is None
    assert result.valuation_comparison is None


def test_analyze_stock_with_profile_from_config_files_loads_once_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    profiles = object()
    expected = object()

    def fake_load_configuration(path):
        calls.append(("valuation", path))
        return configuration

    def fake_load_profiles(path):
        calls.append(("profiles", path))
        return profiles

    def fake_analyze(symbol, loaded_configuration, loaded_profiles):
        calls.append(("analyze", symbol, loaded_configuration, loaded_profiles))
        return expected

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        fake_load_configuration,
    )
    monkeypatch.setattr(stock_analysis, "load_valuation_profiles", fake_load_profiles)
    monkeypatch.setattr(stock_analysis, "analyze_stock_with_profile", fake_analyze)

    assert (
        analyze_stock_with_profile_from_config_files(
            "LITE",
            config_path="valuation.yaml",
            profiles_path="profiles.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("profiles", "profiles.yaml"),
        ("analyze", "LITE", configuration, profiles),
    ]


def test_eps_selection_changes_fair_value_eps_only(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    treasury: TreasuryYieldSnapshot,
) -> None:
    from datetime import datetime, timezone

    stamp = datetime(2026, 7, 18, tzinfo=timezone.utc)
    company = CompanyFundamentals(
        symbol="MU",
        company_name="Micron",
        currency="USD",
        current_price=80.0,
        previous_close=None,
        market_cap=None,
        sector="Technology",
        industry="Semiconductors",
        trailing_eps=44.06,
        forward_eps=150.77,
        trailing_pe=None,
        forward_pe=None,
        peg_ratio=0.13,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        analyst_target_mean_price=None,
        analyst_target_high_price=None,
        analyst_target_low_price=None,
    )
    snapshot = YahooEPSRawSnapshot(
        symbol="MU",
        trailing_eps=44.06,
        forward_eps=150.77,
        trailing_pe=None,
        forward_pe=None,
        peg_ratio=0.13,
        earnings_growth=None,
        quarterly_earnings_growth=None,
        most_recent_quarter=None,
        last_fiscal_year_end=None,
        next_fiscal_year_end=None,
        last_split_date=None,
        shares_outstanding=None,
        implied_shares_outstanding=None,
        price_to_book=None,
        current_quarter_estimate=None,
        next_quarter_estimate=None,
        current_year_estimate=YahooEPSEstimate("0y", 73.37, None, None, None, 10),
        next_year_estimate=YahooEPSEstimate("+1y", 150.47, None, None, None, 10),
        source_timestamp=stamp,
        raw_field_sources=(
            EPSRawFieldSource(
                "forward_eps",
                "yfinance.Ticker.info",
                "forwardEps",
                150.77,
                None,
                stamp,
                None,
            ),
        ),
        warnings=(),
    )
    eps_config = EPSSelectionConfiguration(
        default_rule=EPSSelectionRule(
            method=EPSSelectionMethod.LEGACY_FORWARD,
            current_year_weight=None,
            next_year_weight=None,
            manual_eps=None,
            manual_period_label=None,
            rationale=None,
        ),
        symbol_rules={
            "MU": EPSSelectionRule(
                method=EPSSelectionMethod.CURRENT_YEAR,
                current_year_weight=None,
                next_year_weight=None,
                manual_eps=None,
                manual_period_label=None,
                rationale="Use current EPS.",
            )
        },
    )

    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals_with_eps_snapshot",
        lambda symbol: CompanyFundamentalsWithEPSRawSnapshot(company, snapshot),
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: treasury,
    )

    result = analyze_stock("MU", configuration, eps_config)

    assert result.valuation.forward_eps == 150.77
    assert result.valuation.eps_growth.forward_eps == 150.77
    assert result.valuation.target_pe.actual_eps_growth_percent == pytest.approx(
        242.19246482069903
    )
    assert result.valuation.valuation_eps_used == 73.37
    assert result.valuation.valuation_eps_method == "CURRENT_YEAR"
    assert result.valuation.fair_value.forward_eps == 73.37
    assert result.valuation.fair_value.base_fair_value == pytest.approx(3668.5)
    assert result.eps_selection is not None
    assert result.eps_selection.selected_eps == 73.37


def test_analyze_stock_from_config_file_loads_eps_selection_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    eps_config = object()
    expected = object()

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or configuration,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_eps_selection_configuration",
        lambda path: calls.append(("eps", path)) or eps_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "analyze_stock",
        lambda symbol, config, eps=None: calls.append(("analyze", symbol, config, eps)) or expected,
    )

    assert (
        analyze_stock_from_config_file(
            "MU",
            config_path="valuation.yaml",
            eps_selection_path="eps.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("eps", "eps.yaml"),
        ("analyze", "MU", configuration, eps_config),
    ]


def test_analyze_stock_applies_industry_policy_without_extra_downloads(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    treasury: TreasuryYieldSnapshot,
) -> None:
    calls = []
    company = CompanyFundamentals(
        symbol="MU",
        company_name="Micron",
        currency="USD",
        current_price=80.0,
        previous_close=None,
        market_cap=None,
        sector="Technology",
        industry="Semiconductors",
        trailing_eps=44.06,
        forward_eps=150.77,
        trailing_pe=None,
        forward_pe=5.63,
        peg_ratio=0.13,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        analyst_target_mean_price=None,
        analyst_target_high_price=None,
        analyst_target_low_price=None,
    )
    policy = IndustryValuationPolicy(
        name="CYCLICAL",
        valuation_style=IndustryValuationStyle.CYCLICAL,
        target_pe_mode=TargetPEMode.FIXED,
        fixed_target_pe=10.0,
        minimum_target_pe=7.0,
        maximum_target_pe=12.0,
        use_eps_growth=False,
        use_peg_adjustment=False,
        use_sector_adjustment=False,
        use_forward_pe_penalty=False,
        rationale="cyclical",
    )
    industry_config = IndustryPolicyConfiguration(
        policies={"CYCLICAL": policy},
        symbol_policy_names={"MU": "CYCLICAL"},
    )

    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: calls.append(("company", symbol)) or company,
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: calls.append(("treasury", config)) or treasury,
    )

    result = analyze_stock(
        "MU",
        configuration,
        industry_policy_config=industry_config,
    )

    assert calls == [("company", "MU"), ("treasury", configuration.treasury_history)]
    assert result.valuation.target_pe.recommended_target_pe == 50.0
    assert result.valuation.target_pe_used == 10.0
    assert result.industry_policy.policy_name == "CYCLICAL"
    assert result.valuation.fair_value.forward_eps == 150.77


def test_analyze_stock_adds_analyst_snapshot_without_extra_downloads(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    calls = []
    analyst_config = AnalystConsensusConfiguration(
        default_rule=AnalystConsensusRule(
            enabled=True,
            valuation_method=AnalystValuationMethod.WEIGHTED_MEAN_MIDPOINT,
            mean_weight=0.7,
            midpoint_weight=0.3,
            apply_treasury=False,
            low_dispersion=25.0,
            medium_dispersion=60.0,
            high_dispersion=100.0,
            rationale="analyst",
        ),
        symbol_rules={},
    )

    monkeypatch.setattr(
        stock_analysis,
        "download_company_fundamentals",
        lambda symbol: calls.append(("company", symbol)) or company,
    )
    monkeypatch.setattr(
        stock_analysis,
        "download_treasury_yield_snapshot",
        lambda config: calls.append(("treasury", config)) or treasury,
    )

    result = analyze_stock(
        "LITE",
        configuration,
        analyst_consensus_config=analyst_config,
    )

    assert calls == [("company", "LITE"), ("treasury", configuration.treasury_history)]
    assert result.analyst_consensus is not None
    assert result.analyst_consensus.model_type == ValuationModelType.ANALYST_CONSENSUS
    assert result.analyst_consensus.selected_fair_value == pytest.approx(91.5)
    assert result.valuation.valuation_decision.recommendation == ValuationRecommendation.BUY
    assert result.valuation_snapshots is not None
    assert result.valuation_snapshots.get(ValuationModelType.ANALYST_CONSENSUS) is (
        result.analyst_consensus
    )


def test_analyze_stock_adds_agreement_from_existing_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    agreement_config = AgreementEngineConfiguration(
        enabled=True,
        strong_threshold_pct=10.0,
        moderate_threshold_pct=20.0,
        weak_threshold_pct=35.0,
        outlier_threshold_pct=50.0,
        extreme_outlier_threshold_pct=80.0,
        minimum_primary_models=1,
        include_reference_in_intrinsic_cluster=True,
        market_expectation_affects_overall_agreement=False,
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

    result = analyze_stock("LITE", configuration, agreement_config=agreement_config)

    assert result.agreement_result is not None
    assert result.valuation_snapshots is not None
    assert result.agreement_result.overall_agreement == AgreementLevel.INSUFFICIENT
    assert result.valuation.valuation_decision.recommendation == ValuationRecommendation.BUY


def test_analyze_stock_from_config_file_loads_agreement_config_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    agreement_config = object()
    expected = object()

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or configuration,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_agreement_engine_configuration",
        lambda path: calls.append(("agreement", path)) or agreement_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "analyze_stock",
        lambda symbol, config, eps=None, industry=None, analyst=None, agreement=None: calls.append(
            ("analyze", symbol, config, eps, industry, analyst, agreement)
        )
        or expected,
    )

    assert (
        analyze_stock_from_config_file(
            "MU",
            config_path="valuation.yaml",
            agreement_config_path="agreement.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("agreement", "agreement.yaml"),
        ("analyze", "MU", configuration, None, None, None, agreement_config),
    ]


def test_analyze_stock_from_config_file_loads_industry_policy_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    industry_config = object()
    expected = object()

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or configuration,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_industry_policy_configuration",
        lambda path: calls.append(("industry", path)) or industry_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "analyze_stock",
        lambda symbol, config, eps=None, industry=None: calls.append(
            ("analyze", symbol, config, eps, industry)
        )
        or expected,
    )

    assert (
        analyze_stock_from_config_file(
            "MU",
            config_path="valuation.yaml",
            industry_policies_path="industry.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("industry", "industry.yaml"),
        ("analyze", "MU", configuration, None, industry_config),
    ]


def test_analyze_stock_adds_momentum_and_range_without_changing_recommendation(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
    company: CompanyFundamentals,
    treasury: TreasuryYieldSnapshot,
) -> None:
    history_calls = []
    monkeypatch.setattr(stock_analysis, "download_company_fundamentals", lambda symbol: company)
    monkeypatch.setattr(stock_analysis, "download_treasury_yield_snapshot", lambda config: treasury)
    monkeypatch.setattr(
        stock_analysis,
        "download_daily_price_history",
        lambda symbol, period, interval: history_calls.append((symbol, period, interval))
        or _price_history(symbol),
    )

    result = analyze_stock(
        "LITE",
        configuration,
        momentum_config=_momentum_config(),
        range_config=_range_config(),
    )

    assert history_calls == [("LITE", "1y", "1d")]
    assert result.momentum_reference is not None
    assert result.fair_value_range is not None
    assert result.valuation_snapshots is not None
    assert result.valuation.valuation_decision.recommendation == ValuationRecommendation.BUY


def test_analyze_stock_from_config_file_loads_momentum_and_range_configs_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    momentum_config = object()
    range_config = object()
    expected = object()

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or configuration,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_momentum_reference_configuration",
        lambda path: calls.append(("momentum", path)) or momentum_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_fair_value_range_configuration",
        lambda path: calls.append(("range", path)) or range_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "analyze_stock",
        lambda symbol, config, eps=None, industry=None, analyst=None, agreement=None, momentum=None, fair_range=None: calls.append(
            ("analyze", symbol, config, eps, industry, analyst, agreement, momentum, fair_range)
        )
        or expected,
    )

    assert (
        analyze_stock_from_config_file(
            "MU",
            config_path="valuation.yaml",
            momentum_config_path="momentum.yaml",
            range_config_path="range.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("momentum", "momentum.yaml"),
        ("range", "range.yaml"),
        ("analyze", "MU", configuration, None, None, None, None, momentum_config, range_config),
    ]


def test_analyze_stock_from_config_file_loads_recommendation_v2_config_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    configuration: ValuationConfiguration,
) -> None:
    calls = []
    recommendation_config = object()
    expected = object()

    monkeypatch.setattr(
        stock_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or configuration,
    )
    monkeypatch.setattr(
        stock_analysis,
        "load_recommendation_v2_configuration",
        lambda path: calls.append(("recommendation_v2", path)) or recommendation_config,
    )
    monkeypatch.setattr(
        stock_analysis,
        "analyze_stock",
        lambda symbol, config, eps=None, industry=None, analyst=None, agreement=None, momentum=None, fair_range=None, recommendation_v2=None: calls.append(
            ("analyze", symbol, config, eps, industry, analyst, agreement, momentum, fair_range, recommendation_v2)
        )
        or expected,
    )

    assert (
        analyze_stock_from_config_file(
            "MU",
            config_path="valuation.yaml",
            recommendation_v2_config_path="recommendation.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("recommendation_v2", "recommendation.yaml"),
        ("analyze", "MU", configuration, None, None, None, None, None, None, recommendation_config),
    ]


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


def _momentum_config() -> MomentumReferenceConfiguration:
    return MomentumReferenceConfiguration(
        enabled=True,
        rsi_period=14,
        neutral_level=50.0,
        history_period="1y",
        history_interval="1d",
        minimum_observations=30,
        fallback_to_nearest=True,
        prefer_adjusted_close=True,
    )


def _range_config() -> FairValueRangeConfiguration:
    return FairValueRangeConfiguration(
        enabled=True,
        include_reference_values=True,
        include_low_confidence_intrinsic=True,
        exclude_outliers=True,
        base_method=RangeBaseMethod.CONFIDENCE_WEIGHTED_MEDIAN,
        conservative_method=ConservativeRangeMethod.LOWER_SUPPORT,
        optimistic_method=OptimisticRangeMethod.UPPER_INTRINSIC_SUPPORT,
        high_confidence_weight=1.0,
        medium_confidence_weight=0.75,
        low_confidence_weight=0.5,
        unknown_confidence_weight=0.25,
        minimum_intrinsic_models=1,
        reference_value_weight=0.5,
        market_expectation_in_intrinsic_range=False,
        show_market_expectation_separately=True,
        show_momentum_reference_separately=True,
        deep_undervalued_pct=-30.0,
        undervalued_pct=-10.0,
        near_fair_upper_pct=10.0,
        above_fair_pct=20.0,
    )


def _price_history(symbol: str) -> HistoricalPriceSeries:
    start = date(2026, 1, 1)
    rows = tuple(
        HistoricalPriceRow(
            date=start + timedelta(days=index),
            close=100.0,
            adjusted_close=100.0,
        )
        for index in range(31)
    )
    return HistoricalPriceSeries(symbol=symbol, rows=rows)
