import pytest

import src.main as main_module
from src.config.eps_selection import EPSSelectionConfigurationError
from src.config.industry_policies import IndustryPolicyConfigurationError
from src.config.valuation import ValuationConfigurationError
from src.config.valuation_profiles import ValuationProfileConfigurationError
from src.services.batch_analysis import BatchStockAnalysisResult, StockAnalysisFailure
from src.services.stock_analysis import StockAnalysisServiceError


def test_success_uses_default_config_and_prints_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service_result = object()
    calls = []

    def fake_analyze(symbol: str, config_path: str):
        calls.append(("analyze", symbol, config_path))
        return service_result

    def fake_format(result: object) -> str:
        calls.append(("format", result))
        return "REPORT"

    monkeypatch.setattr(main_module, "analyze_stock_from_config_file", fake_analyze)
    monkeypatch.setattr(main_module, "format_stock_analysis_report", fake_format)

    exit_code = main_module.main(["LITE"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        ("analyze", "LITE", "config/valuation.yaml"),
        ("format", service_result),
    ]
    assert captured.out == "REPORT\n"
    assert captured.err == ""


def test_success_uses_custom_config_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = []
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda symbol, config_path: paths.append((symbol, config_path)) or object(),
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda result: "OK")

    exit_code = main_module.main(["LITE", "--config", "custom.yaml"])

    assert exit_code == 0
    assert paths == [("LITE", "custom.yaml")]
    assert capsys.readouterr().out == "OK\n"


