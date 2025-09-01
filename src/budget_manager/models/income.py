from dataclasses import dataclass, field

from pendulum import Date

from budget_manager.types import Month


@dataclass
class Income:
    name: str | None
    amount: float
    timestamp: Date = field(default_factory=Date.today)


@dataclass
class IncomeCategory:
    name: str
    incomes: list[Income] = field(default_factory=list[Income])

    def monthly_income(self, month: Month, year: int) -> float:
        return 0
