from math import inf, nan

import pytest

from src.yahoo import company
from src.yahoo.company import (
    CompanyFundamentals,
    download_company_fundamentals,
    extract_company_fundamentals,
    normalize_optional_float,
    normalize_optional_string,
    normalize_symbol,
)


class FastInfoObject:
    last_price = 701.0
    previous_close = 691.0
    market_cap = 51_000_000_000
    year_high = 751.0
    year_low = 301.0


class FakeTicker:
    symbols = []

    def __init__(self, symbol, info=None, fast_info=None, error=None):
        self.symbol = symbol
        self._info = info
        self._fast_info = fast_info
        self._error = error
        self.symbols.append(symbol)

    @property
    def info(self):
        if self._error:
            raise self._error
        return self._info

    @property
    def fast_info(self):
        if self._error:
            raise self._error
        return self._fast_info


def full_info() -> dict:
    return {
        "longName": "Lumentum Holdings Inc.",
        "currency": "USD",
        "currentPrice": 700.0,
        "previousClose": 690.0,
        "marketCap": 50_000_000_000,
        "sector": "Technology",
        "industry": "Communication Equipment",
        "trailingEps": 8.0,
        "forwardEps": 10.0,
        "trailingPE": 87.5,
        "forwardPE": 70.0,
        "pegRatio": 1.8,
        "fiftyTwoWeekHigh": 750.0,
        "fiftyTwoWeekLow": 300.0,
        "targetMeanPrice": 760.0,
        "targetHighPrice": 900.0,
        "targetLowPrice": 620.0,
    }


@pytest.mark.parametrize(
    ("raw_symbol", "expected_symbol"),
    [("lite", "LITE"), ("  mu ", "MU"), ("^sox", "^SOX"), ("brk-b", "BRK-B")],
)
def test_symbol_normalization(raw_symbol: str, expected_symbol: str) -> None:
    assert normalize_symbol(raw_symbol) == expected_symbol


@pytest.mark.parametrize("bad_symbol", ["", "   ", "BRK B"])
def test_invalid_string_symbol_raises(bad_symbol: str) -> None:
    with pytest.raises(ValueError):
        normalize_symbol(bad_symbol)


def test_invalid_non_string_symbol_raises() -> None:
    with pytest.raises(ValueError):
        normalize_symbol(123)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(4, 4.0), (4.6, 4.6), ("4.6", 4.6)],
)
def test_valid_float_normalization(value: object, expected: float) -> None:
    assert normalize_optional_float(value, "field") == expected


@pytest.mark.parametrize("value", [None, "", "   ", nan])
def test_missing_float_values_return_none(value: object) -> None:
    assert normalize_optional_float(value, "field") is None


@pytest.mark.parametrize("value", [inf, -inf, True, "not available", {}, []])
def test_invalid_float_values_raise(value: object) -> None:
    with pytest.raises(ValueError, match="bad_field"):
        normalize_optional_float(value, "bad_field")


def test_optional_string_stripping() -> None:
    assert normalize_optional_string("  Technology  ") == "Technology"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_optional_empty_string_handling(value: object) -> None:
    assert normalize_optional_string(value) is None


