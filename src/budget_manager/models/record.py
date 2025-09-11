from dataclasses import dataclass, field

from pendulum import Date


@dataclass
class Record:
    amount: float
    timestamp: Date = field(default_factory=Date.today)
    name: str | None = None
