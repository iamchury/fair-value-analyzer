from dataclasses import FrozenInstanceError

import pytest

import src.services.batch_analysis as batch_analysis
from src.config.stocks import StocksConfiguration
from src.config.eps_selection import EPSSelectionConfiguration
from src.config.industry_policies import IndustryPolicyConfiguration
from src.config.valuation import ValuationConfigurationError
from src.services.batch_analysis import (
    BatchStockAnalysisResult,
    StockAnalysisFailure,
    analyze_stocks,
    analyze_stocks_from_config_files,
    analyze_stocks_with_profiles,
    analyze_stocks_with_profiles_from_config_files,
)
from src.services.stock_analysis import StockAnalysisServiceError


def test_analyze_stocks_is_sequential_and_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    configuration = object()
    calls = []
    results = {"LITE": object(), "MU": object(), "NVDA": object()}

    def fake_analyze(symbol: str, config: object):
        calls.append((symbol, config))
        if symbol == "MU":
            raise RuntimeError("Yahoo failed")
        return results[symbol]

    monkeypatch.setattr(batch_analysis, "analyze_stock", fake_analyze)

    result = analyze_stocks(["lite", "mu", "nvda"], configuration)

    assert calls == [("LITE", configuration), ("MU", configuration), ("NVDA", configuration)]
    assert result.requested_symbols == ("LITE", "MU", "NVDA")
    assert result.successful_results == (results["LITE"], results["NVDA"])
    assert result.failures == (
        StockAnalysisFailure("MU", "RuntimeError", "Yahoo failed"),
    )
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.total_count == 3


def test_multiple_expected_failures_are_retained_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_analyze(symbol: str, config: object):
        if symbol == "LITE":
            raise StockAnalysisServiceError("missing price")
        if symbol == "MU":
            raise ValueError("bad symbol")
        return object()

    monkeypatch.setattr(batch_analysis, "analyze_stock", fake_analyze)

    result = analyze_stocks(["LITE", "MU", "AMAT"], object())

    assert result.failure_count == 2
    assert [failure.symbol for failure in result.failures] == ["LITE", "MU"]
    assert [failure.error_type for failure in result.failures] == [
        "StockAnalysisServiceError",
        "ValueError",
    ]
    assert [failure.message for failure in result.failures] == [
        "missing price",
        "bad symbol",
    ]


@pytest.mark.parametrize("symbols", [[], (), "LITE"])
def test_empty_or_invalid_symbol_sequence_rejected(symbols: object) -> None:
    with pytest.raises(ValueError):
        analyze_stocks(symbols, object())


def test_duplicate_symbols_rejected() -> None:
    with pytest.raises(ValueError, match="LITE is duplicated"):
        analyze_stocks(["LITE", "lite"], object())


def test_unexpected_programming_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        batch_analysis,
        "analyze_stock",
        lambda symbol, config: (_ for _ in ()).throw(AttributeError("bug")),
    )

    with pytest.raises(AttributeError, match="bug"):
        analyze_stocks(["LITE"], object())


def test_batch_result_dataclasses_are_immutable() -> None:
    failure = StockAnalysisFailure("LITE", "RuntimeError", "failed")
    result = BatchStockAnalysisResult(("LITE",), (), (failure,))

    with pytest.raises(FrozenInstanceError):
        failure.message = "changed"
    with pytest.raises(FrozenInstanceError):
        result.failures = ()


def test_file_loading_entry_point_loads_once_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    valuation_config = object()
    stocks_config = StocksConfiguration(("LITE", "MU"))
    expected = object()

    def fake_load_valuation(path):
        calls.append(("valuation", path))
        return valuation_config

    def fake_load_stocks(path):
        calls.append(("stocks", path))
        return stocks_config

    def fake_analyze(symbols, config):
        calls.append(("analyze", symbols, config))
        return expected

    monkeypatch.setattr(batch_analysis, "load_valuation_configuration", fake_load_valuation)
    monkeypatch.setattr(batch_analysis, "load_stocks_configuration", fake_load_stocks)
    monkeypatch.setattr(batch_analysis, "analyze_stocks", fake_analyze)

    result = analyze_stocks_from_config_files("stocks.yaml", "valuation.yaml")

    assert result is expected
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("stocks", "stocks.yaml"),
        ("analyze", ("LITE", "MU"), valuation_config),
    ]


