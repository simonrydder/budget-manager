"""Load the budget from the database into the engine, and store what the engine decides."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.utils import timezone

from budget_manager import engine
from budget_manager.engine import (
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
    BalanceCorrection,
    BudgetSettings,
    ContributionLine,
    Decision,
    Expense,
    IncomeEntry,
    IncomeSource,
    InterestEntry,
    MonthClose,
    SpendingEntry,
    Transfer,
)


def ym(day: date) -> YearMonth:
    return YearMonth.of(day)


# --- Where are we in time? ------------------------------------------------------------------


def last_closed() -> MonthClose | None:
    return MonthClose.objects.filter(status=MonthClose.Status.CLOSED).order_by("-month").first()


def next_close_month() -> YearMonth:
    """The budget month whose month-end comes next."""
    last = last_closed()
    return last.budget_month + 1 if last else BudgetSettings.load().start


def draft_close(month: YearMonth | None = None) -> MonthClose | None:
    month = month or next_close_month()
    return MonthClose.objects.filter(
        month=month.first_day(), status=MonthClose.Status.DRAFT
    ).first()


def start_draft(month: YearMonth, user) -> MonthClose:
    close, _ = MonthClose.objects.get_or_create(
        month=month.first_day(), defaults={"started_by": user}
    )
    return close


def default_start_month(expense: Expense) -> YearMonth:
    return ym(expense.start_month) if expense.start_month else BudgetSettings.load().start


# --- From the database to the engine ------------------------------------------------------------


def engine_accounts(config: BudgetSettings) -> list[engine.Account]:
    result = []
    for account in Account.objects.all():
        role = Role(account.role)
        result.append(
            engine.Account(
                account.id,
                account.name,
                role,
                config.nemkonto_min if role is Role.NEMKONTO else 0,
                config.nemkonto_max if role is Role.NEMKONTO else 0,
            )
        )
    return result


def engine_expense(expense: Expense, start: YearMonth) -> engine.Expense:
    return engine.Expense(
        id=expense.id,
        name=expense.name,
        account_id=expense.account_id,
        kind=engine.Kind(expense.kind),
        amount=expense.amount,
        schedule=Schedule(expense.first_due, expense.interval_months, expense.end_date),
        start_month=ym(expense.start_month) if expense.start_month else start,
        starting_balance=expense.starting_balance,
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


def build_state() -> BudgetState:
    """The budget as it stands before the next month-end."""
    config = BudgetSettings.load()
    month = next_close_month()
    closed = MonthClose.objects.filter(status=MonthClose.Status.CLOSED)

    lines: dict[int, dict[YearMonth, Line]] = defaultdict(dict)
    for row in ContributionLine.objects.filter(close__status=MonthClose.Status.CLOSED).values(
        "expense_id", "close__month", "contribution", "expected_spend", "topup", "cover", "release"
    ):
        lines[row["expense_id"]][ym(row["close__month"])] = Line(
            contribution=row["contribution"],
            expected_spend=row["expected_spend"],
            topup=row["topup"],
            cover=row["cover"],
            release=row["release"],
        )
    spending: dict[int, dict[YearMonth, int]] = defaultdict(dict)
    for row in SpendingEntry.objects.values("expense_id", "month", "amount"):
        spending[row["expense_id"]][ym(row["month"])] = row["amount"]

    ledgers = [
        ExpenseLedger(
            engine_expense(expense, config.start),
            lines=lines[expense.id],
            spending=spending[expense.id],
        )
        for expense in Expense.objects.all()
    ]

    nemkonto = config.nemkonto_opening
    general_savings = config.general_savings_opening
    for close in closed:
        nemkonto += close.nemkonto_end - close.nemkonto_before
        general_savings += close.general_savings_after - close.general_savings_before
    corrections = BalanceCorrection.objects.filter(month__lt=month.first_day())
    for correction in corrections:
        if correction.target == BalanceCorrection.Target.NEMKONTO:
            nemkonto += correction.amount
        else:
            general_savings += correction.amount

    return BudgetState(
        accounts=engine_accounts(config),
        ledgers=ledgers,
        incomes=[engine_income(source) for source in IncomeSource.objects.all()],
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

    @property
    def income(self) -> int:
        return sum(self.income_entries.values())


def close_inputs(month: YearMonth) -> CloseInputs:
    inputs = CloseInputs(month)
    for entry in IncomeEntry.objects.filter(month=month.first_day()):
        inputs.income_entries[entry.source_id] = entry.amount
    for entry in InterestEntry.objects.filter(month=(month - 1).first_day()):
        inputs.interest[entry.account_id] = entry.amount
    close = draft_close(month)
    if close:
        for decision in close.decisions.all():
            target = {
                Decision.Type.COVER: inputs.covers,
                Decision.Type.RELEASE: inputs.releases,
                Decision.Type.TOPUP: inputs.topups,
            }[decision.kind]
            target[decision.expense_id] = decision.amount
    return inputs


def plan_next_close() -> tuple[BudgetState, ClosePlan, CloseInputs]:
    """Plan the next month-end from what has been entered so far (missing income counts as 0)."""
    state = build_state()
    inputs = close_inputs(state.month)
    plan = engine.plan_close(
        state,
        income=inputs.income,
        interest=inputs.interest,
        covers=inputs.covers,
        releases=inputs.releases,
        topups=inputs.topups,
    )
    return state, plan, inputs


def expected_income_entries(state: BudgetState, month: YearMonth) -> dict[int, int]:
    return {income.id: income.expected(month) for income in state.incomes}


def forecast(months: int | None = None, state: BudgetState | None = None) -> list[ForecastMonth]:
    """Forecast from now, using what has been entered for the next month-end and expected
    amounts for everything else."""
    state = state or build_state()
    months = months or BudgetSettings.load().forecast_months
    inputs = close_inputs(state.month)
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
    )


# --- Closing and reopening ----------------------------------------------------------------------


@transaction.atomic
def finalize_close(month: YearMonth, user) -> MonthClose:
    state, plan, _ = plan_next_close()
    if state.month != month:
        raise CloseError(f"The next month-end is {state.month.label}, not {month.label}.")
    if plan.shortfall:
        raise CloseError("Choose where to take the missing money from before closing.")

    close = start_draft(month, user)
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
    latest = last_closed()
    if latest is None or latest.pk != close.pk:
        raise CloseError("Only the most recent month-end can be reopened.")
    for line in close.lines.filter(amount_after__isnull=False).select_related("expense"):
        if line.expense.amount == line.amount_after:
            Expense.objects.filter(pk=line.expense_id).update(amount=line.amount_before)
    close.lines.all().delete()
    close.transfers.all().delete()
    MonthClose.objects.filter(
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


def spending_by_month(year: int) -> dict[int, dict[int, int]]:
    """``{expense_id: {month_number: amount}}`` for one calendar year."""
    result: dict[int, dict[int, int]] = defaultdict(dict)
    entries = SpendingEntry.objects.filter(month__year=year).values("expense_id", "month", "amount")
    for row in entries:
        result[row["expense_id"]][row["month"].month] = row["amount"]
    return result


def completed_spending_months(year: int) -> list[int]:
    """Month numbers in ``year`` whose spending has been entered at a month-end."""
    last = last_closed()
    if last is None:
        return []
    latest_complete = last.budget_month - 1  # spending of this month was entered at the last close
    first = BudgetSettings.load().start
    months = []
    for number in range(1, 13):
        month = YearMonth(year, number)
        if first <= month <= latest_complete:
            months.append(number)
    return months
