from dataclasses import dataclass, field

from pendulum import Date

from budget_manager.models.record import Record
from budget_manager.types import Month


@dataclass
class SavingCategory:
    name: str
    _records: list[Record] = field(default_factory=list[Record])

    def deposits(self, month: Month, year: int | None = None) -> float:
        total = 0
        deposit_records = [record for record in self._records if record.amount > 0]
        for record in deposit_records:
            ts = record.timestamp
            if ts.month == month and ts.year == (year or Date.today().year):
                total += record.amount

        return total

    def withdrawals(self, month: Month, year: int | None = None) -> float: ...

    def balance(self, month: Month, year: int | None = None) -> float: ...

    def add_record(self, record: Record) -> None: ...
