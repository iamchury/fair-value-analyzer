import sys

import yfinance as yf


def get_latest_price(symbol: str) -> float:
    """
    Yahoo Finance에서 종목의 최근 거래 가격을 조회한다.

    Args:
        symbol: Yahoo Finance 티커. 예: MU, NVDA, AMAT

    Returns:
        최근 가격

    Raises:
        RuntimeError: 가격 데이터를 가져오지 못한 경우
    """
    ticker = yf.Ticker(symbol)

    history = ticker.history(period="5d")

    if history.empty:
        raise RuntimeError(f"{symbol}: 주가 데이터를 가져오지 못했습니다.")

    latest_price = float(history["Close"].iloc[-1])

    return latest_price


def main() -> int:
    symbol = "MU"

    try:
        latest_price = get_latest_price(symbol)
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print(f"종목: {symbol}")
    print(f"최근 종가: ${latest_price:,.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
