from datetime import date

import pytest

from budget_manager.engine import YearMonth, format_amount, format_input, parse_amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0,00"),
        (5, "0,05"),
        (123456, "1.234,56"),
        (100000000, "1.000.000,00"),
        (-123456, "−1.234,56"),
    ],
)
def test_format_amount(value, expected):
    assert format_amount(value) == expected


def test_format_amount_without_decimals_rounds():
    assert format_amount(123456, decimals=False) == "1.235"
    assert format_amount(-123449, decimals=False) == "−1.234"


def test_format_input_uses_plain_hyphen():
    assert format_input(-150) == "-1,50"
    assert format_input(None) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", 123456),
        ("1234,56", 123456),
        ("1234,5", 123450),
        ("1234", 123400),
        ("1.234", 123400),
        ("1.234.567", 123456700),
        ("12.5", 1250),
        ("1234.56", 123456),
        (" 1 234,56 ", 123456),
        ("-45,00", -4500),
        ("−45", -4500),
        ("+10", 1000),
        (",50", 50),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["", "   ", None])
def test_parse_amount_empty_is_none(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize("text", ["abc", "1,2,3", "12,345", "1.23.4", "-", "1.2345,00", "1e5"])
def test_parse_amount_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_parse_and_format_round_trip():
    for value in (0, 1, 99, 100, 123456, -987654321):
        assert parse_amount(format_amount(value)) == value


def test_year_month_arithmetic():
    may = YearMonth(2025, 5)
    assert may + 8 == YearMonth(2026, 1)
    assert may - 5 == YearMonth(2024, 12)
    assert may.months_until(YearMonth(2026, 3)) == 10
    assert YearMonth(2026, 3).months_until(may) == -10
    assert may < YearMonth(2025, 6) < YearMonth(2026, 1)


def test_year_month_days():
    assert YearMonth(2024, 2).last_day() == date(2024, 2, 29)
    assert YearMonth(2025, 2).day(31) == date(2025, 2, 28)
    assert YearMonth(2025, 4).first_day() == date(2025, 4, 1)


def test_year_month_parse_and_labels():
    month = YearMonth.parse("2025-05")
    assert month == YearMonth(2025, 5)
    assert str(month) == "2025-05"
    assert month.label == "May 2025"
    assert month.short_label == "May 2025"
    assert YearMonth.of(date(2025, 12, 24)) == YearMonth(2025, 12)
    with pytest.raises(ValueError):
        YearMonth.parse("May 2025")
    with pytest.raises(ValueError):
        YearMonth(2025, 13)
