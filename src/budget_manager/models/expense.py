from dataclasses import dataclass
from datetime import date

from budget_manager.models.amount import Amount
from budget_manager.models.category import Category


@dataclass(frozen=True)
class Expense:
    category: Category | None
    amount: Amount
    date: date
    name: str | None = None
    repitition: str | None = None
