from budget_manager.models.account import Account
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.income_category import IncomeCategory


class Budget:
    def __init__(self, name: str, saving: float = 0) -> None:
        pass

    @property
    def expenses(self) -> list[ExpenseCategory]:
        return []

    @property
    def incomes(self) -> list[IncomeCategory]:
        return []

    @property
    def saving(self) -> float:
        return 0

    @property
    def accounts(self) -> list[Account]:
        return []

    def add_expense_category(self, expense: ExpenseCategory) -> None: ...

    def add_income_category(self, income: IncomeCategory) -> None: ...

    def add_account(self, account: Account) -> None: ...

    def link_expense_category_to_account(
        self, expense: ExpenseCategory, account: Account
    ) -> None: ...

    def save(self) -> None: ...

    def load(self, name: str) -> None: ...
