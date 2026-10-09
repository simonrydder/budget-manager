"""The month-end checklist: spending, interest, income, transfers, then check and close."""

from __future__ import annotations

from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from budget_manager.engine import CloseError, YearMonth, format_amount
from budget_manager.ledger import services
from budget_manager.ledger.models import (
    Account,
    BalanceCorrection,
    Decision,
    IncomeEntry,
    InterestEntry,
    MonthClose,
    SpendingEntry,
    Transfer,
)
from budget_manager.ledger.views.common import parse_month, read_amounts, save_entries, today

STEPS = [
    (1, "spending", "Spending"),
    (2, "interest", "Interest"),
    (3, "income", "Income"),
    (4, "transfers", "Transfers"),
    (5, "check", "Check & close"),
]


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def month_end(request):
    """Continue where the checklist was left, or start it."""
    budget = request.budget
    if not services.budget_started(budget):
        messages.info(request, "Set up the budget first. The month-ends start after that.")
        return redirect("start")
    month = services.next_close_month(budget)
    draft = services.draft_close(budget, month)
    step = draft.step if draft else 1
    name = next(slug for number, slug, _ in STEPS if number == step)
    return redirect(f"month-end-{name}", month=str(month))


def _guard(request, text: str):
    """The month in the URL must be the next month-end. Returns (month, close) or a redirect."""
    budget = request.budget
    month = parse_month(text)
    if not services.budget_started(budget):
        return redirect("month-end")
    expected = services.next_close_month(budget)
    if month != expected:
        close = budget.closes.filter(month=month.first_day()).first()
        if close and close.is_closed:
            return redirect("close-detail", month=str(month))
        messages.info(request, f"The next month-end is on {(expected - 1).last_day():%d %B %Y}.")
        return redirect("month-end")
    close = services.start_draft(budget, month, request.user)
    return month, close


def _context(month: YearMonth, close: MonthClose, current: int, **extra):
    previous = month - 1
    labels = {
        1: f"{previous.name} spending",
        2: f"{previous.name} interest",
        3: f"{month.name} income",
        4: "Transfers",
        5: "Check & close",
    }
    steps = [
        {
            "number": number,
            "slug": slug,
            "label": labels[number],
            "url": reverse(f"month-end-{slug}", kwargs={"month": str(month)}),
            "done": number < close.step and number != current,
            "current": number == current,
            "reachable": number <= close.step,
        }
        for number, slug, _ in STEPS
    ]
    return {
        "month": month,
        "previous": previous,
        "close": close,
        "steps": steps,
        "current_step": current,
        "transfer_day": previous.last_day(),
        **extra,
    }


def _advance(close: MonthClose, to_step: int) -> None:
    if close.step < to_step:
        close.step = to_step
        close.save(update_fields=["step"])


def _next(request, month: YearMonth, slug: str):
    if "stay" in request.POST:
        messages.success(request, "Saved.")
        return redirect(f"month-end-{slug}", month=str(month))
    following = {"spending": "interest", "interest": "income", "income": "transfers"}
    return redirect(f"month-end-{following[slug]}", month=str(month))