@pytest.mark.parametrize(
    "error",
    [
        StockAnalysisServiceError("Cannot analyze LITE."),
        ValuationConfigurationError("bad config"),
        RuntimeError("Yahoo failed"),
        ValueError("bad value"),
    ],
)
def test_expected_errors_print_concise_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def fail_analyze(symbol: str, config_path: str):
        raise error

    monkeypatch.setattr(main_module, "analyze_stock_from_config_file", fail_analyze)
    monkeypatch.setattr(
        main_module,
        "format_stock_analysis_report",
        lambda result: "SHOULD NOT PRINT",
    )

    exit_code = main_module.main(["LITE"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == f"Error: {error}\n"
    assert "Traceback" not in captured.err


def test_formatter_error_is_handled_as_expected_value_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda symbol, config_path: object(),
    )

    def fail_format(result: object) -> str:
        raise ValueError("format failed")

    monkeypatch.setattr(main_module, "format_stock_analysis_report", fail_format)

    assert main_module.main(["LITE"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: format failed\n"


def test_missing_symbol_causes_argparse_exit_2() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main([])

    assert exc_info.value.code == 2


def test_help_causes_argparse_exit_0(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "Analyze a stock using EPS growth" in captured.out


def test_unknown_option_causes_argparse_exit_2() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["LITE", "--unknown"])

    assert exc_info.value.code == 2


def test_main_uses_explicit_argv_not_global_sys_argv(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    symbols = []
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["prog", "GLOBAL"],
    )
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda symbol, config_path: symbols.append(symbol) or object(),
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda result: "OK")

    assert main_module.main(["LOCAL"]) == 0
    assert symbols == ["LOCAL"]
    assert capsys.readouterr().out == "OK\n"


def test_batch_success_uses_stocks_and_config_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    batch_result = BatchStockAnalysisResult(("LITE", "MU"), (object(), object()), ())
    calls = []

    def fake_batch(stocks_path: str, valuation_config_path: str):
        calls.append(("batch", stocks_path, valuation_config_path))
        return batch_result

    def fake_format(result: object) -> str:
        calls.append(("format", result))
        return "BATCH REPORT"

    monkeypatch.setattr(main_module, "analyze_stocks_from_config_files", fake_batch)
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", fake_format)
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda symbol, config_path: (_ for _ in ()).throw(
            AssertionError("single service should not be called")
        ),
    )

    exit_code = main_module.main(
        ["--stocks", "stocks.yaml", "--config", "valuation.yaml"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        ("batch", "stocks.yaml", "valuation.yaml"),
        ("format", batch_result),
    ]
    assert captured.out == "BATCH REPORT\n"
    assert captured.err == ""


def test_batch_partial_success_returns_3_with_empty_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(
        ("LITE", "MU"),
        (object(),),
        (StockAnalysisFailure("MU", "RuntimeError", "failed"),),
    )
    monkeypatch.setattr(main_module, "analyze_stocks_from_config_files", lambda **kwargs: result)
    monkeypatch.setattr(
        main_module,
        "format_batch_stock_analysis_report",
        lambda batch_result: "REPORT WITH RuntimeError: failed",
    )

    assert main_module.main(["--stocks", "stocks.yaml"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "REPORT WITH RuntimeError: failed\n"
    assert captured.err == ""


def test_batch_all_failure_returns_1_and_prints_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(
        ("LITE",),
        (),
        (StockAnalysisFailure("LITE", "RuntimeError", "failed"),),
    )
    monkeypatch.setattr(main_module, "analyze_stocks_from_config_files", lambda **kwargs: result)
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", lambda result: "FAIL REPORT")

    assert main_module.main(["--stocks", "stocks.yaml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "FAIL REPORT\n"
    assert captured.err == ""


def test_global_batch_error_prints_stderr_and_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_batch(**kwargs):
        raise ValuationConfigurationError("bad batch config")

    monkeypatch.setattr(main_module, "analyze_stocks_from_config_files", fail_batch)
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", lambda result: "NOPE")

    assert main_module.main(["--stocks", "stocks.yaml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: bad batch config\n"


def test_both_symbol_and_stocks_causes_argparse_exit_2() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["LITE", "--stocks", "stocks.yaml"])

    assert exc_info.value.code == 2


def test_batch_service_not_called_in_single_stock_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        main_module,
        "analyze_stocks_from_config_files",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("batch service should not be called")
        ),
    )
    monkeypatch.setattr(main_module, "analyze_stock_from_config_file", lambda **kwargs: object())
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda result: "SINGLE")

    assert main_module.main(["LITE"]) == 0
    assert capsys.readouterr().out == "SINGLE\n"


def test_single_profile_option_uses_profile_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_with_profile_from_config_files",
        lambda **kwargs: calls.append(("profile", kwargs)) or result,
    )
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("base service should not be called")
        ),
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "PROFILE")

    exit_code = main_module.main(
        ["LITE", "--config", "valuation.yaml", "--profiles", "profiles.yaml"]
    )

    assert exit_code == 0
    assert calls == [
        (
            "profile",
            {
                "symbol": "LITE",
                "config_path": "valuation.yaml",
                "profiles_path": "profiles.yaml",
            },
        )
    ]
    assert capsys.readouterr().out == "PROFILE\n"


def test_batch_profile_option_uses_profile_batch_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(("LITE",), (object(),), ())
    calls = []

    monkeypatch.setattr(
        main_module,
        "analyze_stocks_with_profiles_from_config_files",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(
        main_module,
        "analyze_stocks_from_config_files",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("base batch service should not be called")
        ),
    )
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", lambda value: "BATCH")

    exit_code = main_module.main(
        ["--stocks", "stocks.yaml", "--config", "valuation.yaml", "--profiles", "profiles.yaml"]
    )

    assert exit_code == 0
    assert calls == [
        {
            "stocks_path": "stocks.yaml",
            "valuation_config_path": "valuation.yaml",
            "profiles_path": "profiles.yaml",
        }
    ]
    assert capsys.readouterr().out == "BATCH\n"


def test_profile_configuration_error_prints_concise_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = ValuationProfileConfigurationError("bad profile config")

    monkeypatch.setattr(
        main_module,
        "analyze_stock_with_profile_from_config_files",
        lambda **kwargs: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(
        main_module,
        "format_stock_analysis_report",
        lambda result: "SHOULD NOT PRINT",
    )

    exit_code = main_module.main(["LITE", "--profiles", "profiles.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "Error: bad profile config\n"


def test_inspect_eps_uses_eps_service_and_formatter(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "inspect_stock_eps",
        lambda **kwargs: calls.append(("inspect", kwargs)) or result,
    )
    monkeypatch.setattr(
        main_module,
        "format_eps_inspection_report",
        lambda value: calls.append(("format", value)) or "EPS REPORT",
    )
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("valuation service should not be called")
        ),
    )
    monkeypatch.setattr(
        main_module,
        "analyze_stock_with_profile_from_config_files",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("profile service should not be called")
        ),
    )

    exit_code = main_module.main(["MU", "--inspect-eps", "--profiles", "profiles.yaml"])

    assert exit_code == 0
    assert calls == [("inspect", {"symbol": "MU"}), ("format", result)]
    assert capsys.readouterr().out == "EPS REPORT\n"


def test_inspect_eps_with_stocks_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["--stocks", "stocks.yaml", "--inspect-eps"])

    assert exc_info.value.code == 2


