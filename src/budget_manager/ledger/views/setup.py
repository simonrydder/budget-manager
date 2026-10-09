"""Setting up a budget, step by step: the accounts, the expenses, a summary of what they cost, the
income, and finally the transfers that start the budget."""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Max
from django.shortcuts import redirect, render
from django.urls import reverse

from budget_manager.engine import CloseError, format_amount, format_input
from budget_manager.ledger import services
from budget_manager.ledger.forms import (
    BalancesForm,
    CategoryForm,
    NewAccountForm,
    QuickExpenseForm,
    QuickIncomeForm,
)
from budget_manager.ledger.models import Account, Category, Expense, IncomeSource
from budget_manager.ledger.views.common import read_amounts, today

STEPS = [
    (1, "accounts", "Accounts", "What is on each account today"),
    (2, "expenses", "Expenses", "Everything the money is for"),
    (3, "summary", "Summary", "What the expenses cost a month"),
    (4, "income", "Income", "What comes in"),
    (5, "transfers", "Transfers", "Even out the accounts and start"),
]


def _slug(number: int) -> str:
    return STEPS[min(max(number, 1), 5) - 1][1]


def _guard(request, step: int):
    """The setup closes after the first month-end, and a step opens once the one before it
    is done."""
    budget = request.budget
    if services.last_closed(budget) is not None:
        messages.info(
            request,
            "The budget is running, so the setup is closed. Change the accounts, expenses and "
            "income on their own pages.",
        )
        return redirect("dashboard")
    if step > budget.setup_step:
        return redirect(f"setup-{_slug(budget.setup_step)}")
    return None


def _reached(budget, step: int) -> None:
    if budget.setup_step < step:
        budget.setup_step = step
        budget.save(update_fields=["setup_step"])


def _context(request, current: int, **extra) -> dict:
    budget = request.budget
    reached = min(budget.setup_step, 5)
    steps = [
        {
            "number": number,
            "slug": slug,
            "label": label,
            "hint": hint,
            "url": reverse(f"setup-{slug}"),
            "current": number == current,
            "done": number < reached and number != current,
            "reachable": number <= reached,
        }
        for number, slug, label, hint in STEPS
    ]
    return {
        "steps": steps,
        "current_step": current,
        "step": steps[current - 1],
        "started": services.budget_started(budget),
        "today": today(),
        **extra,
    }


def resume(request):
    """Continue the setup where it was left."""
    blocked = _guard(request, 1)
    if blocked:
        return blocked
    return redirect(f"setup-{_slug(request.budget.setup_step)}")


# --- Step 1: accounts -----------------------------------------------------------------------


def accounts(request):
    blocked = _guard(request, 1)
    if blocked:
        return blocked
    budget = request.budget
    items = list(budget.accounts.all())
    posted = request.POST if request.method == "POST" else None
    action = request.POST.get("action")
    form = BalancesForm(posted, budget=budget, accounts=items)
    new = NewAccountForm(posted if action == "add" else None, instance=Account(budget=budget))
    if action == "add":
        if new.is_valid():
            form.keep_typed_balances()
            account = new.save(commit=False)
            account.sort_order = (budget.accounts.aggregate(m=Max("sort_order"))["m"] or 0) + 1
            account.save()
            messages.success(request, f"Added {account.name}. Enter its balance too.")
            return redirect(reverse("setup-accounts") + "#balances")
        form = BalancesForm(posted, budget=budget, accounts=items)
        form.errors.clear()  # only the new account's name is checked when adding
    elif request.method == "POST" and form.is_valid():
        form.save(today())
        _reached(budget, 2)
        return redirect("setup-expenses")
    rows = [
        {
            "account": account,
            "field": form[BalancesForm.key(account)],
            "expenses": account.expenses.count(),
        }
        for account in items
    ]
    context = _context(request, 1, form=form, new=new, rows=rows)
    return render(request, "ledger/setup/accounts.html", context)


# --- Step 2: expenses -----------------------------------------------------------------------

KEEP = ("account", "category", "interval_months", "kind")


