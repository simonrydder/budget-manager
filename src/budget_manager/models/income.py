from dataclasses import dataclass
from datetime import date

from budget_manager.models.amount import Amount


@dataclass
class Income:
    name: str | None
    amount: Amount
    date: date
    repitition: str | None = None
