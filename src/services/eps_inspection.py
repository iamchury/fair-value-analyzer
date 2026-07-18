from dataclasses import dataclass

from src.analysis.eps_source_inspector import (
    EPSInspectionResult,
    inspect_eps_source,
)
from src.yahoo.company import (
    CompanyFundamentals,
    YahooEPSRawSnapshot,
    download_company_fundamentals_with_eps_snapshot,
    normalize_symbol,
)


class EPSInspectionServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EPSInspectionServiceResult:
    company: CompanyFundamentals
    eps_snapshot: YahooEPSRawSnapshot
    inspection: EPSInspectionResult


def inspect_stock_eps(symbol: str) -> EPSInspectionServiceResult:
    """Download one company once and inspect its Yahoo EPS source fields."""
    normalized_symbol = normalize_symbol(symbol)
    try:
        downloaded = download_company_fundamentals_with_eps_snapshot(normalized_symbol)
    except RuntimeError as exc:
        raise EPSInspectionServiceError(str(exc)) from exc

    inspection = inspect_eps_source(downloaded.eps_snapshot)
    return EPSInspectionServiceResult(
        company=downloaded.fundamentals,
        eps_snapshot=downloaded.eps_snapshot,
        inspection=inspection,
    )