def spending(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, close = guarded
    budget = request.budget
    previous = month - 1
    state = services.build_state(budget)
    first_close = previous < budget.opening
    opening_month = previous < budget.start

    entries = {
        entry.expense_id: entry.amount
        for entry in SpendingEntry.objects.filter(
            expense__budget=budget, month=previous.first_day()
        )
    }
    expenses = list(budget.expenses.select_related("account", "category"))
    ledgers = {ledger.expense.id: ledger for ledger in state.ledgers}
    rows = []
    for expense in expenses:
        ledger = ledgers[expense.id]
        ended = expense.end_date and expense.end_date < previous.first_day()
        if first_close or (ended and expense.id not in entries):
            continue
        line = ledger.lines.get(previous)
        paid = ledger.expense.schedule.due_in(previous)
        due_amount = ledger.expense.amount_on(paid) if paid else 0
        expected = line.expected_spend if line else due_amount
        rows.append(
            {
                "expense": expense,
                "due": ledger.expense.schedule.due_in(previous),
                "expected": expected,
                "value": entries.get(expense.id),
                "base": ledger.balance_after_close(previous),
                "after": ledger.balance_after_close(previous) - (entries.get(expense.id) or 0),
            }
        )

    errors = {}
    nemkonto = {
        "start": state.nemkonto,
        "expected": state.everyday_spending,
        "value": close.nemkonto_spent,
        "raw": None,
        "error": None,
    }
    if request.method == "POST" and not first_close:
        values, errors = read_amounts(request.POST, "spent-", [row["expense"].id for row in rows])
        spent, nemkonto_error = read_amounts(request.POST, "nemkonto-", ["spent"])
        if not errors and not nemkonto_error:
            with transaction.atomic():
                save_entries(SpendingEntry, "expense", previous.first_day(), values, request.user)
                close.nemkonto_spent = spent["spent"]
                close.save(update_fields=["nemkonto_spent"])
            _advance(close, 2)
            return _next(request, month, "spending")
        for row in rows:
            row["raw"] = request.POST.get(f"spent-{row['expense'].id}", "")
            row["error"] = errors.get(row["expense"].id)
        nemkonto["raw"] = request.POST.get("nemkonto-spent", "")
        nemkonto["error"] = nemkonto_error.get("spent")
        errors = errors or nemkonto_error
    elif request.method == "POST":
        _advance(close, 2)
        return _next(request, month, "spending")

    groups: OrderedDict[Account, list] = OrderedDict()
    for account in budget.accounts.exclude(role="nemkonto"):
        groups[account] = []
    for row in sorted(rows, key=lambda r: (r["due"] is None, r["expense"].name.lower())):
        groups.setdefault(row["expense"].account, []).append(row)
    days_early = (previous.last_day() - today()).days
    context = _context(
        month,
        close,
        1,
        days_early=days_early if days_early > 3 else 0,
        groups=[(account, items) for account, items in groups.items() if items],
        first_close=first_close,
        opening_month=opening_month,
        started_on=budget.started_on,
        entered=len(entries),
        total=len(rows),
        errors=errors,
        nemkonto=nemkonto,
    )
    return render(request, "ledger/month_end/spending.html", context)


def interest(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, close = guarded
    budget = request.budget
    previous = month - 1
    accounts = list(budget.accounts.all())
    entries = {
        entry.account_id: entry.amount
        for entry in InterestEntry.objects.filter(
            account__budget=budget, month=previous.first_day()
        )
    }
    errors = {}
    if request.method == "POST":
        values, errors = read_amounts(request.POST, "interest-", [a.id for a in accounts])
        if not errors:
            values = {key: (value or None) for key, value in values.items()}
            save_entries(InterestEntry, "account", previous.first_day(), values, request.user)
            _advance(close, 3)
            return _next(request, month, "interest")
    rows = [
        {
            "account": account,
            "value": entries.get(account.id),
            "raw": request.POST.get(f"interest-{account.id}") if errors else None,
            "error": errors.get(account.id),
        }
        for account in accounts
    ]
    return render(request, "ledger/month_end/interest.html", _context(month, close, 2, rows=rows))


def income(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, close = guarded
    budget = request.budget
    state = services.build_state(budget)
    expected = services.expected_income_entries(state, month)
    entries = {
        entry.source_id: entry.amount
        for entry in IncomeEntry.objects.filter(source__budget=budget, month=month.first_day())
    }
    show_all = request.GET.get("all") == "1"
    sources = [
        source
        for source in budget.incomes.all()
        if show_all or expected.get(source.id) or source.id in entries
    ]
    errors = {}
    if request.method == "POST":
        values, errors = read_amounts(request.POST, "income-", [s.id for s in sources])
        if not errors:
            save_entries(IncomeEntry, "source", month.first_day(), values, request.user)
            _advance(close, 4)
            return _next(request, month, "income")
    rows = [
        {
            "source": source,
            "expected": expected.get(source.id, 0),
            "value": entries.get(source.id),
            "raw": request.POST.get(f"income-{source.id}") if errors else None,
            "error": errors.get(source.id),
        }
        for source in sources
    ]
    hidden = budget.incomes.count() - len(sources)
    context = _context(month, close, 3, rows=rows, hidden=hidden, show_all=show_all)
    return render(request, "ledger/month_end/income.html", context)


def _plan_context(budget, month: YearMonth, close: MonthClose):
    state, plan, inputs = services.plan_next_close(budget)
    accounts = {account.id: account for account in budget.accounts.all()}
    expenses = {expense.id: expense for expense in budget.expenses.select_related("account")}
    nemkonto = next(a for a in accounts.values() if a.is_nemkonto)
    done = set(close.done_accounts or [])
    transfers = [
        {"account": accounts[t.account_id], "plan": t, "done": t.account_id in done}
        for t in plan.transfers.values()
        if t.amount
    ]
    lines = sorted(
        (
            {"expense": expenses[line.expense_id], "line": line}
            for line in plan.lines.values()
            if line.contribution or line.topup or line.cover or line.release
        ),
        key=lambda item: (item["expense"].account.sort_order, item["expense"].name.lower()),
    )
    expected = services.expected_income_entries(state, month)
    missing = [
        source
        for source in budget.incomes.all()
        if expected.get(source.id) and source.id not in inputs.income_entries
    ]
    balances_after = {account_id: 0 for account_id in accounts}
    for line in plan.lines.values():
        balances_after[line.account_id] += line.balance_after
    balances_after[nemkonto.id] += plan.nemkonto_end
    balances_after[state.savings_account.id] += plan.general_savings_after
    # Corrections recorded after making this month's transfers apply from the next month-end,
    # but they are part of what the bank shows now.
    for item in budget.corrections.filter(month=month.first_day()):
        if item.target == BalanceCorrection.Target.NEMKONTO:
            balances_after[nemkonto.id] += item.amount
        else:
            balances_after[state.savings_account.id] += item.amount
    return {
        "state": state,
        "plan": plan,
        "inputs": inputs,
        "waiting_moves": [
            item for item in services.balancing(budget, today(), state).moves if item.move
        ],
        "transfers": transfers,
        "lines": lines,
        "missing_income": missing,
        "nemkonto_missing": inputs.nemkonto_spent is None and month - 1 >= budget.opening,
        "nemkonto": nemkonto,
        "savings_account": accounts[state.savings_account.id],
        "balances_after": [
            {"account": account, "balance": balances_after[account.id]}
            for account in accounts.values()
        ],
        "open_count": sum(1 for t in transfers if not t["done"]),
    }


def transfers(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, close = guarded
    budget = request.budget
    context = _plan_context(budget, month, close)
    plan = context["plan"]

    cover_errors = {}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "tick":
            account = get_object_or_404(
                Account, pk=_int(request.POST.get("account")), budget=budget
            )
            account_id = account.id
            done = set(close.done_accounts or [])
            done.symmetric_difference_update({account_id})
            close.done_accounts = sorted(done)
            close.save(update_fields=["done_accounts"])
            return redirect("month-end-transfers", month=str(month))
        if action == "covers":
            ids = [line.expense_id for line in plan.lines.values()]
            values, cover_errors = read_amounts(request.POST, "cover-", ids)
            if not cover_errors:
                available = {
                    line.expense_id: max(0, line.balance_before) + line.contribution - line.release
                    for line in plan.lines.values()
                }
                for expense_id, amount in values.items():
                    if amount and not 0 < amount <= available[expense_id]:
                        cover_errors[expense_id] = (
                            f"Enter up to {format_amount(available[expense_id])}."
                        )
            if not cover_errors:
                with transaction.atomic():
                    close.decisions.filter(kind=Decision.Type.COVER).delete()
                    Decision.objects.bulk_create(
                        Decision(
                            close=close, expense_id=eid, kind=Decision.Type.COVER, amount=amount
                        )
                        for eid, amount in values.items()
                        if amount
                    )
                messages.success(request, "Updated where the money comes from.")
                return redirect("month-end-transfers", month=str(month))
        if action == "continue":
            if plan.shortfall:
                messages.error(request, "Choose where to take the missing money from first.")
                return redirect("month-end-transfers", month=str(month))
            _advance(close, 5)
            return redirect("month-end-check", month=str(month))

    context.update(_context(month, close, 4))
    if plan.shortfall or context["inputs"].covers:
        state = context["state"]
        candidates = []
        for ledger in state.ledgers:
            line = plan.lines[ledger.expense.id]
            available = max(0, line.balance_before) + line.contribution - line.release
            if available > 0 or line.cover:
                candidates.append(
                    {
                        "expense": ledger.expense,
                        "available": available,
                        "value": line.cover or None,
                        "raw": request.POST.get(f"cover-{ledger.expense.id}")
                        if cover_errors
                        else None,
                        "error": cover_errors.get(ledger.expense.id),
                        "next_due": line.next_due,
                    }
                )
        context["cover_candidates"] = sorted(
            candidates, key=lambda c: (c["next_due"] is None, c["next_due"] or 0), reverse=True
        )
    return render(request, "ledger/month_end/transfers.html", context)


def check(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, close = guarded
    if close.step < 5:
        return redirect("month-end-transfers", month=str(month))
    context = _plan_context(request.budget, month, close)
    context.update(_context(month, close, 5))
    return render(request, "ledger/month_end/check.html", context)


@require_POST
def finish(request, month: str):
    guarded = _guard(request, month)
    if not isinstance(guarded, tuple):
        return guarded
    month, _ = guarded
    try:
        services.finalize_close(request.budget, month, request.user)
    except CloseError as error:
        messages.error(request, str(error))
        return redirect("month-end-transfers", month=str(month))
    messages.success(
        request,
        f"The month-end on {(month - 1).last_day():%d %B} is closed. "
        "Tick off the transfers as you make them.",
    )
    return redirect("close-detail", month=str(month))


# --- Closed months ------------------------------------------------------------------------------


def close_list(request):
    closes = request.budget.closes.prefetch_related("transfers")
    return render(request, "ledger/closes/list.html", {"closes": closes})


def close_detail(request, month: str):
    month = parse_month(month)
    close = get_object_or_404(MonthClose, month=month.first_day(), budget=request.budget)
    if not close.is_closed:
        return redirect("month-end")
    if request.method == "POST":
        transfer = get_object_or_404(Transfer, pk=_int(request.POST.get("transfer")), close=close)
        transfer.done = not transfer.done
        transfer.done_by = request.user if transfer.done else None
        transfer.done_at = timezone.now() if transfer.done else None
        transfer.save()
        return redirect("close-detail", month=str(month))
    lines = (
        close.lines.select_related("expense", "expense__account")
        .exclude(contribution=0, topup=0, cover=0, release=0, expected_spend=0)
        .order_by("expense__account__sort_order", "expense__name")
    )
    last = services.last_closed(request.budget)
    context = {
        "close": close,
        "month": month,
        "transfer_day": (month - 1).last_day(),
        "transfers": close.transfers.select_related("account"),
        "lines": lines,
        "can_reopen": last is not None and last.pk == close.pk,
    }
    return render(request, "ledger/closes/detail.html", context)


def close_reopen(request, month: str):
    month = parse_month(month)
    close = get_object_or_404(
        MonthClose,
        month=month.first_day(),
        status=MonthClose.Status.CLOSED,
        budget=request.budget,
    )
    if request.method == "POST":
        try:
            services.reopen_close(close)
        except CloseError as error:
            messages.error(request, str(error))
            return redirect("close-detail", month=str(month))
        messages.success(request, "The month-end is open again. Make your changes and close it.")
        return redirect("month-end-transfers", month=str(month))
    return render(request, "ledger/closes/reopen.html", {"close": close, "month": month})
