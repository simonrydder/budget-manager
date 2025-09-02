from abc import ABC
from typing import TYPE_CHECKING

from budget_manager.types import Month
from budget_manager.utils.pendulum import month_shifter

if TYPE_CHECKING:
    from budget_manager.models.income_category import IncomeCategory


class IncomePlan(ABC):
    def __init__(self) -> None:
        super().__init__()

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return 0


class HistoricalIncomePlan(IncomePlan):
    def __init__(self) -> None:
        super().__init__()

    def monthly_expected_income(
        self, income_category: "IncomeCategory", month: Month, year: int
    ) -> float:
        return income_category.monthly_income(*month_shifter(month, year, -1))
