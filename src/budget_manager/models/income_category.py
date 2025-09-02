from dataclasses import dataclass, field

from pendulum import Date, Duration

from budget_manager.models.income import Income
from budget_manager.models.income_plan import IncomePlan
from budget_manager.types import Month


@dataclass
class IncomeCategory:
    name: str
    income_plan: IncomePlan
    incomes: list[Income] = field(default_factory=list[Income])

    def monthly_income(self, month: Month, year: int) -> float:
        total_income = 0
        for income in self.incomes:
            total_income += income.amount if self._within_previous_month(income, month, year) else 0

        return total_income

    def monthly_expected_income(self, month: Month, year: int) -> float:
        return self.income_plan.monthly_expected_income(self, month, year)

    def _within_previous_month(self, income: Income, month: Month, year: int) -> bool:
        date = Date(year, month, 1)
        before_or_equal_first = income.timestamp <= date
        after_previous_first = income.timestamp > date - Duration(months=1)

        within_previous_month = before_or_equal_first and after_previous_first

        return within_previous_month
