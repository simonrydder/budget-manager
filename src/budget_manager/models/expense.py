from dataclasses import dataclass, field

from pendulum import Date


@dataclass
class Expense:
    name: str | None
    amount: float
    timestamp: Date = field(default_factory=Date.today)