def test_inspect_eps_without_symbol_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["--inspect-eps"])

    assert exc_info.value.code == 2


def test_single_eps_selection_option_uses_existing_single_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "EPS")

    assert main_module.main(["MU", "--eps-selection", "eps.yaml"]) == 0
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "eps_selection_path": "eps.yaml",
        }
    ]
    assert capsys.readouterr().out == "EPS\n"


def test_batch_eps_selection_option_uses_batch_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(("MU",), (object(),), ())
    calls = []

    monkeypatch.setattr(
        main_module,
        "analyze_stocks_from_config_files",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", lambda value: "BATCH")

    assert main_module.main(["--stocks", "stocks.yaml", "--eps-selection", "eps.yaml"]) == 0
    assert calls == [
        {
            "stocks_path": "stocks.yaml",
            "valuation_config_path": "config/valuation.yaml",
            "eps_selection_path": "eps.yaml",
        }
    ]
    assert capsys.readouterr().out == "BATCH\n"


def test_profiles_and_eps_selection_together_use_profile_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_with_profile_from_config_files",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "BOTH")

    assert (
        main_module.main(
            ["MU", "--profiles", "profiles.yaml", "--eps-selection", "eps.yaml"]
        )
        == 0
    )
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "profiles_path": "profiles.yaml",
            "eps_selection_path": "eps.yaml",
        }
    ]
    assert capsys.readouterr().out == "BOTH\n"


def test_eps_selection_configuration_error_is_concise(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = EPSSelectionConfigurationError("bad eps config")

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "NO")

    assert main_module.main(["MU", "--eps-selection", "bad.yaml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: bad eps config\n"


def test_inspect_eps_rejects_eps_selection_combination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["MU", "--inspect-eps", "--eps-selection", "eps.yaml"])

    assert exc_info.value.code == 2


def test_single_industry_policy_option_uses_existing_single_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "POLICY")

    assert main_module.main(["MU", "--industry-policies", "industry.yaml"]) == 0
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "industry_policies_path": "industry.yaml",
        }
    ]
    assert capsys.readouterr().out == "POLICY\n"


def test_eps_selection_and_industry_policy_together_use_single_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "BOTH")

    assert (
        main_module.main(
            [
                "MU",
                "--eps-selection",
                "eps.yaml",
                "--industry-policies",
                "industry.yaml",
            ]
        )
        == 0
    )
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "eps_selection_path": "eps.yaml",
            "industry_policies_path": "industry.yaml",
        }
    ]
    assert capsys.readouterr().out == "BOTH\n"


