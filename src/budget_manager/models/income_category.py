from dataclasses import dataclass, field

from pendulum import Date, Duration

from budget_manager.models.income import Income
from budget_manager.types import Month


@dataclass
class IncomeCategory:
    name: str
    incomes: list[Income] = field(default_factory=list[Income])

    def monthly_income(self, month: Month, year: int) -> float:
        requested_date = Date(year, month, 1)

        total_income = 0
        for income in self.incomes:
            total_income += (
                income.amount
                if income.timestamp < requested_date
                and income.timestamp >= requested_date - Duration(months=1)
                else 0
            )

        return total_income