@pytest.mark.parametrize("value", [{}, []])
def test_invalid_string_value_rejection(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_optional_string(value)


def test_complete_info_dictionary_extraction() -> None:
    result = extract_company_fundamentals("lite", full_info())

    assert isinstance(result, CompanyFundamentals)
    assert result.symbol == "LITE"
    assert result.company_name == "Lumentum Holdings Inc."
    assert result.currency == "USD"
    assert result.current_price == 700.0
    assert result.previous_close == 690.0
    assert result.market_cap == 50_000_000_000.0
    assert result.sector == "Technology"
    assert result.industry == "Communication Equipment"
    assert result.trailing_eps == 8.0
    assert result.forward_eps == 10.0
    assert result.trailing_pe == 87.5
    assert result.forward_pe == 70.0
    assert result.peg_ratio == 1.8
    assert result.fifty_two_week_high == 750.0
    assert result.fifty_two_week_low == 300.0
    assert result.analyst_target_mean_price == 760.0
    assert result.analyst_target_high_price == 900.0
    assert result.analyst_target_low_price == 620.0


def test_missing_optional_fields_produce_none() -> None:
    result = extract_company_fundamentals("MU", {})

    assert result.company_name is None
    assert result.forward_eps is None
    assert result.trailing_eps is None
    assert result.trailing_pe is None
    assert result.forward_pe is None
    assert result.peg_ratio is None
    assert result.sector is None
    assert result.industry is None
    assert result.analyst_target_mean_price is None


def test_long_name_falls_back_to_short_name() -> None:
    result = extract_company_fundamentals("LITE", {"shortName": "Lumentum"})
    assert result.company_name == "Lumentum"


def test_current_price_precedence() -> None:
    result = extract_company_fundamentals(
        "LITE",
        {"currentPrice": 700.0, "regularMarketPrice": 699.0},
        {"last_price": 698.0},
    )
    assert result.current_price == 700.0


def test_regular_market_price_fallback() -> None:
    result = extract_company_fundamentals("LITE", {"regularMarketPrice": 699.0})
    assert result.current_price == 699.0


def test_fast_info_last_price_fallback() -> None:
    result = extract_company_fundamentals("LITE", {}, {"last_price": 698.0})
    assert result.current_price == 698.0


def test_previous_close_precedence() -> None:
    result = extract_company_fundamentals(
        "LITE",
        {"previousClose": 690.0, "regularMarketPreviousClose": 689.0},
        {"previous_close": 688.0},
    )
    assert result.previous_close == 690.0


def test_fast_info_previous_close_fallback() -> None:
    result = extract_company_fundamentals("LITE", {}, {"previous_close": 688.0})
    assert result.previous_close == 688.0


def test_market_cap_fallback() -> None:
    result = extract_company_fundamentals("LITE", {}, {"market_cap": 123.0})
    assert result.market_cap == 123.0


def test_peg_ratio_fallback() -> None:
    result = extract_company_fundamentals("LITE", {"trailingPegRatio": 1.7})
    assert result.peg_ratio == 1.7


def test_52_week_high_and_low_fallbacks() -> None:
    result = extract_company_fundamentals(
        "LITE",
        {},
        {"year_high": 750.0, "year_low": 300.0},
    )
    assert result.fifty_two_week_high == 750.0
    assert result.fifty_two_week_low == 300.0


def test_analyst_target_extraction() -> None:
    result = extract_company_fundamentals(
        "LITE",
        {
            "targetMeanPrice": 760.0,
            "targetHighPrice": 900.0,
            "targetLowPrice": 620.0,
        },
    )
    assert result.analyst_target_mean_price == 760.0
    assert result.analyst_target_high_price == 900.0
    assert result.analyst_target_low_price == 620.0


def test_negative_eps_and_pe_are_accepted() -> None:
    result = extract_company_fundamentals(
        "LITE",
        {
            "trailingEps": -1.0,
            "forwardEps": -2.0,
            "trailingPE": -3.0,
            "forwardPE": -4.0,
            "pegRatio": -5.0,
        },
    )
    assert result.trailing_eps == -1.0
    assert result.forward_eps == -2.0
    assert result.trailing_pe == -3.0
    assert result.forward_pe == -4.0
    assert result.peg_ratio == -5.0


def test_zero_price_is_accepted() -> None:
    result = extract_company_fundamentals("LITE", {"currentPrice": 0.0})
    assert result.current_price == 0.0


@pytest.mark.parametrize(
    "field",
    [
        "currentPrice",
        "previousClose",
        "marketCap",
        "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow",
        "targetMeanPrice",
        "targetHighPrice",
        "targetLowPrice",
    ],
)
def test_negative_non_negative_domain_fields_raise(field: str) -> None:
    with pytest.raises(ValueError):
        extract_company_fundamentals("LITE", {field: -0.01})


def test_invalid_finite_data_raises() -> None:
    with pytest.raises(ValueError, match="current_price"):
        extract_company_fundamentals("LITE", {"currentPrice": "not available"})
    with pytest.raises(ValueError, match="market_cap"):
        extract_company_fundamentals("LITE", {"marketCap": -inf})
    with pytest.raises(ValueError, match="trailing_eps"):
        extract_company_fundamentals("LITE", {"trailingEps": True})


def test_fast_info_as_dictionary() -> None:
    result = extract_company_fundamentals("LITE", {}, {"last_price": 700.0})
    assert result.current_price == 700.0


def test_fast_info_as_attribute_based_object() -> None:
    result = extract_company_fundamentals("LITE", {}, FastInfoObject())
    assert result.current_price == 701.0
    assert result.previous_close == 691.0
    assert result.market_cap == 51_000_000_000.0
    assert result.fifty_two_week_high == 751.0
    assert result.fifty_two_week_low == 301.0


def test_fast_info_as_none() -> None:
    result = extract_company_fundamentals("LITE", {}, None)
    assert result.current_price is None


def test_yahoo_ticker_called_with_normalized_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeTicker.symbols = []
    monkeypatch.setattr(
        company.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, info=full_info(), fast_info={}),
    )

    result = download_company_fundamentals(" lite ")

    assert result.symbol == "LITE"
    assert FakeTicker.symbols == ["LITE"]


def test_ticker_info_and_fast_info_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        company.yf,
        "Ticker",
        lambda symbol: FakeTicker(
            symbol,
            info={"longName": "Lumentum", "regularMarketPrice": None},
            fast_info={"last_price": 702.0},
        ),
    )

    result = download_company_fundamentals("LITE")

    assert result.company_name == "Lumentum"
    assert result.current_price == 702.0


def test_ticker_info_none_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, info=None, fast_info={}),
    )

    result = download_company_fundamentals("LITE")

    assert result.symbol == "LITE"
    assert result.company_name is None


def test_non_dictionary_info_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, info=[], fast_info={}),
    )

    with pytest.raises(RuntimeError, match="LITE"):
        download_company_fundamentals("LITE")


def test_yahoo_exception_wrapped_with_normalized_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        company.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, error=OSError("network down")),
    )

    with pytest.raises(RuntimeError, match="LITE"):
        download_company_fundamentals(" lite ")
