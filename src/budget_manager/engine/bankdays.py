"""Danish bank days: weekdays that are not one of the banks' closing days.

A payment due on a closing day is drawn on the next bank day, and standing orders "on the last
bank day" leave on the last one of the month.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

from budget_manager.engine.months import YearMonth


def easter(year: int) -> date:
    """Easter Sunday (the Gregorian computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


@cache
def closing_days(year: int) -> frozenset[date]:
    """The days Danish banks are closed besides weekends."""
    sunday = easter(year)
    return frozenset(
        {
            date(year, 1, 1),  # New Year's Day
            sunday - timedelta(days=3),  # Maundy Thursday
            sunday - timedelta(days=2),  # Good Friday
            sunday + timedelta(days=1),  # Easter Monday
            sunday + timedelta(days=39),  # Ascension Day
            sunday + timedelta(days=40),  # the Friday after it
            sunday + timedelta(days=50),  # Whit Monday
            date(year, 6, 5),  # Constitution Day
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        }
    )


def is_bank_day(day: date) -> bool:
    return day.weekday() < 5 and day not in closing_days(day.year)


def next_bank_day(day: date) -> date:
    """``day`` itself when it is a bank day, otherwise the first bank day after it."""
    while not is_bank_day(day):
        day += timedelta(days=1)
    return day


def first_bank_day(month: YearMonth) -> date:
    return next_bank_day(month.first_day())


def last_bank_day(month: YearMonth) -> date:
    day = month.last_day()
    while not is_bank_day(day):
        day -= timedelta(days=1)
    return day


def drawn_on(due: date) -> date:
    """The day a payment due on ``due`` leaves the account."""
    return next_bank_day(due)
