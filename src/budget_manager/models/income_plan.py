from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pendulum import Date, Duration

from budget_manager.types import Month
from budget_manager.utils.pendulum import month_shifter

if TYPE_CHECKING:
    from budget_manager.models.income_category import IncomeCategory


class IncomePlan(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return 0


class HistoricalIncomePlan(IncomePlan):
    def __init__(self) -> None:
        super().__init__()

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return income_category.monthly_income(*month_shifter(month, year, -1))


class ScheduledIncomePlan(IncomePlan):
    def __init__(
        self,
        amount: float = 0,
        repetition: Duration | None = Duration(months=1),
        start_date: Date | None = None,
        end_date: Date | None = None,
    ) -> None:
        super().__init__()
        self.amount = amount
        self.repetition = repetition
        self.start_date = start_date or Date.today()
        self.end_date = end_date

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        request_date = Date(year, month, 1)

        # One-time income
        if self.repetition is None:
            return (
                self.amount
                if self._pay_date_within_request_date(self.start_date, request_date)
                else 0.0
            )

        # Recurring income
        max_date = self.end_date or request_date.add(months=1)

        count = 0
        current = self.start_date
        while current <= max_date:
            if self._pay_date_within_request_date(current, request_date):
                count += 1
            current += self.repetition

        return self.amount * count

    def _pay_date_within_request_date(self, pay_date: Date, request_date: Date) -> bool:
        compare_date = request_date - Duration(months=1)

        same_year = pay_date.year == compare_date.year
        same_month = pay_date.month == compare_date.month

        return same_year and same_month
