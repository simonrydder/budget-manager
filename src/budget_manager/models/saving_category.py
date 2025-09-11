from dataclasses import dataclass, field

from budget_manager.models.record import Record
from budget_manager.types import Month
from budget_manager.utils.pendulum import is_date_in_month


@dataclass
class SavingCategory:
    name: str
    start_amount: float = 0.0
    records: list[Record] = field(default_factory=list[Record])

    def _sum_records(self, records: list[Record], month: Month, year: int | None = None) -> float:
        total = 0
        for record in records:
            if is_date_in_month(record.timestamp, month, year):
                total += record.amount

        return total

    def deposits(self, month: Month, year: int | None = None) -> float:
        deposit_records = [record for record in self._records if record.amount > 0]
        return self._sum_records(deposit_records, month, year)

    def withdrawals(self, month: Month, year: int | None = None) -> float:
        withdrawal_records = [record for record in self.records if record.amount < 0]
        total = self._sum_records(withdrawal_records, month, year)
        return abs(total)

    def balance(self, month: Month, year: int | None = None) -> float: ...
