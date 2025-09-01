from dataclasses import dataclass, field

from pendulum import Date, Duration, Interval

from budget_manager.models.allocation_plan import AllocationPlan
from budget_manager.models.expense import Expense
from budget_manager.types import Month


@dataclass
class ExpenseCategory:
    name: str

    allocations: list[AllocationPlan] = field(default_factory=list[AllocationPlan])

    expenses: list[Expense] = field(default_factory=list[Expense])

    children: list["ExpenseCategory"] = field(default_factory=list["ExpenseCategory"])
    parent: "ExpenseCategory | None" = None

    def monthly_balance(self, month: Month, year: int) -> float:
        current_date = Date(year, month, 1)

        if all(current_date < alloc.start_date for alloc in self.allocations):
            return sum(alloc.start_amount for alloc in self.allocations)

        monthly_saving = self.monthly_saving(month, year)
        monthly_expense = self.monthly_expense_total(month, year)
        monthly_balance = monthly_saving - monthly_expense

        last_month = current_date - Duration(months=1)
        return monthly_balance + self.monthly_balance(last_month.month, last_month.year)

    def monthly_saving(self, month: Month, year: int) -> float:
        return sum(alloc.monthly_allocation(month, year) for alloc in self.allocations)

    def monthly_expense_total(self, month: Month, year: int) -> float:
        start = Date(year, month, 1)
        end = start + Duration(months=1, days=-1)
        month_interval = Interval(start, end)
        return sum([e.amount for e in self.expenses if e.timestamp in month_interval])