def expenses(request):
    blocked = _guard(request, 2)
    if blocked:
        return blocked
    budget = request.budget
    action = request.POST.get("action")
    initial = {name: request.GET[name] for name in KEEP if request.GET.get(name)}
    form = QuickExpenseForm(
        request.POST if action == "add" else None,
        instance=Expense(budget=budget),
        initial=initial,
    )
    if action == "add" and form.is_valid():
        expense = form.save(commit=False)
        expense.sort_order = (budget.expenses.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        expense.save()
        keep = {
            "account": expense.account_id,
            "category": expense.category_id or "",
            "interval_months": expense.interval_months,
            "kind": expense.kind,
            "added": expense.name,
        }
        return redirect(f"{reverse('setup-expenses')}?{urlencode(keep)}#add")
    category_form = CategoryForm(
        request.POST if action == "add_category" else None,
        prefix="category",
        instance=Category(budget=budget),
    )
    if action == "add_category" and category_form.is_valid():
        category = category_form.save(commit=False)
        category.sort_order = (budget.categories.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        category.save()
        messages.success(request, f"Added the category {category.name}.")
        return redirect(reverse("setup-expenses") + "#categories")
    if action == "remove_category":
        category = budget.categories.filter(pk=_int(request.POST.get("category"))).first()
        if category is not None:
            moved = category.expenses.count()
            category.delete()
            note = f" Its {moved} expense{'s are' if moved != 1 else ' is'} now uncategorised."
            messages.success(request, f"Removed {category.name}.{note if moved else ''}")
        return redirect(reverse("setup-expenses") + "#categories")
    if action == "remove":
        expense = budget.expenses.filter(pk=_int(request.POST.get("expense"))).first()
        if expense is None:
            pass
        elif expense.lines.exists() or expense.moves.filter(done=True).exists():
            messages.error(request, f"{expense.name} has history, so it stays. Edit it instead.")
        else:
            expense.delete()
            messages.success(request, f"Removed {expense.name}.")
        return redirect("setup-expenses")
    if action == "next":
        if not budget.expenses.exists():
            messages.error(request, "Add at least one expense first.")
            return redirect("setup-expenses")
        _reached(budget, 3)
        return redirect("setup-summary")
    now = today()
    start = services.setup_start_month(budget, now)
    groups = []
    listed = budget.expenses.select_related("account", "category")
    for category in [*budget.categories.all(), None]:
        items = [
            {
                "expense": expense,
                "next_due": services.engine_expense(expense, start).schedule.next_due_from(now),
                "monthly": services.monthly_need(expense, start, now),
            }
            for expense in listed
            if expense.category_id == (category.pk if category else None)
        ]
        if items:
            groups.append(
                {
                    "name": category.name if category else "Uncategorised",
                    "key": category.pk if category else "none",
                    "items": items,
                    "monthly": sum(item["monthly"] or 0 for item in items),
                }
            )
    added = request.GET.get("added", "")
    if added and not form.is_bound:
        form.fields["name"].widget.attrs["autofocus"] = True
    categories = budget.categories.annotate(used=Count("expenses"))
    context = _context(
        request,
        2,
        form=form,
        groups=groups,
        count=sum(len(g["items"]) for g in groups),
        monthly=sum(g["monthly"] for g in groups),
        added=added,
        categories=categories,
        category_form=category_form,
    )
    return render(request, "ledger/setup/expenses.html", context)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- Step 3: summary ------------------------------------------------------------------------


def summary(request):
    blocked = _guard(request, 3)
    if blocked:
        return blocked
    budget = request.budget
    if request.method == "POST":
        _reached(budget, 4)
        return redirect("setup-income")
    result = services.setup_summary(budget, today())
    context = _context(request, 3, summary=result)
    return render(request, "ledger/setup/summary.html", context)


# --- Step 4: income -------------------------------------------------------------------------


def income(request):
    blocked = _guard(request, 4)
    if blocked:
        return blocked
    budget = request.budget
    action = request.POST.get("action")
    start = services.setup_start_month(budget, today())
    form = QuickIncomeForm(
        request.POST if action == "add" else None,
        instance=IncomeSource(budget=budget),
        initial={"first_month": start.first_day()},
    )
    if action == "add" and form.is_valid():
        source = form.save(commit=False)
        source.sort_order = (budget.incomes.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        source.save()
        return redirect(f"{reverse('setup-income')}?{urlencode({'added': source.name})}#add")
    if action == "remove":
        source = budget.incomes.filter(pk=_int(request.POST.get("source"))).first()
        if source is not None:
            if source.entries.exists():
                messages.error(request, f"{source.name} has history, so it stays.")
            else:
                source.delete()
                messages.success(request, f"Removed {source.name}.")
        return redirect("setup-income")
    if action == "next":
        if not budget.incomes.exists():
            messages.error(request, "Add at least one income first.")
            return redirect("setup-income")
        _reached(budget, 5)
        return redirect("setup-transfers")
    result = services.setup_summary(budget, today())
    sources = [
        {
            "source": source,
            "monthly": source.amount // source.interval_months if source.interval_months else 0,
        }
        for source in budget.incomes.all()
    ]
    added = request.GET.get("added", "")
    if added and not form.is_bound:
        form.fields["name"].widget.attrs["autofocus"] = True
    context = _context(
        request, 4, form=form, sources=sources, summary=result, start=start, added=added
    )
    return render(request, "ledger/setup/income.html", context)


# --- Step 5: transfers ----------------------------------------------------------------------


def transfers(request):
    blocked = _guard(request, 5)
    if blocked:
        return blocked
    budget = request.budget
    now = today()
    services.align_running_budgets(budget, now)
    items = list(budget.accounts.all())
    expense_ids = list(budget.expenses.values_list("pk", flat=True))
    bank = {account.pk: account.start_balance for account in items}
    errors: dict[str, str] = {}
    spent = None
    if request.method == "POST":
        spent, spent_errors = read_amounts(request.POST, "spent-", expense_ids)
        errors = {f"spent-{key}": value for key, value in spent_errors.items()}
    plan = services.plan_start(budget, now, bank, spent)
    if request.POST.get("action") == "start" and not errors:
        try:
            services.apply_start(budget, plan, request.user)
        except CloseError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"{budget.name} is started. Its first month-end is on "
                f"{plan.opening.last_day():%d %B}.",
            )
            return redirect("dashboard")

    raw = request.POST if request.method == "POST" else {}

    def field(name: str, value: int | None) -> dict:
        typed = raw.get(name)
        return {
            "name": name,
            "value": typed if typed is not None else format_input(value),
            "error": errors.get(name),
        }

    for row in plan.rows:
        row.spent_field = field(f"spent-{row.expense.id}", row.spent or None)
    missing = [item.account for item in plan.accounts if item.bank is None]
    bills_due = sorted(
        (row for row in plan.rows if row.due and not row.expense.is_running),
        key=lambda row: row.due,
    )
    preview = services.preview_first_close(budget, plan) if not errors else None
    accounts_by_id = {account.pk: account for account in items}
    first_transfers = []
    if preview:
        # Next to each transfer, what its expenses need on average a month: with every expense
        # set aside as suggested the two match, give or take rounding up to whole kroner.
        usual = services.monthly_amounts(services.preview_state(budget, plan))
        for transfer in preview.transfers.values():
            if not transfer.amount:
                continue
            first_transfers.append(
                {
                    "account": accounts_by_id[transfer.account_id],
                    "plan": transfer,
                    "usual": sum(
                        usual[row.expense.id]
                        for row in plan.rows
                        if row.expense.account_id == transfer.account_id
                    ),
                }
            )
    context = _context(
        request,
        5,
        plan=plan,
        preview=preview,
        first_transfers=first_transfers,
        missing=missing,
        errors=errors,
        running_rows=[row for row in plan.rows if row.due and row.expense.is_running],
        paid_rows=[row for row in bills_due if row.spent],
        unpaid_rows=[row for row in bills_due if not row.spent],
        old_balances=budget.balances_on and budget.balances_on != now,
        shortage=format_amount(-plan.general_savings)
        if plan.complete and plan.general_savings < 0
        else None,
    )
    return render(request, "ledger/setup/transfers.html", context)
