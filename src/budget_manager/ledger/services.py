"""Load the budget from the database into the engine, and store what the engine decides."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date

from django.db import transaction
from django.utils import timezone

from budget_manager import engine
from budget_manager.engine import (
    Adjustment,
    format_amount,
    BudgetState,
    ClosePlan,
    CloseError,
    ExpenseLedger,
    ForecastMonth,
    Line,
    MonthSchedule,
    Role,
    Schedule,
    YearMonth,
)
from budget_manager.ledger.models import (
    Account,
    Budget,
    ContributionLine,
    Decision,
    Expense,
    IncomeEntry,
    IncomeSource,
    InterestEntry,
    MonthClose,
    Move,
    SpendingEntry,
    Transfer,
)


def ym(day: date) -> YearMonth:
    return YearMonth.of(day)


# --- Where are we in time? ------------------------------------------------------------------


def last_closed(budget: Budget) -> MonthClose | None:
    return budget.closes.filter(status=MonthClose.Status.CLOSED).order_by("-month").first()


def next_close_month(budget: Budget) -> YearMonth:
    """The budget month whose month-end comes next."""
    last = last_closed(budget)
    return last.budget_month + 1 if last else budget.start


def draft_close(budget: Budget, month: YearMonth | None = None) -> MonthClose | None:
    month = month or next_close_month(budget)
    return budget.closes.filter(month=month.first_day(), status=MonthClose.Status.DRAFT).first()


def start_draft(budget: Budget, month: YearMonth, user) -> MonthClose:
    close, _ = MonthClose.objects.get_or_create(
        budget=budget, month=month.first_day(), defaults={"started_by": user}
    )
    return close


def budget_started(budget: Budget) -> bool:
    """True once the budget has been started or has had a month-end."""
    return budget.started_on is not None or last_closed(budget) is not None


# --- From the database to the engine ------------------------------------------------------------


def engine_accounts(budget: Budget) -> list[engine.Account]:
    result = []
    for account in budget.accounts.all():
        role = Role(account.role)
        result.append(
            engine.Account(
                account.id,
                account.name,
                role,
                budget.nemkonto_min if role is Role.NEMKONTO else 0,
                budget.nemkonto_max if role is Role.NEMKONTO else 0,
            )
        )
    return result


def engine_expense(
    expense: Expense, start: YearMonth, opening: YearMonth | None = None
) -> engine.Expense:
    return engine.Expense(
        id=expense.id,
        name=expense.name,
        account_id=expense.account_id,
        kind=engine.Kind(expense.kind),
        amount=expense.amount,
        schedule=Schedule(expense.first_due, expense.interval_months, expense.end_date),
        start_month=ym(expense.start_month) if expense.start_month else start,
        starting_balance=expense.starting_balance,
        opening_month=None if expense.start_month else opening,
    )


def engine_income(source: IncomeSource) -> engine.Income:
    return engine.Income(
        source.id,
        source.name,
        source.amount,
        MonthSchedule(
            ym(source.first_month),
            source.interval_months,
            ym(source.end_month) if source.end_month else None,
        ),
    )


def build_state(budget: Budget) -> BudgetState:
    """The budget as it stands before the next month-end."""
    month = next_close_month(budget)
    closed = budget.closes.filter(status=MonthClose.Status.CLOSED)

    lines: dict[int, dict[YearMonth, Line]] = defaultdict(dict)
    for row in ContributionLine.objects.filter(
        close__budget=budget, close__status=MonthClose.Status.CLOSED
    ).values(
        "expense_id",
        "close__month",
        "contribution",
        "expected_spend",
        "topup",
        "cover",
        "release",
        "funding",
    ):
        lines[row["expense_id"]][ym(row["close__month"])] = Line(
            contribution=row["contribution"],
            expected_spend=row["expected_spend"],
            topup=row["topup"],
            cover=row["cover"],
            release=row["release"],
            funding=row["funding"],
        )
    spending: dict[int, dict[YearMonth, int]] = defaultdict(dict)
    for row in SpendingEntry.objects.filter(expense__budget=budget).values(
        "expense_id", "month", "amount"
    ):
        spending[row["expense_id"]][ym(row["month"])] = row["amount"]

    adjustments: dict[int, list[Adjustment]] = defaultdict(list)
    moved_to_general_savings = 0
    for move in budget.moves.filter(done=True):
        moved_to_general_savings += move.to_general_savings
        if move.expense_id:
            adjustments[move.expense_id].append(
                Adjustment(ym(move.month), move.to_expense, planned=move.kind == Move.Type.FUND)
            )

    ledgers = [
        ExpenseLedger(
            engine_expense(expense, budget.start, budget.opening),
            lines=lines[expense.id],
            spending=spending[expense.id],
            adjustments=adjustments[expense.id],
        )
        for expense in budget.expenses.all()
    ]

    nemkonto = budget.nemkonto_opening
    general_savings = budget.general_savings_opening + moved_to_general_savings
    for close in closed:
        nemkonto += close.nemkonto_end - close.nemkonto_before
        general_savings += close.general_savings_after - close.general_savings_before
    corrections = budget.corrections.filter(month__lt=month.first_day())
    for correction in corrections:
        if correction.target == correction.Target.NEMKONTO:
            nemkonto += correction.amount
        else:
            general_savings += correction.amount

    return BudgetState(
        accounts=engine_accounts(budget),
        ledgers=ledgers,
        incomes=[engine_income(source) for source in budget.incomes.all()],
        month=month,
        nemkonto=nemkonto,
        general_savings=general_savings,
    )


# --- Month-end inputs ---------------------------------------------------------------------------


@dataclass
class CloseInputs:
    month: YearMonth
    income_entries: dict[int, int] = field(default_factory=dict)
    interest: dict[int, int] = field(default_factory=dict)
    covers: dict[int, int] = field(default_factory=dict)
    releases: dict[int, int] = field(default_factory=dict)
    topups: dict[int, int] = field(default_factory=dict)
    funding: dict[int, int] = field(default_factory=dict)

    @property
    def income(self) -> int:
        return sum(self.income_entries.values())


def close_inputs(budget: Budget, month: YearMonth) -> CloseInputs:
    inputs = CloseInputs(month)
    for entry in IncomeEntry.objects.filter(source__budget=budget, month=month.first_day()):
        inputs.income_entries[entry.source_id] = entry.amount
    interest = InterestEntry.objects.filter(account__budget=budget, month=(month - 1).first_day())
    for entry in interest:
        inputs.interest[entry.account_id] = entry.amount
    close = draft_close(budget, month)
    if close:
        for decision in close.decisions.all():
            target = {
                Decision.Type.COVER: inputs.covers,
                Decision.Type.RELEASE: inputs.releases,
                Decision.Type.TOPUP: inputs.topups,
                Decision.Type.FUND: inputs.funding,
            }[decision.kind]
            target[decision.expense_id] = decision.amount
    return inputs


def plan_next_close(budget: Budget) -> tuple[BudgetState, ClosePlan, CloseInputs]:
    """Plan the next month-end from what has been entered so far (missing income counts as 0)."""
    state = build_state(budget)
    inputs = close_inputs(budget, state.month)
    plan = engine.plan_close(
        state,
        income=inputs.income,
        interest=inputs.interest,
        covers=inputs.covers,
        releases=inputs.releases,
        topups=inputs.topups,
        funding=inputs.funding,
    )
    return state, plan, inputs


def expected_income_entries(state: BudgetState, month: YearMonth) -> dict[int, int]:
    return {income.id: income.expected(month) for income in state.incomes}


def forecast(
    budget: Budget, months: int | None = None, state: BudgetState | None = None
) -> list[ForecastMonth]:
    """Forecast from now, using what has been entered for the next month-end and expected
    amounts for everything else."""
    state = state or build_state(budget)
    months = months or budget.forecast_months
    inputs = close_inputs(budget, state.month)
    expected = expected_income_entries(state, state.month)
    income = sum({**expected, **inputs.income_entries}.values())
    return engine.run_forecast(
        state,
        months,
        income={state.month: income},
        interest={state.month: inputs.interest},
        covers={state.month: inputs.covers},
        releases={state.month: inputs.releases},
        topups={state.month: inputs.topups},
        funding={state.month: inputs.funding},
    )


# --- Closing and reopening ----------------------------------------------------------------------


@transaction.atomic
def finalize_close(budget: Budget, month: YearMonth, user) -> MonthClose:
    state, plan, _ = plan_next_close(budget)
    if state.month != month:
        raise CloseError(f"The next month-end is {state.month.label}, not {month.label}.")
    if plan.shortfall:
        raise CloseError("Choose where to take the missing money from before closing.")
    if any(item.move for item in balancing(budget, date.today(), state).moves):
        raise CloseError(
            "Some money is waiting to be moved to or from General Savings. Make those transfers "
            "(or cancel them) under Balance first."
        )

    close = start_draft(budget, month, user)
    done = set(close.done_accounts or [])
    close.status = MonthClose.Status.CLOSED
    close.closed_by = user
    close.closed_at = timezone.now()
    close.nemkonto_before = plan.nemkonto_before
    close.income = plan.income
    close.interest = plan.interest_total
    close.contributions = plan.contributions_total
    close.nemkonto_after_transfers = plan.nemkonto_after_transfers
    close.surplus = plan.surplus
    close.taken = plan.taken
    close.nemkonto_end = plan.nemkonto_end
    close.general_savings_before = plan.general_savings_before
    close.general_savings_after = plan.general_savings_after
    close.notices = [
        {"level": n.level, "code": n.code, "message": n.message, "amount": n.amount}
        for n in plan.notices
    ]
    close.save()

    ContributionLine.objects.bulk_create(
        ContributionLine(
            close=close,
            expense_id=line.expense_id,
            contribution=line.contribution,
            expected_spend=line.expected_spend,
            topup=line.topup,
            cover=line.cover,
            release=line.release,
            funding=line.funding,
            balance_before=line.balance_before,
            planned_before=line.planned_before,
            amount_before=line.amount_before,
            amount_after=line.amount_after,
        )
        for line in plan.lines.values()
    )
    now = timezone.now()
    Transfer.objects.bulk_create(
        Transfer(
            close=close,
            account_id=transfer.account_id,
            amount=transfer.amount,
            contributions=transfer.contributions,
            interest=transfer.interest,
            topups=transfer.topups,
            covers=transfer.covers,
            releases=transfer.releases,
            general_savings=transfer.general_savings,
            done=transfer.account_id in done,
            done_by=user if transfer.account_id in done else None,
            done_at=now if transfer.account_id in done else None,
        )
        for transfer in plan.transfers.values()
        if transfer.amount
    )
    for line in plan.lines.values():
        if line.amount_after:
            Expense.objects.filter(pk=line.expense_id).update(amount=line.amount_after)
    return close


@transaction.atomic
def reopen_close(close: MonthClose) -> None:
    budget = close.budget
    latest = last_closed(budget)
    if latest is None or latest.pk != close.pk:
        raise CloseError("Only the most recent month-end can be reopened.")
    for line in close.lines.filter(amount_after__isnull=False).select_related("expense"):
        if line.expense.amount == line.amount_after:
            Expense.objects.filter(pk=line.expense_id).update(amount=line.amount_before)
    close.lines.all().delete()
    close.transfers.all().delete()
    # Moves made after this month-end now come before it.
    budget.moves.filter(done=True, month__gt=close.month).update(month=close.month)
    budget.closes.filter(
        month=(close.budget_month + 1).first_day(), status=MonthClose.Status.DRAFT
    ).delete()
    close.status = MonthClose.Status.DRAFT
    close.closed_at = None
    close.closed_by = None
    close.step = 4
    close.save()


# --- Reading helpers ----------------------------------------------------------------------------


def expense_balances(state: BudgetState) -> dict[int, int]:
    return state.current_expense_balances()


def spending_by_month(budget: Budget, year: int) -> dict[int, dict[int, int]]:
    """``{expense_id: {month_number: amount}}`` for one calendar year."""
    result: dict[int, dict[int, int]] = defaultdict(dict)
    entries = SpendingEntry.objects.filter(expense__budget=budget, month__year=year).values(
        "expense_id", "month", "amount"
    )
    for row in entries:
        result[row["expense_id"]][row["month"].month] = row["amount"]
    return result


def completed_spending_months(budget: Budget, year: int) -> list[int]:
    """Month numbers in ``year`` whose spending has been entered at a month-end."""
    last = last_closed(budget)
    if last is None:
        return []
    latest_complete = last.budget_month - 1  # spending of this month was entered at the last close
    first = budget.opening
    months = []
    for number in range(1, 13):
        month = YearMonth(year, number)
        if first <= month <= latest_complete:
            months.append(number)
    return months


# --- Is the budget balanced? --------------------------------------------------------------------


@dataclass
class MonthlyBalance:
    """Average expected income against the average set aside each month."""

    income: int
    expenses: int
    general_savings: int
    month: YearMonth  # first month the averages apply to

    @property
    def difference(self) -> int:
        return self.income - self.expenses

    @property
    def shortfall(self) -> int:
        return max(0, -self.difference)

    @property
    def months_covered(self) -> int | None:
        """How many months General Savings can cover the shortfall (None: no shortfall)."""
        if not self.shortfall:
            return None
        return max(0, self.general_savings) // self.shortfall

    @property
    def runs_out(self) -> YearMonth | None:
        """The first month General Savings cannot cover in full."""
        covered = self.months_covered
        return None if covered is None else self.month + covered

    def warning(self) -> str | None:
        if not self.shortfall:
            return None
        text = (
            f"Your expenses now need {format_amount(self.expenses)} a month on average, "
            f"{format_amount(self.shortfall)} more than your expected income of "
            f"{format_amount(self.income)}. "
        )
        if self.months_covered == 0:
            return text + "General Savings cannot cover that, so the NemKonto will run short."
        return text + (
            f"About {format_amount(self.shortfall)} is taken from General Savings each month. "
            f"Its {format_amount(self.general_savings)} covers {self.months_covered} "
            f"month{'s' if self.months_covered != 1 else ''} and runs out in "
            f"{self.runs_out.label}."
        )


def monthly_balance(budget: Budget, state: BudgetState | None = None) -> MonthlyBalance:
    """Average income and set-aside per month from the next month-end on.

    A repeating expense counts as its amount divided by its interval; a one-off savings goal
    counts as what is still missing spread over the months left. Ended expenses and incomes
    count as 0.
    """
    state = state or build_state(budget)
    month = state.month
    expenses = 0
    for ledger in state.ledgers:
        expense = ledger.expense
        due = expense.schedule.next_due(month)
        if due is None:
            continue
        interval = expense.schedule.interval_months
        if interval:
            expenses += expense.amount // interval
        else:
            missing = max(0, expense.amount - ledger.planned_balance_before(month))
            expenses += missing // (month.months_until(YearMonth.of(due)) + 1)
    income = 0
    for source in state.incomes:
        schedule = source.schedule
        if schedule.interval_months and (schedule.end_month is None or schedule.end_month >= month):
            income += source.amount // schedule.interval_months
    return MonthlyBalance(income, expenses, state.general_savings, month)


# --- Starting the budget ------------------------------------------------------------------------


@dataclass
class StartRow:
    expense: Expense
    suggested: int | None  # None: one-off goal without a steady amount
    set_aside: int  # at the start of the opening month
    spent: int  # in the opening month so far
    due: date | None  # due date inside the opening month

    @property
    def now(self) -> int:
        return self.set_aside - self.spent


@dataclass
class StartAccount:
    account: Account
    bank: int | None
    expected: int

    @property
    def difference(self) -> int | None:
        return None if self.bank is None else self.bank - self.expected


@dataclass
class StartPlan:
    today: date
    opening: YearMonth
    rows: list[StartRow]
    accounts: list[StartAccount]

    @property
    def start(self) -> YearMonth:
        return self.opening + 1

    @property
    def complete(self) -> bool:
        return all(item.bank is not None for item in self.accounts)

    @property
    def nemkonto(self) -> int | None:
        return next(a.bank for a in self.accounts if a.account.is_nemkonto)

    @property
    def general_savings(self) -> int | None:
        """What is left on the accounts once every expense has what it should have."""
        if not self.complete:
            return None
        return sum(a.difference for a in self.accounts if not a.account.is_nemkonto)

    @property
    def moves(self) -> list[tuple[str, str, int]]:
        """Bank transfers that put each account's surplus into (or shortage from) Savings."""
        savings = next(a.account for a in self.accounts if a.account.holds_general_savings)
        moves = []
        for item in self.accounts:
            account = item.account
            if account.is_nemkonto or account.holds_general_savings or not item.difference:
                continue
            if item.difference > 0:
                moves.append((account.name, savings.name, item.difference))
            else:
                moves.append((savings.name, account.name, -item.difference))
        return moves


