from pendulum import Date, Duration

from budget_manager.exeptions import DuplicateCategoryName
from budget_manager.models.account import Account
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.income_category import IncomeCategory
from budget_manager.types import Month
from budget_manager.utils.pendulum import month_shifter, next_first


class Budget:
    def __init__(self, name: str, start_saving: float = 0, start_date: Date | None = None) -> None:
        self._expenses: list[ExpenseCategory] = []
        self._incomes: list[IncomeCategory] = []
        self._accounts: list[Account] = []
        self.start_saving: float = start_saving
        self.start_date: Date = start_date or Date.today()

    @property
    def expenses(self) -> list[ExpenseCategory]:
        return self._expenses

    @property
    def incomes(self) -> list[IncomeCategory]:
        return self._incomes

    @property
    def accounts(self) -> list[Account]:
        return self._accounts

    def saving(self, month: Month, year: int) -> float:
        current_month = next_first(Date.today()) - Duration(months=1)

        request_date = Date(year, month, 1)
        if request_date < self.start_date:
            return self.start_saving

        total_income = sum(
            [
                income.monthly_expected_income(month, year)
                if current_month < request_date
                else income.monthly_income(month, year)
                for income in self._incomes
            ]
        )
        total_expense = sum(
            [
                expense.monthly_expected_expense(month, year)
                if current_month < request_date
                else expense.monthly_expense(month, year)
                for expense in self._expenses
            ]
        )

        total_saving = total_income - total_expense + self.saving(*month_shifter(month, year, -1))
        return total_saving

    def add_expense_category(self, new_expense: ExpenseCategory) -> None:
        if any(expense.name == new_expense.name for expense in self._expenses):
            raise DuplicateCategoryName("Can not add expense category with identical name.")

        self._expenses.append(new_expense)

    def add_income_category(self, new_income: IncomeCategory) -> None:
        if any(income.name == new_income.name for income in self._incomes):
            raise DuplicateCategoryName("Can not add expense category with identical name.")

        self._incomes.append(new_income)

    def add_account(self, new_account: Account) -> None: ...

    def link_expense_category_to_account(
        self, expense: ExpenseCategory, account: Account
    ) -> None: ...