def test_global_configuration_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        batch_analysis,
        "load_valuation_configuration",
        lambda path: (_ for _ in ()).throw(ValuationConfigurationError("bad config")),
    )

    with pytest.raises(ValuationConfigurationError, match="bad config"):
        analyze_stocks_from_config_files()


def test_analyze_stocks_with_profiles_passes_profile_mapping_to_each_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = object()
    profiles = object()
    calls = []
    expected = {"LITE": object(), "MU": object()}

    def fake_analyze(symbol: str, config: object, loaded_profiles: object):
        calls.append((symbol, config, loaded_profiles))
        return expected[symbol]

    monkeypatch.setattr(batch_analysis, "analyze_stock_with_profile", fake_analyze)

    result = analyze_stocks_with_profiles(["lite", "mu"], configuration, profiles)

    assert calls == [
        ("LITE", configuration, profiles),
        ("MU", configuration, profiles),
    ]
    assert result.successful_results == (expected["LITE"], expected["MU"])
    assert result.failures == ()


def test_profile_batch_file_loading_entry_point_loads_profiles_once_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    valuation_config = object()
    profiles = object()
    stocks_config = StocksConfiguration(("LITE", "MU"))
    expected = object()

    def fake_load_valuation(path):
        calls.append(("valuation", path))
        return valuation_config

    def fake_load_stocks(path):
        calls.append(("stocks", path))
        return stocks_config

    def fake_load_profiles(path):
        calls.append(("profiles", path))
        return profiles

    def fake_analyze(symbols, config, loaded_profiles):
        calls.append(("analyze", symbols, config, loaded_profiles))
        return expected

    monkeypatch.setattr(batch_analysis, "load_valuation_configuration", fake_load_valuation)
    monkeypatch.setattr(batch_analysis, "load_stocks_configuration", fake_load_stocks)
    monkeypatch.setattr(batch_analysis, "load_valuation_profiles", fake_load_profiles)
    monkeypatch.setattr(batch_analysis, "analyze_stocks_with_profiles", fake_analyze)

    result = analyze_stocks_with_profiles_from_config_files(
        stocks_path="stocks.yaml",
        valuation_config_path="valuation.yaml",
        profiles_path="profiles.yaml",
    )

    assert result is expected
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("stocks", "stocks.yaml"),
        ("profiles", "profiles.yaml"),
        ("analyze", ("LITE", "MU"), valuation_config, profiles),
    ]


def test_batch_file_loading_loads_eps_selection_once_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    valuation_config = object()
    eps_config = object()
    stocks_config = StocksConfiguration(("LITE", "MU"))
    expected = object()

    monkeypatch.setattr(
        batch_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or valuation_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "load_stocks_configuration",
        lambda path: calls.append(("stocks", path)) or stocks_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "load_eps_selection_configuration",
        lambda path: calls.append(("eps", path)) or eps_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "analyze_stocks",
        lambda symbols, config, eps=None: calls.append(("analyze", symbols, config, eps)) or expected,
    )

    assert (
        analyze_stocks_from_config_files(
            stocks_path="stocks.yaml",
            valuation_config_path="valuation.yaml",
            eps_selection_path="eps.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("stocks", "stocks.yaml"),
        ("eps", "eps.yaml"),
        ("analyze", ("LITE", "MU"), valuation_config, eps_config),
    ]


def test_batch_file_loading_loads_industry_policy_once_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    valuation_config = object()
    industry_config = object()
    stocks_config = StocksConfiguration(("LITE", "MU"))
    expected = object()

    monkeypatch.setattr(
        batch_analysis,
        "load_valuation_configuration",
        lambda path: calls.append(("valuation", path)) or valuation_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "load_stocks_configuration",
        lambda path: calls.append(("stocks", path)) or stocks_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "load_industry_policy_configuration",
        lambda path: calls.append(("industry", path)) or industry_config,
    )
    monkeypatch.setattr(
        batch_analysis,
        "analyze_stocks",
        lambda symbols, config, eps=None, industry=None: calls.append(
            ("analyze", symbols, config, eps, industry)
        )
        or expected,
    )

    assert (
        analyze_stocks_from_config_files(
            stocks_path="stocks.yaml",
            valuation_config_path="valuation.yaml",
            industry_policies_path="industry.yaml",
        )
        is expected
    )
    assert calls == [
        ("valuation", "valuation.yaml"),
        ("stocks", "stocks.yaml"),
        ("industry", "industry.yaml"),
        ("analyze", ("LITE", "MU"), valuation_config, None, industry_config),
    ]