def plan_start(
    budget: Budget,
    today: date,
    bank: dict[int, int | None] | None = None,
    set_aside: dict[int, int | None] | None = None,
    spent: dict[int, int | None] | None = None,
) -> StartPlan:
    """Balances when starting the budget today: what each expense should have (so its monthly
    contribution stays steady) and how the accounts must be evened out via General Savings."""
    bank, set_aside, spent = bank or {}, set_aside or {}, spent or {}
    opening = YearMonth.of(today)
    # Starting again in the same month begins from what was chosen the first time.
    again = budget.started_on is not None and budget.opening_month == opening.first_day()
    entered = {}
    if again:
        entered = dict(
            SpendingEntry.objects.filter(
                expense__budget=budget, month=opening.first_day()
            ).values_list("expense_id", "amount")
        )
    rows = []
    for expense in budget.expenses.select_related("account").order_by(
        "account__sort_order", "sort_order", "name"
    ):
        model = replace(
            engine_expense(expense, opening + 1), start_month=opening + 1, opening_month=opening
        )
        suggested = model.suggested_starting_balance()
        due = model.schedule.due_in(opening)
        default_spent = expense.amount if expense.is_fixed and due and due <= today else 0
        chosen = set_aside.get(expense.id)
        if again and expense.start_month is None:
            default_spent = entered.get(expense.id, 0)
            if chosen is None:
                chosen = expense.starting_balance
        if chosen is None:
            chosen = suggested if suggested is not None else expense.starting_balance
        used = spent.get(expense.id)
        rows.append(
            StartRow(expense, suggested, chosen, default_spent if used is None else used, due)
        )
    accounts = []
    for account in budget.accounts.all():
        expected = sum(row.now for row in rows if row.expense.account_id == account.id)
        accounts.append(StartAccount(account, bank.get(account.id), expected))
    return StartPlan(today, opening, rows, accounts)


