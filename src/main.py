import argparse
import sys
from collections.abc import Sequence
from typing import Callable

analyze_stock_from_config_file: Callable[..., object] | None = None
format_stock_analysis_report: Callable[[object], str] | None = None
analyze_stocks_from_config_files: Callable[..., object] | None = None
format_batch_stock_analysis_report: Callable[[object], str] | None = None
analyze_stock_with_profile_from_config_files: Callable[..., object] | None = None
analyze_stocks_with_profiles_from_config_files: Callable[..., object] | None = None
inspect_stock_eps: Callable[..., object] | None = None
format_eps_inspection_report: Callable[[object], str] | None = None
_EXPECTED_ERRORS: tuple[type[BaseException], ...] | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for single-stock or batch analysis."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a stock using EPS growth, Target PE, Treasury adjustment, "
            "and fair-value thresholds."
        )
    )
    parser.add_argument(
        "symbol",
        nargs="?",
        help="Yahoo Finance stock symbol to analyze.",
    )
    parser.add_argument(
        "--stocks",
        help="Path to stocks configuration YAML for batch analysis.",
    )
    parser.add_argument(
        "--config",
        default="config/valuation.yaml",
        help="Path to valuation configuration YAML. Default: config/valuation.yaml",
    )
    parser.add_argument(
        "--profiles",
        help="Path to optional valuation profiles YAML.",
    )
    parser.add_argument(
        "--inspect-eps",
        action="store_true",
        help="Print a diagnostic Yahoo EPS source inspection report.",
    )
    parser.add_argument(
        "--eps-selection",
        help="Path to optional EPS selection configuration YAML.",
    )
    parser.add_argument(
        "--industry-policies",
        help="Path to optional industry valuation policy YAML.",
    )
    parser.add_argument(
        "--analyst-consensus",
        help="Path to optional analyst consensus valuation YAML.",
    )
    parser.add_argument(
        "--show-snapshots",
        action="store_true",
        help="Append diagnostic unified valuation snapshot output.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one stock or batch valuation analysis from the command line."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.symbol) == bool(args.stocks):
        parser.error("provide exactly one of symbol or --stocks.")
    if args.inspect_eps and args.stocks:
        parser.error("--inspect-eps does not support --stocks.")
    if args.inspect_eps and args.eps_selection:
        parser.error("--inspect-eps cannot be combined with --eps-selection.")
    if args.inspect_eps and args.industry_policies:
        parser.error("--inspect-eps cannot be combined with --industry-policies.")
    if args.inspect_eps and args.analyst_consensus:
        parser.error("--inspect-eps cannot be combined with --analyst-consensus.")
    if args.inspect_eps and args.show_snapshots:
        parser.error("--inspect-eps cannot be combined with --show-snapshots.")

    try:
        dependencies = _load_runtime_dependencies()
    except ModuleNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.inspect_eps:
            result = dependencies.eps_inspector(symbol=args.symbol)
            report = dependencies.eps_formatter(result)
            print(report)
            return 0

        if args.stocks:
            if args.profiles:
                if args.eps_selection and args.industry_policies and args.analyst_consensus:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        eps_selection_path=args.eps_selection,
                        industry_policies_path=args.industry_policies,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.eps_selection and args.industry_policies:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        eps_selection_path=args.eps_selection,
                        industry_policies_path=args.industry_policies,
                    )
                elif args.eps_selection and args.analyst_consensus:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        eps_selection_path=args.eps_selection,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.industry_policies and args.analyst_consensus:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        industry_policies_path=args.industry_policies,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.eps_selection:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        eps_selection_path=args.eps_selection,
                    )
                elif args.industry_policies:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        industry_policies_path=args.industry_policies,
                    )
                elif args.analyst_consensus:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                else:
                    result = dependencies.batch_profile_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        profiles_path=args.profiles,
                    )
            else:
                if args.eps_selection and args.industry_policies and args.analyst_consensus:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        eps_selection_path=args.eps_selection,
                        industry_policies_path=args.industry_policies,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.eps_selection and args.industry_policies:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        eps_selection_path=args.eps_selection,
                        industry_policies_path=args.industry_policies,
                    )
                elif args.eps_selection and args.analyst_consensus:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        eps_selection_path=args.eps_selection,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.industry_policies and args.analyst_consensus:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        industry_policies_path=args.industry_policies,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                elif args.eps_selection:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        eps_selection_path=args.eps_selection,
                    )
                elif args.industry_policies:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        industry_policies_path=args.industry_policies,
                    )
                elif args.analyst_consensus:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                        analyst_consensus_path=args.analyst_consensus,
                    )
                else:
                    result = dependencies.batch_analyzer(
                        stocks_path=args.stocks,
                        valuation_config_path=args.config,
                    )
            report = (
                dependencies.batch_formatter(result, show_snapshots=True)
                if args.show_snapshots
                else dependencies.batch_formatter(result)
            )
            print(report)
            if result.failure_count == 0:
                return 0
            if result.success_count == 0:
                return 1
            return 3

        if args.profiles:
            if args.eps_selection and args.industry_policies and args.analyst_consensus:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    eps_selection_path=args.eps_selection,
                    industry_policies_path=args.industry_policies,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.eps_selection and args.industry_policies:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    eps_selection_path=args.eps_selection,
                    industry_policies_path=args.industry_policies,
                )
            elif args.eps_selection and args.analyst_consensus:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    eps_selection_path=args.eps_selection,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.industry_policies and args.analyst_consensus:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    industry_policies_path=args.industry_policies,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.eps_selection:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    eps_selection_path=args.eps_selection,
                )
            elif args.industry_policies:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    industry_policies_path=args.industry_policies,
                )
            elif args.analyst_consensus:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                    analyst_consensus_path=args.analyst_consensus,
                )
            else:
                result = dependencies.single_profile_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    profiles_path=args.profiles,
                )
        else:
            if args.eps_selection and args.industry_policies and args.analyst_consensus:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    eps_selection_path=args.eps_selection,
                    industry_policies_path=args.industry_policies,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.eps_selection and args.industry_policies:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    eps_selection_path=args.eps_selection,
                    industry_policies_path=args.industry_policies,
                )
            elif args.eps_selection and args.analyst_consensus:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    eps_selection_path=args.eps_selection,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.industry_policies and args.analyst_consensus:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    industry_policies_path=args.industry_policies,
                    analyst_consensus_path=args.analyst_consensus,
                )
            elif args.eps_selection:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    eps_selection_path=args.eps_selection,
                )
            elif args.industry_policies:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    industry_policies_path=args.industry_policies,
                )
            elif args.analyst_consensus:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                    analyst_consensus_path=args.analyst_consensus,
                )
            else:
                result = dependencies.single_analyzer(
                    symbol=args.symbol,
                    config_path=args.config,
                )
        report = (
            dependencies.single_formatter(result, show_snapshots=True)
            if args.show_snapshots
            else dependencies.single_formatter(result)
        )
    except dependencies.expected_errors as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(report)
    return 0


