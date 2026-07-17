import argparse
import sys
from dataclasses import dataclass

import yfinance as yf


@dataclass
class PriceData:
    """종목의 최근 거래 데이터."""

    symbol: str
    date: str
    close: float
    volume: int
    currency: str


def get_latest_price(symbol: str) -> PriceData:
    """
    Yahoo Finance에서 종목의 최근 거래일 데이터를 조회한다.

    Args:
        symbol: Yahoo Finance 티커. 예: MU, NVDA, AMAT

    Returns:
        최근 거래일의 날짜, 종가, 거래량, 통화

    Raises:
        RuntimeError: 데이터를 가져오지 못한 경우
    """
    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        raise ValueError("종목 티커를 입력해야 합니다.")

    ticker = yf.Ticker(normalized_symbol)

    history = ticker.history(
        period="5d",
        auto_adjust=False,
        repair=True,
    )

    if history.empty:
        raise RuntimeError(
            f"{normalized_symbol}: 주가 데이터를 가져오지 못했습니다."
        )

    latest_row = history.iloc[-1]
    latest_date = history.index[-1].strftime("%Y-%m-%d")

    try:
        currency = ticker.fast_info.get("currency", "USD")
    except Exception:
        currency = "USD"

    return PriceData(
        symbol=normalized_symbol,
        date=latest_date,
        close=float(latest_row["Close"]),
        volume=int(latest_row["Volume"]),
        currency=str(currency),
    )


def parse_arguments() -> argparse.Namespace:
    """명령행 인수를 읽는다."""
    parser = argparse.ArgumentParser(
        description="Yahoo Finance에서 최근 종가를 조회합니다."
    )

    parser.add_argument(
        "symbol",
        nargs="?",
        default="MU",
        help="조회할 종목 티커. 기본값: MU",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        price_data = get_latest_price(args.symbol)
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print("=" * 40)
    print("Yahoo Finance 최근 거래 데이터")
    print("=" * 40)
    print(f"종목       : {price_data.symbol}")
    print(f"기준 날짜  : {price_data.date}")
    print(f"최근 종가  : {price_data.close:,.2f} {price_data.currency}")
    print(f"거래량     : {price_data.volume:,}")
    print("=" * 40)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())