@transaction.atomic
def apply_start(budget: Budget, plan: StartPlan, user) -> None:
    if last_closed(budget) is not None:
        raise CloseError("The budget has already had a month-end, so it cannot be started again.")
    if not plan.complete:
        raise CloseError("Enter the balance of every account.")
    if plan.general_savings < 0:
        raise CloseError(
            f"The accounts hold {format_amount(-plan.general_savings)} less than the expenses "
            "should have. Lower some set-aside amounts or check the balances."
        )
    budget.opening_month = plan.opening.first_day()
    budget.start_month = plan.start.first_day()
    budget.started_on = plan.today
    budget.nemkonto_opening = plan.nemkonto
    budget.general_savings_opening = plan.general_savings
    budget.start_transfers = [
        {"source": source, "target": target, "amount": amount}
        for source, target, amount in plan.moves
    ]
    budget.save()
    for item in plan.accounts:
        Account.objects.filter(pk=item.account.pk).update(start_balance=item.bank)
    SpendingEntry.objects.filter(expense__budget=budget, month=plan.opening.first_day()).delete()
    budget.moves.filter(done=True).delete()  # already part of today's bank balances
    for row in plan.rows:
        Expense.objects.filter(pk=row.expense.pk).update(
            starting_balance=row.set_aside, start_month=None
        )
        if row.spent:
            SpendingEntry.objects.create(
                expense=row.expense,
                month=plan.opening.first_day(),
                amount=row.spent,
                updated_by=user,
            )
    budget.closes.filter(status=MonthClose.Status.DRAFT).exclude(
        month=plan.start.first_day()
    ).delete()


