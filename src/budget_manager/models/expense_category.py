from dataclasses import dataclass, field

from pendulum import Date, Duration, Interval

from budget_manager.models.allocation_plan import AllocationPlan
from budget_manager.models.record import Record
from budget_manager.types import Month
from budget_manager.utils.pendulum import is_completed_month, is_current_month


@dataclass
class ExpenseCategory:
    name: str
    allocations: list[AllocationPlan] = field(default_factory=list[AllocationPlan])
    expenses: list[Record] = field(default_factory=list[Record])

    def balance(self, month: Month, year: int) -> float:
        request_date = Date(year, month, 1)

        if all(request_date < alloc.start_date for alloc in self.allocations):
            return sum(alloc.start_amount for alloc in self.allocations)

        monthly_saving = self.allocation(month, year)
        monthly_expense = self.expense(month, year)
        monthly_balance = monthly_saving - monthly_expense

        last_month = request_date - Duration(months=1)
        return monthly_balance + self.balance(last_month.month, last_month.year)

    def expense(self, month: Month, year: int) -> float:
        if is_completed_month(month, year):
            return self.actual_expense(month, year)

        if is_current_month(month, year):
            return max(self.actual_expense(month, year), self.expected_expense(month, year))

        return self.expected_expense(month, year)

    def allocation(self, month: Month, year: int) -> float:
        return sum(alloc.allocation(month, year) for alloc in self.allocations)

    def actual_expense(self, month: Month, year: int) -> float:
        start = Date(year, month, 1)
        end = start + Duration(months=1, days=-1)
        month_interval = Interval(start, end)
        return sum([e.amount for e in self.expenses if e.timestamp in month_interval])

    def expected_expense(self, month: Month, year: int) -> float:
        return sum(alloc.expected_expense(month, year) for alloc in self.allocations)
