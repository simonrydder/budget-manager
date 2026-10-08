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
    FIXED = "fixed"  # the same amount, paid on its due date (rent, insurance)
    VARIABLE = "variable"  # paid on its due date, the amount varies (power, heating)
    RUNNING = "running"  # spent bit by bit through the month (food, fuel, everyday spending)


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
    # The month ``starting_balance`` refers to the start of. Normally the start month; when the
    # budget is started mid-month it is the current month, whose payments come out of it.
    opening_month: YearMonth | None = None

    @property
    def opening(self) -> YearMonth:
        return min(self.opening_month or self.start_month, self.start_month)

    def due_before_start(self) -> int:
        """Payments due between the opening month and the start month, paid from the
        starting balance."""
        total = 0
        month = self.opening
        while month < self.start_month:
            if self.schedule.due_in(month):
                total += self.amount
            month += 1
        return total

    def suggested_starting_balance(self) -> int | None:
        """What should already be set aside at the start of the opening month so the monthly
        contribution is the same before and after the next payment ("top up all").

        Payments due in the opening month must be there in full. ``None`` for one-off goals,
        which have no steady amount.
        """
        due = self.schedule.next_due(self.opening)
        if due is None:
            return 0
        due_month = YearMonth.of(due)
        if due_month < self.start_month:
            return self.amount
        interval = self.schedule.interval_months
        if not interval:
            return None
        rate = _round_up(self.amount, interval)
        transfers = self.start_month.months_until(due_month) + 1
        return max(0, self.amount - rate * transfers)

    def expected_spend(self, month: YearMonth) -> int:
        if month < self.start_month:
            return 0
        return self.amount if self.schedule.due_in(month) else 0

    def cycle_start(self, month: YearMonth) -> YearMonth:
        """The first transfer that saves for the payment due next after ``month`` starts."""
        previous = self.schedule.previous_due(month)
        start = YearMonth.of(previous) + 1 if previous else self.start_month
        return max(start, self.start_month)

    def contribution(
        self, month: YearMonth, planned_balance: int, planned_at_cycle_start: int | None = None
    ) -> int:
        """What to set aside in the transfer for ``month``.

        Each saving period (the transfers up to a payment) uses one fixed amount, rounded up to
        whole units, so the transfer stays the same every month and can be a standing order in
        the bank. Rounding up overshoots a little; the next period starts from what is left.
        If the amount changes, the rest is caught up by the due date. Monthly payments are
        topped up exactly.
        """
        if month < self.start_month:
            return 0
        due = self.schedule.next_due(month)
        if due is None:
            return 0
        due_month = YearMonth.of(due)
        missing = self.amount - planned_balance
        cycle = self.cycle_start(month)
        cycle_transfers = cycle.months_until(due_month) + 1
        if cycle_transfers <= 1:
            return max(0, missing)
        if planned_at_cycle_start is None:
            planned_at_cycle_start = planned_balance
        rate = _round_up(max(0, self.amount - planned_at_cycle_start), cycle_transfers)
        if missing <= -rate:
            return 0  # already a whole contribution ahead
        transfers_left = month.months_until(due_month) + 1
        catch_up = _round_up(missing, transfers_left) if missing > 0 else 0
        return max(rate, catch_up)


def _round_up(amount: int, parts: int) -> int:
    """``amount`` split into ``parts``, rounded up to whole units (hundredths)."""
    per_part = -(-amount // parts)
    return -(-per_part // 100) * 100


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
    funding: int = 0  # part of ``topup`` that fills a new expense up to its steady path


@dataclass(frozen=True)
class Adjustment:
    """Money moved between General Savings and an expense between two month-ends."""

    month: YearMonth  # budget month of the next month-end after the move
    amount: int  # positive: into the expense
    planned: bool = False  # counts towards the plan (filling a new expense)


@dataclass
class ExpenseLedger:
    """An expense with its closed months, its actual spending and the money moved to or from
    it between month-ends."""

    expense: Expense
    lines: dict[YearMonth, Line] = field(default_factory=dict)
    spending: dict[YearMonth, int] = field(default_factory=dict)
    adjustments: list[Adjustment] = field(default_factory=list)

    def _adjusted(self, until: YearMonth, *, planned_only: bool = False) -> int:
        return sum(
            item.amount
            for item in self.adjustments
            if item.month <= until and (item.planned or not planned_only)
        )

    def planned_balance_before(self, month: YearMonth) -> int:
        """The balance the plan expects before the transfer for ``month``.

        It assumes every payment cost exactly the expected amount, so actual deviations never
        change the contributions. Money taken to cover the NemKonto is rebuilt.
        """
        total = self.expense.starting_balance - self.expense.due_before_start()
        for line_month, line in self.lines.items():
            if line_month < month:
                total += line.contribution - line.expected_spend - line.cover + line.funding
        return total + self._adjusted(month, planned_only=True)

    def planned_at_cycle_start(self, month: YearMonth) -> int:
        """The planned balance a saving period starting at ``month`` begins with, including any
        filling from General Savings made at that month-end."""
        line = self.lines.get(month)
        return self.planned_balance_before(month) + (line.funding if line else 0)

    def balance_after_close(self, month: YearMonth) -> int:
        """Actual balance right after the transfer for ``month`` (spending up to the month before)."""
        total = self.expense.starting_balance
        for line_month, line in self.lines.items():
            if line_month <= month:
                total += line.contribution + line.topup - line.cover - line.release
        for spend_month, spent in self.spending.items():
            if spend_month < month:
                total -= spent
        return total + self._adjusted(month)

    def balance_end_of(self, month: YearMonth) -> int:
        """Actual balance at the end of ``month``, after its spending and the moves made since
        the transfer, before the next transfer."""
        moved = sum(item.amount for item in self.adjustments if item.month == month + 1)
        return self.balance_after_close(month) - self.spending.get(month, 0) + moved


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