# --- Moving money between month-ends ------------------------------------------------------------


@dataclass
class PendingMove:
    """A move waiting for its bank transfer. ``move`` is None for money left on an ended
    expense, which is suggested automatically."""

    kind: str
    amount: int
    account: Account
    expense: Expense | None = None
    move: Move | None = None
    note: str = ""

    @property
    def to_expense(self) -> int:
        return Move(kind=self.kind, amount=self.amount).to_expense

    @property
    def to_general_savings(self) -> int:
        return Move(kind=self.kind, amount=self.amount).to_general_savings

    @property
    def label(self) -> str:
        return Move.Type(self.kind).label


@dataclass
class BankMove:
    source: Account
    target: Account
    amount: int


@dataclass
class Balancing:
    moves: list[PendingMove]
    savings: Account
    general_savings: int  # before the moves
    stale: list[Move] = field(default_factory=list)  # waiting moves with nothing left to move

    @property
    def general_savings_after(self) -> int:
        return self.general_savings + sum(item.to_general_savings for item in self.moves)

    @property
    def bank_moves(self) -> list[BankMove]:
        """One transfer per account to or from the account holding General Savings."""
        net: dict[int, int] = defaultdict(int)
        accounts = {}
        for item in self.moves:
            if item.account.pk == self.savings.pk:
                continue
            accounts[item.account.pk] = item.account
            net[item.account.pk] += item.to_expense if item.expense else -item.amount
        result = []
        for account_id, amount in net.items():
            account = accounts[account_id]
            if amount > 0:
                result.append(BankMove(self.savings, account, amount))
            elif amount < 0:
                result.append(BankMove(account, self.savings, -amount))
        return sorted(result, key=lambda move: (move.source.sort_order, move.target.sort_order))


