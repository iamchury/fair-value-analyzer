import argparse
import sys
from collections.abc import Sequence
from typing import Callable

analyze_stock_from_config_file: Callable[..., object] | None = None
format_stock_analysis_report: Callable[[object], str] | None = None
analyze_stocks_from_config_files: Callable[..., object] | None = None
analyze_symbol_list_from_config_files: Callable[..., object] | None = None
format_batch_stock_analysis_report: Callable[[object], str] | None = None
analyze_stock_with_profile_from_config_files: Callable[..., object] | None = None
analyze_stocks_with_profiles_from_config_files: Callable[..., object] | None = None
analyze_symbol_list_with_profiles_from_config_files: Callable[..., object] | None = None
inspect_stock_eps: Callable[..., object] | None = None
format_eps_inspection_report: Callable[[object], str] | None = None
analyze_soxx_timing_from_config_file: Callable[..., object] | None = None
format_soxx_timing_report: Callable[..., str] | None = None
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
        "symbols",
        nargs="*",
        help="Yahoo Finance stock symbol or symbols to analyze.",
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
        "--agreement-config",
        help="Path to optional valuation snapshot agreement engine YAML.",
    )
    parser.add_argument(
        "--momentum-config",
        help="Path to optional RSI momentum reference YAML.",
    )
    parser.add_argument(
        "--range-config",
        help="Path to optional fair value range YAML.",
    )
    parser.add_argument(
        "--recommendation-v2-config",
        help="Path to optional Recommendation V2 YAML.",
    )
    parser.add_argument(
        "--show-snapshots",
        action="store_true",
        help="Append diagnostic unified valuation snapshot output.",
    )
    parser.add_argument(
        "--show-agreement",
        action="store_true",
        help="Append valuation snapshot agreement analysis output.",
    )
    parser.add_argument(
        "--show-momentum",
        action="store_true",
        help="Append RSI momentum reference output.",
    )
    parser.add_argument(
        "--show-range",
        action="store_true",
        help="Append fair value range output.",
    )
    parser.add_argument(
        "--show-recommendation-v2",
        action="store_true",
        help="Append Recommendation V2 output.",
    )
    parser.add_argument(
        "--ranking-config",
        help="Path to optional multi-stock ranking engine YAML.",
    )
    parser.add_argument(
        "--show-ranking",
        action="store_true",
        help="Append multi-stock ranking output.",
    )
    parser.add_argument(
        "--show-ranking-details",
        action="store_true",
        help="Append detailed multi-stock ranking score breakdowns.",
    )
    parser.add_argument(
        "--ranking-only",
        action="store_true",
        help="Print only multi-stock ranking output.",
    )
    parser.add_argument(
        "--ranking-format",
        choices=("text", "csv", "json"),
        default="text",
        help="Ranking output format. Default: text",
    )
    parser.add_argument(
        "--soxx-timing",
        action="store_true",
        help="Append the SOXX buy/sell timing section before valuation output.",
    )
    parser.add_argument(
        "--soxx-timing-config",
        default="config/soxx_timing.yaml",
        help="Path to SOXX timing configuration YAML. Default: config/soxx_timing.yaml",
    )
    parser.add_argument(
        "--soxx-timing-only",
        action="store_true",
        help="Print only SOXX buy/sell timing output.",
    )
    parser.add_argument(
        "--show-soxx-chart-data",
        action="store_true",
        help="Append recent SOXX timing chart data to the CLI report.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one stock or batch valuation analysis from the command line."""
    parser = build_parser()
    args = parser.parse_args(argv)
    has_symbols = bool(args.symbols)
    if args.soxx_timing_only:
        args.soxx_timing = True
    if not args.soxx_timing_only and has_symbols == bool(args.stocks):
        parser.error("provide exactly one of symbol or --stocks.")
    if args.soxx_timing_only and (has_symbols or args.stocks):
        parser.error("--soxx-timing-only does not accept ordinary stock symbols or --stocks.")
    if args.inspect_eps and args.stocks:
        parser.error("--inspect-eps does not support --stocks.")
    if args.inspect_eps and len(args.symbols) != 1:
        parser.error("--inspect-eps requires exactly one symbol.")
    if args.inspect_eps and args.eps_selection:
        parser.error("--inspect-eps cannot be combined with --eps-selection.")
    if args.inspect_eps and args.industry_policies:
        parser.error("--inspect-eps cannot be combined with --industry-policies.")
    if args.inspect_eps and args.analyst_consensus:
        parser.error("--inspect-eps cannot be combined with --analyst-consensus.")
    if args.inspect_eps and args.agreement_config:
        parser.error("--inspect-eps cannot be combined with --agreement-config.")
    if args.inspect_eps and args.momentum_config:
        parser.error("--inspect-eps cannot be combined with --momentum-config.")
    if args.inspect_eps and args.range_config:
        parser.error("--inspect-eps cannot be combined with --range-config.")
    if args.inspect_eps and args.recommendation_v2_config:
        parser.error("--inspect-eps cannot be combined with --recommendation-v2-config.")
    if args.inspect_eps and args.ranking_config:
        parser.error("--inspect-eps cannot be combined with --ranking-config.")
    if args.inspect_eps and args.show_snapshots:
        parser.error("--inspect-eps cannot be combined with --show-snapshots.")
    if args.inspect_eps and args.show_agreement:
        parser.error("--inspect-eps cannot be combined with --show-agreement.")
    if args.inspect_eps and args.show_momentum:
        parser.error("--inspect-eps cannot be combined with --show-momentum.")
    if args.inspect_eps and args.show_range:
        parser.error("--inspect-eps cannot be combined with --show-range.")
    if args.inspect_eps and args.show_recommendation_v2:
        parser.error("--inspect-eps cannot be combined with --show-recommendation-v2.")
    if args.inspect_eps and args.show_ranking:
        parser.error("--inspect-eps cannot be combined with --show-ranking.")
    if args.inspect_eps and args.show_ranking_details:
        parser.error("--inspect-eps cannot be combined with --show-ranking-details.")
    if args.inspect_eps and args.ranking_only:
        parser.error("--inspect-eps cannot be combined with --ranking-only.")
    if args.show_agreement and not args.agreement_config:
        parser.error("--show-agreement requires --agreement-config.")
    if args.show_momentum and not args.momentum_config:
        parser.error("--show-momentum requires --momentum-config.")
    if args.show_range and not args.range_config:
        parser.error("--show-range requires --range-config.")
    if args.show_recommendation_v2 and not args.recommendation_v2_config:
        parser.error("--show-recommendation-v2 requires --recommendation-v2-config.")
    if (args.show_ranking or args.show_ranking_details or args.ranking_only) and not args.ranking_config:
        parser.error("ranking output requires --ranking-config.")
    if (args.show_ranking or args.show_ranking_details or args.ranking_only) and not args.recommendation_v2_config:
        parser.error("ranking output requires --recommendation-v2-config.")
    if (args.show_ranking or args.show_ranking_details or args.ranking_only) and has_symbols and len(args.symbols) < 2:
        parser.error("ranking output requires at least two symbols or --stocks.")
    if args.ranking_format != "text" and not (args.show_ranking or args.ranking_only):
        parser.error("--ranking-format csv/json requires --show-ranking or --ranking-only.")

    try:
        dependencies = _load_runtime_dependencies()
    except ModuleNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.inspect_eps:
            result = dependencies.eps_inspector(symbol=args.symbols[0])
            report = dependencies.eps_formatter(result)
            print(report)
            return 0

        analysis_options = _analysis_options(args)
        formatter_options = _formatter_options(args)
        soxx_report = None
        if args.soxx_timing:
            soxx_result = dependencies.soxx_analyzer(args.soxx_timing_config)
            soxx_report = dependencies.soxx_formatter(
                soxx_result,
                show_chart_data=args.show_soxx_chart_data,
            )
            if args.soxx_timing_only:
                print(soxx_report)
                return 0

        if args.stocks:
            if args.profiles:
                result = dependencies.batch_profile_analyzer(
                    stocks_path=args.stocks,
                    valuation_config_path=args.config,
                    profiles_path=args.profiles,
                    **analysis_options,
                )
            else:
                result = dependencies.batch_analyzer(
                    stocks_path=args.stocks,
                    valuation_config_path=args.config,
                    **analysis_options,
                )
            report = (
                dependencies.batch_formatter(result, **formatter_options)
                if formatter_options
                else dependencies.batch_formatter(result)
            )
            print(_prepend_soxx_report(soxx_report, report))
            if result.failure_count == 0:
                return 0
            if result.success_count == 0:
                return 1
            return 3

        if len(args.symbols) > 1:
            if args.profiles:
                result = dependencies.batch_symbol_profile_analyzer(
                    symbols=args.symbols,
                    valuation_config_path=args.config,
                    profiles_path=args.profiles,
                    **analysis_options,
                )
            else:
                result = dependencies.batch_symbol_analyzer(
                    symbols=args.symbols,
                    valuation_config_path=args.config,
                    **analysis_options,
                )
            report = (
                dependencies.batch_formatter(result, **formatter_options)
                if formatter_options
                else dependencies.batch_formatter(result)
            )
            print(_prepend_soxx_report(soxx_report, report))
            if result.failure_count == 0:
                return 0
            if result.success_count == 0:
                return 1
            return 3

        if args.profiles:
            result = dependencies.single_profile_analyzer(
                symbol=args.symbols[0],
                config_path=args.config,
                profiles_path=args.profiles,
                **analysis_options,
            )
        else:
            result = dependencies.single_analyzer(
                symbol=args.symbols[0],
                config_path=args.config,
                **analysis_options,
            )
        report = (
            dependencies.single_formatter(result, **formatter_options)
            if formatter_options
            else dependencies.single_formatter(result)
        )
    except dependencies.expected_errors as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_prepend_soxx_report(soxx_report, report))
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
        batch_symbol_analyzer: Callable[..., object],
        batch_symbol_profile_analyzer: Callable[..., object],
        eps_inspector: Callable[..., object],
        eps_formatter: Callable[[object], str],
        soxx_analyzer: Callable[..., object],
        soxx_formatter: Callable[..., str],
        expected_errors: tuple[type[BaseException], ...],
    ) -> None:
        self.single_analyzer = single_analyzer
        self.single_formatter = single_formatter
        self.batch_analyzer = batch_analyzer
        self.batch_formatter = batch_formatter
        self.single_profile_analyzer = single_profile_analyzer
        self.batch_profile_analyzer = batch_profile_analyzer
        self.batch_symbol_analyzer = batch_symbol_analyzer
        self.batch_symbol_profile_analyzer = batch_symbol_profile_analyzer
        self.eps_inspector = eps_inspector
        self.eps_formatter = eps_formatter
        self.soxx_analyzer = soxx_analyzer
        self.soxx_formatter = soxx_formatter
        self.expected_errors = expected_errors


