import argparse
import sys
from collections.abc import Sequence
from typing import Callable

analyze_stock_from_config_file: Callable[..., object] | None = None
format_stock_analysis_report: Callable[[object], str] | None = None
_EXPECTED_ERRORS: tuple[type[BaseException], ...] | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for single-stock analysis."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a stock using EPS growth, Target PE, Treasury adjustment, "
            "and fair-value thresholds."
        )
    )
    parser.add_argument("symbol", help="Yahoo Finance stock symbol to analyze.")
    parser.add_argument(
        "--config",
        default="config/valuation.yaml",
        help="Path to valuation configuration YAML. Default: config/valuation.yaml",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one stock valuation analysis from the command line."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        analyzer, formatter, expected_errors = _load_runtime_dependencies()
    except ModuleNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        result = analyzer(
            symbol=args.symbol,
            config_path=args.config,
        )
        report = formatter(result)
    except expected_errors as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(report)
    return 0


def _load_runtime_dependencies() -> tuple[
    Callable[..., object],
    Callable[[object], str],
    tuple[type[BaseException], ...],
]:
    global analyze_stock_from_config_file
    global format_stock_analysis_report
    global _EXPECTED_ERRORS

    if analyze_stock_from_config_file is None:
        from src.services.stock_analysis import (
            analyze_stock_from_config_file as service_analyze_stock,
        )

        analyze_stock_from_config_file = service_analyze_stock
    if format_stock_analysis_report is None:
        from src.reports.text_report import (
            format_stock_analysis_report as report_formatter,
        )

        format_stock_analysis_report = report_formatter
    if _EXPECTED_ERRORS is None:
        from src.config.valuation import ValuationConfigurationError
        from src.services.stock_analysis import StockAnalysisServiceError

        _EXPECTED_ERRORS = (
            StockAnalysisServiceError,
            ValuationConfigurationError,
            ValueError,
            RuntimeError,
        )

    return (
        analyze_stock_from_config_file,
        format_stock_analysis_report,
        _EXPECTED_ERRORS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
