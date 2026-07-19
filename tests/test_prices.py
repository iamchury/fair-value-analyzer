from datetime import date

from src.yahoo.prices import extract_price_history


class FakeHistory:
    empty = False
    index = ["2026-01-03", "2026-01-01", "bad", "2026-01-01"]

    def __getitem__(self, key):
        if key == "Close":
            return [103.0, 101.0, 999.0, 102.0]
        if key == "Adj Close":
            return [93.0, 91.0, 999.0, 92.0]
        raise KeyError(key)


def test_extract_price_history_sorts_and_deduplicates_dates() -> None:
    result = extract_price_history(" mu ", FakeHistory())

    assert result.symbol == "MU"
    assert [row.date for row in result.rows] == [date(2026, 1, 1), date(2026, 1, 3)]
    assert result.rows[0].close == 102.0
    assert result.rows[0].adjusted_close == 92.0
