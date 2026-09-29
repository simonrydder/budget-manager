"""When expenses are due and when income is expected."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from budget_manager.engine.months import YearMonth

#: Choices offered in the app. 0 means a single payment (a one-off expense or savings goal).
FREQUENCIES: dict[int, str] = {
    0: "One-off",
    1: "Monthly",
    2: "Every 2 months",
    3: "Quarterly",
    4: "Every 4 months",
    6: "Every 6 months",
    12: "Yearly",
    24: "Every 2 years",
    36: "Every 3 years",
}


def frequency_label(interval_months: int) -> str:
    return FREQUENCIES.get(interval_months, f"Every {interval_months} months")


@dataclass(frozen=True)
class Schedule:
    """Due dates of an expense: ``first_due`` and then every ``interval_months`` (0 = once).

    The day of the month follows ``first_due`` and is clamped to short months, so a payment
    on the 31st falls on 28/29 February and on 31 March again. Due dates after ``end_date``
    are dropped.
    """

    first_due: date
    interval_months: int = 0
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.interval_months < 0:
            raise ValueError("interval_months must be 0 (one-off) or positive")

    @property
    def first_month(self) -> YearMonth:
        return YearMonth.of(self.first_due)

    def due_in(self, month: YearMonth) -> date | None:
        """The due date inside ``month``, if there is one."""
        offset = self.first_month.months_until(month)
        if offset < 0:
            return None
        if self.interval_months == 0 and offset != 0:
            return None
        if self.interval_months and offset % self.interval_months:
            return None
        return self._valid(month.day(self.first_due.day))

    def next_due(self, month: YearMonth) -> date | None:
        """The first due date in ``month`` or later."""
        offset = self.first_month.months_until(month)
        if offset <= 0:
            return self._valid(self.first_due)
        if self.interval_months == 0:
            return None
        steps = -(-offset // self.interval_months)
        due_month = self.first_month + steps * self.interval_months
        return self._valid(due_month.day(self.first_due.day))

    def next_due_from(self, day: date) -> date | None:
        """The first due date on or after ``day``."""
        due = self.next_due(YearMonth.of(day))
        while due is not None and due < day:
            due = self.next_due(YearMonth.of(due) + 1)
        return due

    def upcoming(self, day: date, count: int) -> list[date]:
        """Up to ``count`` due dates on or after ``day``."""
        dates: list[date] = []
        due = self.next_due_from(day)
        while due is not None and len(dates) < count:
            dates.append(due)
            due = self.next_due(YearMonth.of(due) + 1)
        return dates

    def _valid(self, due: date) -> date | None:
        if self.end_date is not None and due > self.end_date:
            return None
        return due


@dataclass(frozen=True)
class MonthSchedule:
    """Budget months an income is expected in: ``first_month`` and every ``interval_months``."""

    first_month: YearMonth
    interval_months: int = 1
    end_month: YearMonth | None = None

    def is_due(self, month: YearMonth) -> bool:
        offset = self.first_month.months_until(month)
        if offset < 0 or (self.end_month is not None and month > self.end_month):
            return False
        if self.interval_months == 0:
            return offset == 0
        return offset % self.interval_months == 0
