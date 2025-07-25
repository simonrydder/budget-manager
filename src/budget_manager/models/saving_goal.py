from dataclasses import dataclass
from datetime import date

from budget_manager.models.amount import Amount
from budget_manager.models.category import Category


@dataclass
class SavingGoal:
    category: Category
    target_amount: Amount
    target_date: date
    repetition: str | None
    currnet_amount: Amount = Amount(0)
    start_date: date = date.today()
    end_date: date | None = None
