from dataclasses import dataclass, field

from budget_manager.models.amount import Amount


@dataclass
class Account:
    name: str
    _balance: Amount = field(default_factory=lambda: Amount(0))

    @property
    def balance(self) -> Amount:
        """Public read-only access to balance."""
        return self._balance

    def deposit(self, amount: Amount) -> None:
        if amount.value < 0:
            raise ValueError("Deposit amount must be non-negative")

        self._balance += amount

    def withdraw(self, amount: Amount) -> None:
        if amount.value < 0:
            raise ValueError("Withdrawal amount must be non-negative")

        self._balance -= amount