def fund_amount(ledger: ExpenseLedger, month: YearMonth) -> int:
    """What fills a new expense up to the steady path at the month-end for ``month``."""
    suggested = ledger.expense.suggested_starting_balance()
    if suggested is None:
        return 0
    return max(0, suggested - ledger.planned_balance_before(month))


def leftover(ledger: ExpenseLedger, month: YearMonth, today: date) -> int:
    """Money left on an ended expense once all its payments have been entered."""
    expense = ledger.expense
    end = expense.schedule.end_date
    if end is None or end >= today:
        return 0
    first_open = max(month - 1, expense.opening).first_day()
    if expense.schedule.next_due_from(first_open) is not None:
        return 0  # a last payment is still to be entered at the month-end
    return max(0, ledger.balance_end_of(month - 1))


def balancing(budget: Budget, today: date, state: BudgetState | None = None) -> Balancing:
    """Moves waiting for their bank transfers, and the transfers that settle them."""
    state = state or build_state(budget)
    expenses = {expense.pk: expense for expense in budget.expenses.select_related("account")}
    savings = budget.accounts.get(role=Role.SAVINGS.value)
    items = []
    stored = budget.moves.filter(done=False).select_related("account").order_by("created_at")
    waiting = set()
    for move in stored:
        expense = expenses.get(move.expense_id)
        amount = move.amount
        if expense:
            waiting.add(expense.pk)
            ledger = state.ledger(expense.pk)
            if move.kind == Move.Type.FUND and ledger.expense.start_month == state.month:
                amount = fund_amount(ledger, state.month)
        account = expense.account if expense else move.account
        items.append(PendingMove(move.kind, amount, account, expense, move, move.note))
    for ledger in state.ledgers:
        expense = expenses[ledger.expense.id]
        if expense.pk in waiting:
            continue
        amount = leftover(ledger, state.month, today)
        if amount:
            items.append(
                PendingMove(Move.Type.RELEASE, amount, expense.account, expense, note="Ended")
            )
    return Balancing(
        [item for item in items if item.amount],
        savings,
        state.general_savings,
        [item.move for item in items if item.move and not item.amount],
    )


