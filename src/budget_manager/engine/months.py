"""Calendar months as a small value type.

A *budget month* is the month an expense is due in. Its money is transferred on the last day of
the month before, so the transfer for May happens on 30 April.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_PATTERN = re.compile(r"^(\d{4})-(\d{1,2})$")


@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"Month must be between 1 and 12, got {self.month}")

    @classmethod
    def of(cls, day: date) -> YearMonth:
        return cls(day.year, day.month)

    @classmethod
    def parse(cls, text: str) -> YearMonth:
        """Parse ``"2025-05"``."""
        match = _PATTERN.match(text.strip())
        if not match:
            raise ValueError(f"Expected a month like 2025-05, got {text!r}")
        return cls(int(match.group(1)), int(match.group(2)))

    def __add__(self, months: int) -> YearMonth:
        index = self.year * 12 + (self.month - 1) + months
        return YearMonth(index // 12, index % 12 + 1)

    def __sub__(self, months: int) -> YearMonth:
        return self + (-months)

    def months_until(self, other: YearMonth) -> int:
        """Number of months from this month to ``other`` (negative if ``other`` is earlier)."""
        return (other.year - self.year) * 12 + (other.month - self.month)

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def last_day(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    def day(self, day: int) -> date:
        """The given day in this month, clamped to the month's length (31 → 28 in February)."""
        return date(self.year, self.month, min(day, calendar.monthrange(self.year, self.month)[1]))

    @property
    def name(self) -> str:
        return MONTH_NAMES[self.month - 1]

    @property
    def label(self) -> str:
        return f"{self.name} {self.year}"

    @property
    def short_label(self) -> str:
        return f"{self.name[:3]} {self.year}"

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"
