from dataclasses import dataclass, field

from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.income_category import IncomeCategory


@dataclass
class Budget:
    name: str
    expenses: list[ExpenseCategory] = field(default_factory=list[ExpenseCategory])
    incomes: list[IncomeCategory] = field(default_factory=list[IncomeCategory])
    saving: float = 0

    def save_budget(self) -> None: ...

    def load_budget(self) -> None: ...
