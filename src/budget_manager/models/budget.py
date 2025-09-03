from budget_manager.exeptions import DuplicateCategoryName
from budget_manager.models.account import Account
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.income_category import IncomeCategory
from budget_manager.types import Month


class Budget:
    def __init__(self, name: str, start_saving: float = 0) -> None:
        self._expenses: list[ExpenseCategory] = []
        self._incomes: list[IncomeCategory] = []
        self._accounts: list[Account] = []

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
        return 0

    def add_expense_category(self, new_expense: ExpenseCategory) -> None:
        if any(exp.name == new_expense.name for exp in self._expenses):
            raise DuplicateCategoryName("Can not add expense category with identical name.")

        self._expenses.append(new_expense)

    def add_income_category(self, new_income: IncomeCategory) -> None: ...

    def add_account(self, new_account: Account) -> None: ...

    def link_expense_category_to_account(
        self, expense: ExpenseCategory, account: Account
    ) -> None: ...

    def save(self) -> None: ...

    def load(self, name: str) -> None: ...
