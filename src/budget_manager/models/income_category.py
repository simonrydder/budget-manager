from dataclasses import dataclass, field

from pendulum import Date, Duration

from budget_manager.models.income_plan import IncomePlan
from budget_manager.models.record import Record
from budget_manager.types import Month
from budget_manager.utils.pendulum import is_completed_month, is_current_month


@dataclass
class IncomeCategory:
    name: str
    income_plans: list[IncomePlan] = field(default_factory=list[IncomePlan])
    incomes: list[Record] = field(default_factory=list[Record])

    def income(self, month: Month, year: int) -> float:
        if is_completed_month(month, year):
            return self.actual_income(month, year)

        if is_current_month(month, year):
            return self.actual_income(month, year)

        return self.expected_income(month, year)

    def actual_income(self, month: Month, year: int) -> float:
        total_income = 0
        for income in self.incomes:
            total_income += income.amount if self._within_previous_month(income, month, year) else 0

        return total_income

    def expected_income(self, month: Month, year: int) -> float:
        return sum(plan.expected_income(self, month, year) for plan in self.income_plans)

    def _within_previous_month(self, income: Record, month: Month, year: int) -> bool:
        """Incomes paid in April are used in May and etc."""
        date = Date(year, month, 1)
        before_first = income.timestamp < date
        after_or_equal_previous_first = income.timestamp >= date - Duration(months=1)

        within_previous_month = before_first and after_or_equal_previous_first

        return within_previous_month