@transaction.atomic
def make_moves(budget: Budget, today: date, user) -> Balancing:
    """Record that the bank transfers for every waiting move have been made."""
    if not budget_started(budget):
        raise CloseError("Start the budget before moving money.")
    plan = balancing(budget, today)
    if not plan.moves:
        raise CloseError("Nothing is waiting to be moved.")
    if plan.general_savings_after < 0:
        raise CloseError(
            f"General Savings only has {format_amount(plan.general_savings)}, which is "
            f"{format_amount(-plan.general_savings_after)} too little for these moves."
        )
    month = next_close_month(budget).first_day()
    now = timezone.now()
    for item in plan.moves:
        move = item.move or Move(
            budget=budget, kind=item.kind, expense=item.expense, note=item.note, created_by=user
        )
        move.amount = item.amount
        move.account = item.account
        move.done = True
        move.month = month
        move.done_by = user
        move.done_at = now
        move.save()
    for move in plan.stale:
        move.delete()
    return plan


def undo_move(move: Move) -> None:
    """Put a made move back on the waiting list, while no month-end has happened since."""
    if not move.done or move.month != next_close_month(move.budget).first_day():
        raise CloseError("A month-end has happened since, so this move can no longer be undone.")
    move.done = False
    move.month = None
    move.done_by = None
    move.done_at = None
    move.save()