def _load_runtime_dependencies() -> _RuntimeDependencies:
    global analyze_stock_from_config_file
    global format_stock_analysis_report
    global analyze_stocks_from_config_files
    global analyze_symbol_list_from_config_files
    global format_batch_stock_analysis_report
    global analyze_stock_with_profile_from_config_files
    global analyze_stocks_with_profiles_from_config_files
    global analyze_symbol_list_with_profiles_from_config_files
    global inspect_stock_eps
    global format_eps_inspection_report
    global analyze_soxx_timing_from_config_file
    global format_soxx_timing_report
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
    if analyze_symbol_list_from_config_files is None:
        from src.services.batch_analysis import (
            analyze_symbol_list_from_config_files as service_analyze_symbol_list,
        )

        analyze_symbol_list_from_config_files = service_analyze_symbol_list
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
    if analyze_symbol_list_with_profiles_from_config_files is None:
        from src.services.batch_analysis import (
            analyze_symbol_list_with_profiles_from_config_files as service_batch_symbol_profiles,
        )

        analyze_symbol_list_with_profiles_from_config_files = service_batch_symbol_profiles
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
    if analyze_soxx_timing_from_config_file is None:
        from src.services.soxx_timing import (
            analyze_soxx_timing_from_config_file as service_analyze_soxx_timing,
        )

        analyze_soxx_timing_from_config_file = service_analyze_soxx_timing
    if format_soxx_timing_report is None:
        from src.reports.soxx_timing_report import (
            format_soxx_timing_report as soxx_report_formatter,
        )

        format_soxx_timing_report = soxx_report_formatter
    if _EXPECTED_ERRORS is None:
        from src.config.stocks import StocksConfigurationError
        from src.config.analyst_consensus import AnalystConsensusConfigurationError
        from src.config.agreement_engine import AgreementEngineConfigurationError
        from src.config.momentum_reference import MomentumReferenceConfigurationError
        from src.config.fair_value_range import FairValueRangeConfigurationError
        from src.config.recommendation_v2 import RecommendationV2ConfigurationError
        from src.config.ranking_engine import RankingEngineConfigurationError
        from src.config.eps_selection import EPSSelectionConfigurationError
        from src.config.industry_policies import IndustryPolicyConfigurationError
        from src.config.valuation import ValuationConfigurationError
        from src.config.valuation_profiles import ValuationProfileConfigurationError
        from src.services.eps_inspection import EPSInspectionServiceError
        from src.config.soxx_timing import SoxxTimingConfigurationError
        from src.services.stock_analysis import StockAnalysisServiceError

        _EXPECTED_ERRORS = (
            EPSInspectionServiceError,
            SoxxTimingConfigurationError,
            AnalystConsensusConfigurationError,
            AgreementEngineConfigurationError,
            MomentumReferenceConfigurationError,
            FairValueRangeConfigurationError,
            RecommendationV2ConfigurationError,
            RankingEngineConfigurationError,
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
        analyze_symbol_list_from_config_files,
        analyze_symbol_list_with_profiles_from_config_files,
        inspect_stock_eps,
        format_eps_inspection_report,
        analyze_soxx_timing_from_config_file,
        format_soxx_timing_report,
        _EXPECTED_ERRORS,
    )


