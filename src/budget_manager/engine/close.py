"""The month-end close: how much goes where on the last day of the month.

For budget month *B* the close happens on the last day of *B − 1*:

1. Fixed expenses that went below zero during *B − 1* are topped up from General Savings, and
   their expected amount is raised to the real cost when the payment itself cost more.
2. Every active expense gets its contribution for *B*.
3. Each account receives the contributions of its expenses minus the interest that already
   landed on it (interest counts as if it had arrived on the NemKonto).
4. What is left on the NemKonto is kept between its minimum (X) and maximum (Y): the excess goes
   to General Savings, a shortfall is taken from General Savings. If General Savings cannot cover
   it, the NemKonto may go below X, and if it would go below 0 the person has to choose which
   expenses to take the money from (``covers``).

All transfers are netted so the NemKonto sends (or receives) one amount per account.

The NemKonto is also the everyday account: what is spent from it during the month
(``nemkonto_spent``) comes out of what it held after the last month-end, before the minimum and
maximum are applied. So the money left on it after a month-end is the everyday money for the
month, and the month-end refills it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from budget_manager.engine.model import BudgetState, Kind, Line, Role
from budget_manager.engine.money import format_amount
from budget_manager.engine.months import YearMonth


@dataclass(frozen=True)
class Notice:
    level: str  # "info", "warning" or "danger"
    code: str
    message: str
    amount: int = 0
    expense_id: int | None = None


@dataclass
class LinePlan:
    expense_id: int
    account_id: int
    balance_before: int  # actual balance after last month's spending
    planned_before: int
    contribution: int = 0
    expected_spend: int = 0
    topup_needed: int = 0
    topup_chosen: int = 0
    funding_requested: int = 0
    funding: int = 0
    topup: int = 0
    cover: int = 0
    release: int = 0
    amount_before: int = 0
    amount_after: int | None = None  # set when a fixed expense's expected amount is raised
    next_due: date | None = None

    @property
    def balance_after(self) -> int:
        return self.balance_before + self.topup - self.cover - self.release + self.contribution

    def to_line(self) -> Line:
        return Line(
            contribution=self.contribution,
            expected_spend=self.expected_spend,
            topup=self.topup,
            cover=self.cover,
            release=self.release,
            funding=self.funding,
        )


@dataclass
class TransferPlan:
    """The net amount the NemKonto sends to one account (negative: the account sends it back)."""

    account_id: int
    contributions: int = 0
    interest: int = 0
    topups: int = 0
    covers: int = 0
    releases: int = 0
    general_savings: int = 0  # net change of General Savings, only on the savings account

    @property
    def amount(self) -> int:
        return (
            self.contributions
            - self.interest
            + self.topups
            - self.covers
            - self.releases
            + self.general_savings
        )


@dataclass
class ClosePlan:
    month: YearMonth
    lines: dict[int, LinePlan]
    transfers: dict[int, TransferPlan]
    nemkonto_before: int
    income: int
    interest: dict[int, int]
    nemkonto_after_transfers: int  # before surplus/shortfall handling
    surplus: int  # moved from the NemKonto to General Savings
    taken: int  # moved from General Savings to the NemKonto
    nemkonto_end: int
    general_savings_before: int
    general_savings_after: int
    min_balance: int
    max_balance: int
    notices: list[Notice] = field(default_factory=list)
    nemkonto_spent: int = 0  # everyday spending from the NemKonto since the last month-end

    @property
    def transfer_date(self) -> date:
        return (self.month - 1).last_day()

    @property
    def interest_total(self) -> int:
        return sum(self.interest.values())

    @property
    def contributions_total(self) -> int:
        return sum(line.contribution for line in self.lines.values())

    @property
    def topups_total(self) -> int:
        return sum(line.topup for line in self.lines.values())

    @property
    def releases_total(self) -> int:
        return sum(line.release for line in self.lines.values())

    @property
    def covers_total(self) -> int:
        return sum(line.cover for line in self.lines.values())

    @property
    def shortfall(self) -> int:
        """How far the NemKonto would end below zero. Must be covered before closing."""
        return max(0, -self.nemkonto_end)

    @property
    def general_savings_change(self) -> int:
        return self.general_savings_after - self.general_savings_before


class CloseError(ValueError):
    pass


def plan_close(
    state: BudgetState,
    *,
    income: int = 0,
    interest: dict[int, int] | None = None,
    covers: dict[int, int] | None = None,
    releases: dict[int, int] | None = None,
    topups: dict[int, int] | None = None,
    funding: dict[int, int] | None = None,
    nemkonto_spent: int = 0,
) -> ClosePlan:
    """Plan the close for ``state.month``.

    ``income`` is the income that arrived on the NemKonto for the month. ``interest`` maps
    account ids to the interest (negative for interest paid) that landed during the month
    before. ``covers`` and ``releases`` map expense ids to amounts taken from an expense to the
    NemKonto or moved to General Savings. ``topups`` maps expense ids to amounts the person
    chose to move from General Savings to an expense (any kind, e.g. a variable expense that
    has been below zero for a while). ``funding`` is the same, but counts towards the plan: it
    fills a new expense up to what a steady monthly amount would have saved by now.
    ``nemkonto_spent`` is what was spent from the NemKonto itself since the last month-end.
    """
    interest = {k: v for k, v in (interest or {}).items() if v}
    covers = {k: v for k, v in (covers or {}).items() if v}
    releases = {k: v for k, v in (releases or {}).items() if v}
    topups = {k: v for k, v in (topups or {}).items() if v}
    funding = {k: v for k, v in (funding or {}).items() if v}
    month = state.month
    nemkonto = state.nemkonto_account
    savings = state.savings_account
    notices: list[Notice] = []

    account_ids = {account.id for account in state.accounts}
    for account_id in interest:
        if account_id not in account_ids:
            raise CloseError(f"Unknown account {account_id}")
    known = {ledger.expense.id for ledger in state.ledgers}
    for expense_id in (*covers, *releases, *topups, *funding):
        if expense_id not in known:
            raise CloseError(f"Unknown expense {expense_id}")

    lines: dict[int, LinePlan] = {}
    for ledger in state.ledgers:
        expense = ledger.expense
        balance = ledger.balance_end_of(month - 1)
        line = LinePlan(
            expense_id=expense.id,
            account_id=expense.account_id,
            balance_before=balance,
            planned_before=ledger.planned_balance_before(month),
            amount_before=expense.amount,
        )
        if expense.kind is Kind.FIXED and balance < 0:
            line.topup_needed = -balance
            previous = ledger.lines.get(month - 1)
            spent = ledger.spending.get(month - 1, 0)
            paid = expense.schedule.due_in(month - 1)
            # A different first payment says nothing about the normal amount.
            usual = paid is None or expense.amount_on(paid) == expense.amount
            if usual and previous and previous.expected_spend and spent > previous.expected_spend:
                line.amount_after = spent if spent > expense.amount else None
        line.topup_chosen = topups.get(expense.id, 0)
        if line.topup_chosen < 0:
            raise CloseError("A top-up cannot be negative")
        line.funding_requested = funding.get(expense.id, 0)
        if line.topup_chosen < 0 or line.funding_requested < 0:
            raise CloseError("A top-up cannot be negative")
        line.topup_needed += line.topup_chosen + line.funding_requested
        effective = replace(expense, amount=line.amount_after) if line.amount_after else expense
        cycle_start = effective.cycle_start(month)
        planned_at_start = ledger.planned_at_cycle_start(cycle_start)
        if cycle_start == month:
            planned_at_start += line.funding_requested
        line.contribution = effective.contribution(
            month, line.planned_before + line.funding_requested, planned_at_start
        )
        line.expected_spend = effective.expected_spend(month)
        line.next_due = effective.schedule.next_due(month)
        line.cover = covers.get(expense.id, 0)
        line.release = releases.get(expense.id, 0)
        if line.cover < 0 or line.release < 0:
            raise CloseError("Amounts taken from an expense cannot be negative")
        available = max(0, balance) + line.contribution
        if line.cover + line.release > available:
            name = expense.name
            raise CloseError(
                f"{name} only has {format_amount(available)} after this month's contribution"
            )
        lines[expense.id] = line

    transfers = {
        account.id: TransferPlan(account.id)
        for account in state.accounts
        if account.role is not Role.NEMKONTO
    }
    for line in lines.values():
        transfer = transfers.get(line.account_id)
        if transfer is None:
            continue  # set aside on the NemKonto itself: nothing to transfer
        transfer.contributions += line.contribution
        transfer.covers += line.cover
        transfer.releases += line.release
    for account_id, amount in interest.items():
        if account_id != nemkonto.id:
            transfers[account_id].interest += amount

    contributions = sum(line.contribution for line in lines.values())
    after = (
        state.nemkonto
        - nemkonto_spent
        + income
        + sum(interest.values())
        - contributions
        + sum(line.cover for line in lines.values())
    )

    pool = state.general_savings + sum(line.release for line in lines.values())
    surplus = taken = 0
    if after > nemkonto.max_balance:
        surplus = after - nemkonto.max_balance
    elif after < nemkonto.min_balance:
        needed = nemkonto.min_balance - after
        taken = min(needed, max(0, pool))
        if taken < needed:
            end = after + taken
            notices.append(
                Notice(
                    "warning",
                    "savings_cannot_cover_nemkonto",
                    f"General Savings cannot cover the shortfall. The NemKonto ends at "
                    f"{format_amount(end)}, below its minimum of "
                    f"{format_amount(nemkonto.min_balance)}.",
                    amount=needed - taken,
                )
            )
    pool += surplus - taken
    end = after - surplus + taken
    if end < 0:
        notices.append(
            Notice(
                "danger",
                "nemkonto_below_zero",
                f"The NemKonto would end at {format_amount(end)}. Choose which expenses or "
                f"savings goals to take {format_amount(-end)} from.",
                amount=-end,
            )
        )

    names = {ledger.expense.id: ledger.expense.name for ledger in state.ledgers}
    needing = sorted(
        (line for line in lines.values() if line.topup_needed),
        key=lambda line: (line.next_due or date.max, names[line.expense_id]),
    )
    for line in needing:
        line.topup = min(line.topup_needed, max(0, pool))
        line.funding = min(line.funding_requested, line.topup)
        pool -= line.topup
        if line.account_id in transfers:
            transfers[line.account_id].topups += line.topup
        name = names[line.expense_id]
        if line.funding:
            notices.append(
                Notice(
                    "info",
                    "funded",
                    f"{name} is filled with {format_amount(line.funding)} from General Savings, "
                    f"so it can save {format_amount(line.contribution)} a month from now on.",
                    line.funding,
                    line.expense_id,
                )
            )
        if line.topup and not line.topup_chosen and not line.funding_requested:
            message = f"{name} was {format_amount(line.topup_needed)} below zero. "
            message += f"{format_amount(line.topup)} is taken from General Savings."
            if line.amount_after:
                message += (
                    f" Its expected amount is raised from {format_amount(line.amount_before)}"
                    f" to {format_amount(line.amount_after)}."
                )
            notices.append(Notice("info", "fixed_topped_up", message, line.topup, line.expense_id))
        elif line.topup > line.funding:
            notices.append(
                Notice(
                    "info",
                    "topped_up",
                    f"{name} gets {format_amount(line.topup - line.funding)} from General "
                    "Savings, as chosen.",
                    line.topup - line.funding,
                    line.expense_id,
                )
            )
        if line.topup < line.topup_needed:
            missing = line.topup_needed - line.topup
            notices.append(
                Notice(
                    "warning",
                    "savings_cannot_cover_fixed",
                    f"General Savings cannot cover {name}. It gets "
                    f"{format_amount(missing)} less than needed.",
                    missing,
                    line.expense_id,
                )
            )
    kinds = {ledger.expense.id: ledger.expense.kind for ledger in state.ledgers}
    for line in lines.values():
        if (
            kinds[line.expense_id] is not Kind.FIXED
            and line.balance_before < 0
            and line.balance_before + line.topup < 0
        ):
            notices.append(
                Notice(
                    "info",
                    "variable_below_zero",
                    f"{names[line.expense_id]} is at {format_amount(line.balance_before)}. "
                    "Its amount varies, so adjust it if this keeps happening.",
                    -line.balance_before,
                    line.expense_id,
                )
            )

    transfers[savings.id].general_savings = pool - state.general_savings
    return ClosePlan(
        month=month,
        lines=lines,
        transfers=transfers,
        nemkonto_before=state.nemkonto,
        income=income,
        interest=interest,
        nemkonto_after_transfers=after,
        surplus=surplus,
        taken=taken,
        nemkonto_end=end,
        general_savings_before=state.general_savings,
        general_savings_after=pool,
        min_balance=nemkonto.min_balance,
        max_balance=nemkonto.max_balance,
        notices=notices,
        nemkonto_spent=nemkonto_spent,
    )


def apply_close(state: BudgetState, plan: ClosePlan) -> None:
    """Record ``plan`` in ``state`` and move on to the next month."""
    if plan.month != state.month:
        raise CloseError(f"The plan is for {plan.month}, but the next close is {state.month}")
    for ledger in state.ledgers:
        line = plan.lines.get(ledger.expense.id)
        if line is None:
            continue
        ledger.lines[plan.month] = line.to_line()
        if line.amount_after:
            ledger.expense = replace(ledger.expense, amount=line.amount_after)
    state.nemkonto = plan.nemkonto_end
    state.general_savings = plan.general_savings_after
    state.month = plan.month + 1
