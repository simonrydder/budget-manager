from abc import ABC
from typing import TYPE_CHECKING

from pendulum import Date, Duration

from budget_manager.types import Month
from budget_manager.utils.pendulum import month_shifter

if TYPE_CHECKING:
    from budget_manager.models.income_category import IncomeCategory


class IncomePlan(ABC):
    def __init__(self) -> None:
        super().__init__()

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return 0

    def adjust(self, **kwargs) -> None:
        raise NotImplementedError("This plan does not support adjustable attributes.")


class HistoricalIncomePlan(IncomePlan):
    def __init__(self) -> None:
        super().__init__()

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return income_category.monthly_income(*month_shifter(month, year, -1))

    def adjust(self, **kwargs) -> None:
        return super().adjust(**kwargs)


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
                if self.start_date.year == year and self.start_date.month == month
                else 0.0
            )

        # Recurring income
        max_date = self.end_date or request_date.add(months=1)

        count = 0
        current = self.start_date
        while current <= max_date:
            if current.year == year and current.month == month:
                count += 1
            current += self.repetition

        return self.amount * count
