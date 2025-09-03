from dataclasses import dataclass, field

from pendulum import Date, Duration

from budget_manager.models.income import Income
from budget_manager.models.income_plan import IncomePlan
from budget_manager.types import Month


@dataclass
class IncomeCategory:
    name: str
    income_plans: list[IncomePlan] = field(default_factory=list[IncomePlan])
    incomes: list[Income] = field(default_factory=list[Income])

    def monthly_income(self, month: Month, year: int) -> float:
        total_income = 0
        for income in self.incomes:
            total_income += income.amount if self._within_previous_month(income, month, year) else 0

        return total_income

    def monthly_expected_income(self, month: Month, year: int) -> float:
        return sum(plan.monthly_expected_income(self, month, year) for plan in self.income_plans)

    def _within_previous_month(self, income: Income, month: Month, year: int) -> bool:
        """Incomes paid in April are used in May and etc."""
        date = Date(year, month, 1)
        before_first = income.timestamp < date
        after_or_equal_previous_first = income.timestamp >= date - Duration(months=1)

        within_previous_month = before_first and after_or_equal_previous_first

        return within_previous_month