def test_profiles_eps_selection_and_industry_policy_use_profile_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_with_profile_from_config_files",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "ALL")

    assert (
        main_module.main(
            [
                "MU",
                "--profiles",
                "profiles.yaml",
                "--eps-selection",
                "eps.yaml",
                "--industry-policies",
                "industry.yaml",
            ]
        )
        == 0
    )
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "profiles_path": "profiles.yaml",
            "eps_selection_path": "eps.yaml",
            "industry_policies_path": "industry.yaml",
        }
    ]
    assert capsys.readouterr().out == "ALL\n"


def test_batch_industry_policy_option_uses_batch_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(("MU",), (object(),), ())
    calls = []

    monkeypatch.setattr(
        main_module,
        "analyze_stocks_from_config_files",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_batch_stock_analysis_report", lambda value: "BATCH")

    assert (
        main_module.main(
            ["--stocks", "stocks.yaml", "--industry-policies", "industry.yaml"]
        )
        == 0
    )
    assert calls == [
        {
            "stocks_path": "stocks.yaml",
            "valuation_config_path": "config/valuation.yaml",
            "industry_policies_path": "industry.yaml",
        }
    ]
    assert capsys.readouterr().out == "BATCH\n"


def test_industry_policy_configuration_error_is_concise(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = IndustryPolicyConfigurationError("bad industry config")

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "NO")

    assert main_module.main(["MU", "--industry-policies", "bad.yaml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: bad industry config\n"


def test_inspect_eps_rejects_industry_policy_combination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["MU", "--inspect-eps", "--industry-policies", "industry.yaml"])

    assert exc_info.value.code == 2


def test_single_analyst_consensus_option_uses_existing_single_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()

    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(main_module, "format_stock_analysis_report", lambda value: "ANALYST")

    assert main_module.main(["MU", "--analyst-consensus", "analyst.yaml"]) == 0
    assert calls == [
        {
            "symbol": "MU",
            "config_path": "config/valuation.yaml",
            "analyst_consensus_path": "analyst.yaml",
        }
    ]
    assert capsys.readouterr().out == "ANALYST\n"


def test_inspect_eps_rejects_analyst_consensus_combination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["MU", "--inspect-eps", "--analyst-consensus", "analyst.yaml"])

    assert exc_info.value.code == 2


def test_single_show_snapshots_passes_explicit_formatter_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    result = object()
    monkeypatch.setattr(
        main_module,
        "analyze_stock_from_config_file",
        lambda **kwargs: calls.append(("analyze", kwargs)) or result,
    )
    monkeypatch.setattr(
        main_module,
        "format_stock_analysis_report",
        lambda value, show_snapshots=False: calls.append(
            ("format", value, show_snapshots)
        )
        or "SNAPSHOTS",
    )

    assert main_module.main(["MU", "--show-snapshots"]) == 0

    assert calls == [
        (
            "analyze",
            {"symbol": "MU", "config_path": "config/valuation.yaml"},
        ),
        ("format", result, True),
    ]
    assert capsys.readouterr().out == "SNAPSHOTS\n"


def test_batch_show_snapshots_passes_explicit_formatter_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = BatchStockAnalysisResult(("MU",), (object(),), ())
    calls = []
    monkeypatch.setattr(
        main_module,
        "analyze_stocks_from_config_files",
        lambda **kwargs: calls.append(("analyze", kwargs)) or result,
    )
    monkeypatch.setattr(
        main_module,
        "format_batch_stock_analysis_report",
        lambda value, show_snapshots=False: calls.append(
            ("format", value, show_snapshots)
        )
        or "BATCH SNAPSHOTS",
    )

    assert main_module.main(["--stocks", "stocks.yaml", "--show-snapshots"]) == 0

    assert calls == [
        (
            "analyze",
            {
                "stocks_path": "stocks.yaml",
                "valuation_config_path": "config/valuation.yaml",
            },
        ),
        ("format", result, True),
    ]
    assert capsys.readouterr().out == "BATCH SNAPSHOTS\n"


def test_inspect_eps_rejects_show_snapshots_combination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["MU", "--inspect-eps", "--show-snapshots"])

    assert exc_info.value.code == 2
