import pytest

import src.main as main_module
from src.config.valuation import ValuationConfigurationError
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
