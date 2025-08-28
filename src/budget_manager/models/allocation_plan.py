from dataclasses import dataclass, field

from pendulum import Date, Duration

from budget_manager.types import Month
from budget_manager.utils.pendulum import next_first


@dataclass
class AllocationPlan:
    target_amount: float
    target_date: Date
    repetition: Duration | None
    start_amount: float = 0.0
    start_date: Date = field(default_factory=Date.today)
    end_date: Date | None = None

    def monthly_allocation(self, month: Month, year: int) -> float:
        requested_date = Date(year, month, 1)

        # Before or at the first target date
        if requested_date <= self.target_date:
            return self._compute_initial_allocation()

        # No repetition defined → nothing to save
        if not self.repetition:
            return 0.0

        # After the last valid saving date
        cutoff = self._last_repeated_target_date()
        if cutoff and requested_date > cutoff:
            return 0.0

        # Within valid repetition timeframe
        return self._compute_repeated_allocation()

    def _compute_initial_allocation(self) -> float:
        """Distribute target amount evenly up to the first target date."""

        first_saving = next_first(self.start_date)
        number_of_savings = (self.target_date - first_saving).months + 1
        return (self.target_amount - self.start_amount) / number_of_savings

    def _compute_repeated_allocation(self) -> float:
        """Distribute target amount across one repetition cycle."""

        assert self.repetition is not None
        number_of_savings = self.repetition.months
        return self.target_amount / number_of_savings

    def _last_repeated_target_date(self) -> Date | None:
        """Return the last target date allowed by repetition and end_date, or None if unlimited."""

        if not self.repetition or not self.end_date:
            return None

        last = self.target_date
        while last + self.repetition < self.end_date:
            last += self.repetition
        return last