# --- The setup: what the budget costs a month, and how its first month-end will look ------------


def setup_start_month(budget: Budget, today: date) -> YearMonth:
    """The first budget month when starting today (its transfers are made at this month's end)."""
    return budget.start if budget.started_on else YearMonth.of(today) + 1


def monthly_need(expense: Expense, start: YearMonth, today: date) -> int:
    """What an expense costs on average a month: a repeating one its amount divided by its
    interval, a one-off goal its amount spread over the months until it is due."""
    if expense.is_ended(today):
        return 0
    if expense.interval_months:
        return expense.amount // expense.interval_months
    due = YearMonth.of(expense.first_due)
    if due < start:
        return 0  # due before the first transfer: paid from what is already set aside
    return expense.amount // (start.months_until(due) + 1)


@dataclass
class SummaryGroup:
    name: str
    rows: list[tuple[Expense, int]]

    @property
    def monthly(self) -> int:
        return sum(monthly for _, monthly in self.rows)


@dataclass
class SetupSummary:
    groups: list[SummaryGroup]
    accounts: list[tuple[Account, int]]
    income: int  # expected income a month

    @property
    def monthly(self) -> int:
        return sum(group.monthly for group in self.groups)

    @property
    def left_over(self) -> int:
        return self.income - self.monthly

    def share(self, amount: int) -> float:
        return round(amount * 100 / self.monthly, 1) if self.monthly else 0


def setup_summary(budget: Budget, today: date) -> SetupSummary:
    """Expenses per category and per account with what they cost a month, and the income."""
    start = setup_start_month(budget, today)
    expenses = list(budget.expenses.select_related("category", "account"))
    needs = {expense.pk: monthly_need(expense, start, today) for expense in expenses}
    groups = []
    for category in [*budget.categories.all(), None]:
        rows = [
            (expense, needs[expense.pk])
            for expense in expenses
            if expense.category_id == (category.pk if category else None)
            and not expense.is_ended(today)
        ]
        if rows:
            groups.append(SummaryGroup(category.name if category else "Uncategorised", rows))
    groups.sort(key=lambda group: -group.monthly)
    accounts = [
        (account, sum(needs[e.pk] for e in expenses if e.account_id == account.pk))
        for account in budget.accounts.exclude(role=Role.NEMKONTO.value)
    ]
    income = 0
    for source in budget.incomes.all():
        ends = source.end_month and YearMonth.of(source.end_month) < start
        if source.interval_months and not ends:
            income += source.amount // source.interval_months
    return SetupSummary(groups, accounts, income)


def preview_first_close(budget: Budget, plan: StartPlan) -> ClosePlan | None:
    """The first month-end as it will look if the budget is started with ``plan``, using the
    expected income. None until the plan is complete."""
    if not plan.complete or plan.general_savings < 0:
        return None
    ledgers = []
    for row in plan.rows:
        model = replace(
            engine_expense(row.expense, plan.start),
            start_month=plan.start,
            opening_month=plan.opening,
            starting_balance=row.set_aside,
        )
        spending = {plan.opening: row.spent} if row.spent else {}
        ledgers.append(ExpenseLedger(model, spending=spending))
    state = BudgetState(
        accounts=engine_accounts(budget),
        ledgers=ledgers,
        incomes=[engine_income(source) for source in budget.incomes.all()],
        month=plan.start,
        nemkonto=plan.nemkonto,
        general_savings=plan.general_savings,
    )
    return engine.plan_close(state, income=state.expected_income(plan.start))