def _analysis_options(args: argparse.Namespace) -> dict[str, str]:
    options: dict[str, str] = {}
    if args.eps_selection:
        options["eps_selection_path"] = args.eps_selection
    if args.industry_policies:
        options["industry_policies_path"] = args.industry_policies
    if args.analyst_consensus:
        options["analyst_consensus_path"] = args.analyst_consensus
    if args.agreement_config:
        options["agreement_config_path"] = args.agreement_config
    if args.momentum_config:
        options["momentum_config_path"] = args.momentum_config
    if args.range_config:
        options["range_config_path"] = args.range_config
    if args.recommendation_v2_config:
        options["recommendation_v2_config_path"] = args.recommendation_v2_config
    if args.ranking_config:
        options["ranking_config_path"] = args.ranking_config
    return options


def _prepend_soxx_report(soxx_report: str | None, report: str) -> str:
    if not soxx_report:
        return report
    return f"{soxx_report}\n\n{report}"


def _formatter_options(args: argparse.Namespace) -> dict[str, object]:
    options: dict[str, object] = {}
    if args.show_snapshots:
        options["show_snapshots"] = True
    if args.show_agreement:
        options["show_agreement"] = True
    if args.show_momentum:
        options["show_momentum"] = True
    if args.show_range:
        options["show_range"] = True
    if args.show_recommendation_v2:
        options["show_recommendation_v2"] = True
    if args.show_ranking or args.show_ranking_details:
        options["show_ranking"] = True
    if args.show_ranking_details:
        options["show_ranking_details"] = True
    if args.ranking_only:
        options["ranking_only"] = True
    if args.ranking_format != "text":
        options["ranking_format"] = args.ranking_format
    return options


if __name__ == "__main__":
    raise SystemExit(main())
