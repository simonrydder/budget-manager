from dataclasses import dataclass, field

from pendulum import Date, Duration, Interval

from budget_manager.models.expense import Expense
from budget_manager.models.saving_goal import SavingGoal
from budget_manager.types import Month


@dataclass(frozen=True)
class ExpenseCategory:
    name: str

    goal: SavingGoal
    # saving_strategy: ...

    expenses: list[Expense] = field(default_factory=list[Expense])

    children: list["ExpenseCategory"] = field(default_factory=list["ExpenseCategory"])
    parent: "ExpenseCategory | None" = None

    def get_monthly_balance(self, month: Month, year: int) -> float:
        return 0.0

    def get_monthly_saving(self, month: Month, year: int) -> float:
        return self.goal.get_saving_amount(month, year)

    def get_monthly_expense_total(self, month: Month, year: int) -> float:
        start = Date(year, month, 1)
        end = start + Duration(months=1, days=-1)
        month_interval = Interval(start, end)
        return sum([e.amount for e in self.expenses if e.timestamp in month_interval])
