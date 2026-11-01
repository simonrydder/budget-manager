from datetime import date

from budget_manager.engine.bankdays import (
    drawn_on,
    easter,
    is_bank_day,
    last_bank_day,
    next_bank_day,
)
from budget_manager.engine.months import YearMonth


def test_easter():
    assert easter(2024) == date(2024, 3, 31)
    assert easter(2025) == date(2025, 4, 20)
    assert easter(2026) == date(2026, 4, 5)
    assert easter(2027) == date(2027, 3, 28)


def test_weekends_and_closing_days_are_not_bank_days():
    assert is_bank_day(date(2026, 10, 30))  # a Friday
    assert not is_bank_day(date(2026, 10, 31))  # a Saturday
    assert not is_bank_day(date(2026, 12, 24))
    assert not is_bank_day(date(2026, 12, 31))
    assert not is_bank_day(date(2026, 6, 5))  # Constitution Day, a Friday
    assert not is_bank_day(date(2026, 5, 15))  # the Friday after Ascension Day
    assert not is_bank_day(date(2024, 4, 1))  # Easter Monday


def test_last_bank_day():
    assert last_bank_day(YearMonth(2026, 10)) == date(2026, 10, 30)
    assert last_bank_day(YearMonth(2026, 11)) == date(2026, 11, 30)
    assert last_bank_day(YearMonth(2026, 12)) == date(2026, 12, 30)
    assert last_bank_day(YearMonth(2024, 3)) == date(2024, 3, 27)  # before Easter


def test_a_payment_on_a_closing_day_is_drawn_on_the_next_bank_day():
    assert drawn_on(date(2026, 10, 31)) == date(2026, 11, 2)
    assert drawn_on(date(2026, 11, 2)) == date(2026, 11, 2)
    assert next_bank_day(date(2026, 12, 24)) == date(2026, 12, 28)
