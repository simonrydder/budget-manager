"""Plain data the engine works on. The web app builds these from the database."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum

from budget_manager.engine.months import YearMonth
from budget_manager.engine.schedule import MonthSchedule, Schedule


class Role(StrEnum):
    NEMKONTO = "nemkonto"  # income arrives here; transfers go out from here
    SAVINGS = "savings"  # holds the savings goals *and* General Savings
    NORMAL = "normal"


class Kind(StrEnum):
    FIXED = "fixed"
    VARIABLE = "variable"


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    role: Role = Role.NORMAL
    min_balance: int = 0  # X, only used for the NemKonto
    max_balance: int = 0  # Y, only used for the NemKonto


@dataclass(frozen=True)
class Expense:
    """A planned cost that money is set aside for. Amounts are in hundredths."""

    id: int
    name: str
    account_id: int
    kind: Kind
    amount: int
    schedule: Schedule
    start_month: YearMonth  # first budget month that receives a contribution
    starting_balance: int = 0

    def expected_spend(self, month: YearMonth) -> int:
        if month < self.start_month:
            return 0
        return self.amount if self.schedule.due_in(month) else 0

    def contribution(self, month: YearMonth, planned_balance: int) -> int:
        """What to set aside in the transfer for ``month``.

        The rest of the next payment is spread evenly over the transfers left before it is due,
        so a changed amount is caught up by the due date. Amounts are rounded up to whole units
        and the last transfer before a payment tops up exactly.
        """
        if month < self.start_month:
            return 0
        due = self.schedule.next_due(month)
        if due is None:
            return 0
        missing = self.amount - planned_balance
        if missing <= 0:
            return 0
        transfers_left = month.months_until(YearMonth.of(due)) + 1
        if transfers_left <= 1:
            return missing
        per_transfer = -(-missing // transfers_left)
        per_transfer = -(-per_transfer // 100) * 100
        return min(per_transfer, missing)


@dataclass(frozen=True)
class Income:
    id: int
    name: str
    amount: int  # expected amount each time it arrives
    schedule: MonthSchedule

    def expected(self, month: YearMonth) -> int:
        return self.amount if self.schedule.is_due(month) else 0


@dataclass(frozen=True)
class Line:
    """What happened to one expense in one closed month."""

    contribution: int = 0
    expected_spend: int = 0
    topup: int = 0  # added from General Savings because a fixed expense went below zero
    cover: int = 0  # taken to the NemKonto; later contributions rebuild it
    release: int = 0  # moved to General Savings; not rebuilt


@dataclass
class ExpenseLedger:
    """An expense with its closed months and its actual spending."""

    expense: Expense
    lines: dict[YearMonth, Line] = field(default_factory=dict)
    spending: dict[YearMonth, int] = field(default_factory=dict)

    def planned_balance_before(self, month: YearMonth) -> int:
        """The balance the plan expects before the transfer for ``month``.

        It assumes every payment cost exactly the expected amount, so actual deviations never
        change the contributions. Money taken to cover the NemKonto is rebuilt.
        """
        total = self.expense.starting_balance
        for line_month, line in self.lines.items():
            if line_month < month:
                total += line.contribution - line.expected_spend - line.cover
        return total

    def balance_after_close(self, month: YearMonth) -> int:
        """Actual balance right after the transfer for ``month`` (spending up to the month before)."""
        total = self.expense.starting_balance
        for line_month, line in self.lines.items():
            if line_month <= month:
                total += line.contribution + line.topup - line.cover - line.release
        for spend_month, spent in self.spending.items():
            if spend_month < month:
                total -= spent
        return total

    def balance_end_of(self, month: YearMonth) -> int:
        """Actual balance at the end of ``month``, after its spending, before the next transfer."""
        return self.balance_after_close(month) - self.spending.get(month, 0)


@dataclass
class BudgetState:
    """Everything needed to plan the next month-end close."""

    accounts: list[Account]
    ledgers: list[ExpenseLedger]
    incomes: list[Income]
    month: YearMonth  # budget month of the next close
    nemkonto: int  # NemKonto balance before the income for ``month`` arrives
    general_savings: int  # General Savings before the next close

    def __post_init__(self) -> None:
        roles = [account.role for account in self.accounts]
        if roles.count(Role.NEMKONTO) != 1:
            raise ValueError("There must be exactly one NemKonto")
        if roles.count(Role.SAVINGS) != 1:
            raise ValueError("Exactly one account must hold General Savings")

    @property
    def nemkonto_account(self) -> Account:
        return next(a for a in self.accounts if a.role is Role.NEMKONTO)

    @property
    def savings_account(self) -> Account:
        return next(a for a in self.accounts if a.role is Role.SAVINGS)

    def account(self, account_id: int) -> Account:
        return next(a for a in self.accounts if a.id == account_id)

    def ledger(self, expense_id: int) -> ExpenseLedger:
        return next(ledger for ledger in self.ledgers if ledger.expense.id == expense_id)

    def expected_income(self, month: YearMonth) -> int:
        return sum(income.expected(month) for income in self.incomes)

    def copy(self) -> BudgetState:
        return copy.deepcopy(self)

    def account_balances_after_close(self, month: YearMonth) -> dict[int, int]:
        """Account balances right after the transfer for ``month`` (which must be closed)."""
        balances = {account.id: 0 for account in self.accounts}
        for ledger in self.ledgers:
            balances[ledger.expense.account_id] += ledger.balance_after_close(month)
        balances[self.nemkonto_account.id] += self.nemkonto
        balances[self.savings_account.id] += self.general_savings
        return balances

    def current_expense_balances(self) -> dict[int, int]:
        """Balances after the last transfer and the spending entered since."""
        return {ledger.expense.id: ledger.balance_end_of(self.month - 1) for ledger in self.ledgers}

    def current_account_balances(self) -> dict[int, int]:
        balances = {account.id: 0 for account in self.accounts}
        for expense_id, balance in self.current_expense_balances().items():
            balances[self.ledger(expense_id).expense.account_id] += balance
        balances[self.nemkonto_account.id] += self.nemkonto
        balances[self.savings_account.id] += self.general_savings
        return balances