class _RuntimeDependencies:
    def __init__(
        self,
        single_analyzer: Callable[..., object],
        single_formatter: Callable[[object], str],
        batch_analyzer: Callable[..., object],
        batch_formatter: Callable[[object], str],
        single_profile_analyzer: Callable[..., object],
        batch_profile_analyzer: Callable[..., object],
        eps_inspector: Callable[..., object],
        eps_formatter: Callable[[object], str],
        expected_errors: tuple[type[BaseException], ...],
    ) -> None:
        self.single_analyzer = single_analyzer
        self.single_formatter = single_formatter
        self.batch_analyzer = batch_analyzer
        self.batch_formatter = batch_formatter
        self.single_profile_analyzer = single_profile_analyzer
        self.batch_profile_analyzer = batch_profile_analyzer
        self.eps_inspector = eps_inspector
        self.eps_formatter = eps_formatter
        self.expected_errors = expected_errors


def _load_runtime_dependencies() -> _RuntimeDependencies:
    global analyze_stock_from_config_file
    global format_stock_analysis_report
    global analyze_stocks_from_config_files
    global format_batch_stock_analysis_report
    global analyze_stock_with_profile_from_config_files
    global analyze_stocks_with_profiles_from_config_files
    global inspect_stock_eps
    global format_eps_inspection_report
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
    if analyze_stocks_from_config_files is None:
        from src.services.batch_analysis import (
            analyze_stocks_from_config_files as service_analyze_stocks,
        )

        analyze_stocks_from_config_files = service_analyze_stocks
    if analyze_stock_with_profile_from_config_files is None:
        from src.services.stock_analysis import (
            analyze_stock_with_profile_from_config_files as service_analyze_profile,
        )

        analyze_stock_with_profile_from_config_files = service_analyze_profile
    if analyze_stocks_with_profiles_from_config_files is None:
        from src.services.batch_analysis import (
            analyze_stocks_with_profiles_from_config_files as service_batch_profiles,
        )

        analyze_stocks_with_profiles_from_config_files = service_batch_profiles
    if format_batch_stock_analysis_report is None:
        from src.reports.batch_text_report import (
            format_batch_stock_analysis_report as batch_report_formatter,
        )

        format_batch_stock_analysis_report = batch_report_formatter
    if inspect_stock_eps is None:
        from src.services.eps_inspection import (
            inspect_stock_eps as service_inspect_eps,
        )

        inspect_stock_eps = service_inspect_eps
    if format_eps_inspection_report is None:
        from src.reports.eps_inspection_report import (
            format_eps_inspection_report as eps_report_formatter,
        )

        format_eps_inspection_report = eps_report_formatter
    if _EXPECTED_ERRORS is None:
        from src.config.stocks import StocksConfigurationError
        from src.config.analyst_consensus import AnalystConsensusConfigurationError
        from src.config.eps_selection import EPSSelectionConfigurationError
        from src.config.industry_policies import IndustryPolicyConfigurationError
        from src.config.valuation import ValuationConfigurationError
        from src.config.valuation_profiles import ValuationProfileConfigurationError
        from src.services.eps_inspection import EPSInspectionServiceError
        from src.services.stock_analysis import StockAnalysisServiceError

        _EXPECTED_ERRORS = (
            EPSInspectionServiceError,
            AnalystConsensusConfigurationError,
            EPSSelectionConfigurationError,
            IndustryPolicyConfigurationError,
            StockAnalysisServiceError,
            StocksConfigurationError,
            ValuationConfigurationError,
            ValuationProfileConfigurationError,
            ValueError,
            RuntimeError,
        )

    return _RuntimeDependencies(
        analyze_stock_from_config_file,
        format_stock_analysis_report,
        analyze_stocks_from_config_files,
        format_batch_stock_analysis_report,
        analyze_stock_with_profile_from_config_files,
        analyze_stocks_with_profiles_from_config_files,
        inspect_stock_eps,
        format_eps_inspection_report,
        _EXPECTED_ERRORS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
