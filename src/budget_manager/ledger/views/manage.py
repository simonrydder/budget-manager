"""Create, edit and end accounts, categories, expenses and income sources."""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import Max, ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from budget_manager.engine import Role, YearMonth, format_amount
from budget_manager.ledger import services
from budget_manager.ledger.forms import (
    AccountForm,
    CategoryForm,
    CorrectionForm,
    EndExpenseForm,
    ExpenseForm,
    IncomeSourceForm,
    ReleaseForm,
)
from budget_manager.ledger.models import (
    Account,
    BalanceCorrection,
    Category,
    Expense,
    IncomeSource,
    Move,
)
from budget_manager.ledger.views.common import next_value, safe_next, today


# --- Accounts -----------------------------------------------------------------------------------


def account_list(request):
    budget = request.budget
    state = services.build_state(budget)
    balances = state.current_expense_balances()
    account_balances = state.current_account_balances()
    rows = []
    for account in budget.accounts.all():
        expenses = [
            {"expense": expense, "balance": balances[expense.id]}
            for expense in account.expenses.select_related("category")
        ]
        rows.append(
            {
                "account": account,
                "balance": account_balances[account.id],
                "expenses": sorted(expenses, key=lambda item: item["expense"].name.lower()),
                "expenses_total": sum(item["balance"] for item in expenses),
            }
        )
    context = {
        "rows": rows,
        "nemkonto": state.nemkonto,
        "general_savings": state.general_savings,
        "corrections": budget.corrections.select_related("created_by")[:10],
    }
    return render(request, "ledger/accounts/list.html", context)


def _save_account(form: AccountForm) -> Account:
    with transaction.atomic():
        account = form.save(commit=False)
        budget = account.budget
        wants_savings = form.cleaned_data.get("holds_general_savings")
        if wants_savings and not account.holds_general_savings:
            budget.accounts.filter(role=Role.SAVINGS.value).update(role=Role.NORMAL.value)
            account.role = Role.SAVINGS.value
        if not account.pk:
            account.sort_order = (budget.accounts.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        account.save()
    return account


def account_form(request, pk: int | None = None):
    budget = request.budget
    account = get_object_or_404(Account, pk=pk, budget=budget) if pk else Account(budget=budget)
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        previous_holder = budget.accounts.filter(role=Role.SAVINGS.value).first()
        saved = _save_account(form)
        if previous_holder and previous_holder.pk != saved.pk and saved.holds_general_savings:
            messages.warning(
                request,
                f"General Savings now lives on {saved.name}. Move its money from "
                f"{previous_holder.name} in your bank.",
            )
        messages.success(request, f"Saved {saved.name}.")
        return redirect(safe_next(request, "accounts"))
    context = {"form": form, "account": account, "next": next_value(request)}
    return render(request, "ledger/accounts/form.html", context)


def account_delete(request, pk: int):
    account = get_object_or_404(Account, pk=pk, budget=request.budget)
    blocked = None
    if account.is_nemkonto:
        blocked = "The NemKonto is always needed."
    elif account.holds_general_savings:
        blocked = "Choose another account for General Savings first."
    elif account.expenses.exists():
        blocked = "Move or delete the expenses linked to this account first."
    elif account.transfers.exists():
        blocked = "This account has transfers in closed months, so it is kept for history."
    if request.method == "POST" and not blocked:
        account.delete()
        messages.success(request, f"Deleted {account.name}.")
        return redirect(safe_next(request, "accounts"))
    return render(
        request,
        "ledger/confirm_delete.html",
        {"object": account, "blocked": blocked, "kind": "account", "next": next_value(request)},
    )


def correction(request, target: str):
    if target not in BalanceCorrection.Target.values:
        return redirect("accounts")
    label = BalanceCorrection.Target(target).label
    initial = {}
    if "amount" in request.GET:
        initial["amount"] = request.GET["amount"]
    form = CorrectionForm(request.POST or None, initial=initial)
    # From the month-end check the transfers are already made, so the correction applies from
    # the following month-end. Otherwise it applies to the coming one.
    after_transfers = (request.POST or request.GET).get("after") == "1"
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.budget = request.budget
        item.target = target
        upcoming = services.next_close_month(request.budget)
        item.month = (upcoming if after_transfers else upcoming - 1).first_day()
        item.created_by = request.user
        item.save()
        messages.success(request, f"{label} corrected.")
        return redirect(safe_next(request, "accounts"))
    return render(
        request,
        "ledger/accounts/correction.html",
        {
            "form": form,
            "label": label,
            "next": (request.POST or request.GET).get("next", ""),
            "after": after_transfers,
        },
    )


# --- Categories ---------------------------------------------------------------------------------


def category_list(request):
    budget = request.budget
    form = CategoryForm(request.POST or None, instance=Category(budget=budget))
    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.sort_order = (budget.categories.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        category.save()
        messages.success(request, f"Added {category.name}.")
        return redirect("categories")
    categories = budget.categories.all()
    return render(request, "ledger/categories/list.html", {"form": form, "categories": categories})


def category_edit(request, pk: int):
    category = get_object_or_404(Category, pk=pk, budget=request.budget)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Renamed.")
        return redirect(safe_next(request, "categories"))
    context = {"form": form, "category": category, "next": next_value(request)}
    return render(request, "ledger/categories/form.html", context)


def category_delete(request, pk: int):
    category = get_object_or_404(Category, pk=pk, budget=request.budget)
    if request.method == "POST":
        category.delete()
        messages.success(request, f"Deleted {category.name}. Its expenses are now uncategorised.")
        return redirect("categories")
    return render(request, "ledger/confirm_delete.html", {"object": category, "kind": "category"})


@require_POST
def category_move(request, pk: int, direction: str):
    get_object_or_404(Category, pk=pk, budget=request.budget)
    categories = list(request.budget.categories.all())
    index = next(i for i, c in enumerate(categories) if c.pk == pk)
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(categories):
        categories[index], categories[other] = categories[other], categories[index]
        for number, category in enumerate(categories):
            if category.sort_order != number:
                category.sort_order = number
                category.save(update_fields=["sort_order"])
    return redirect("categories")


# --- Expenses -----------------------------------------------------------------------------------


def _card(expense, ledger, balance: int, month, now) -> dict:
    """What an expense card shows: the next payment (or the month's running budget, or the
    goal), how much of it is there, and whether that is on track with the plan."""
    model = ledger.expense
    next_due = model.schedule.next_due_from(now)
    card = {
        "expense": expense,
        "balance": balance,
        "next_due": next_due,
        "ended": expense.is_ended(now),
        "days": (next_due - now).days if next_due else None,
    }
    if expense.is_running:
        card["shape"] = "running"
        card["target"] = model.amount
        card["refill"] = (month - 1).last_day()
        card["this_month"] = YearMonth.of(now)
    elif model.schedule.interval_months == 0:
        card["shape"] = "goal"
        card["target"] = model.amount
        card["months"] = YearMonth.of(now).months_until(YearMonth.of(next_due)) if next_due else 0
    else:
        card["shape"] = "bill"
        card["target"] = model.amount_on(next_due) if next_due else 0
    target = card["target"]
    card["percent"] = max(0, min(100, round(balance * 100 / target))) if target else 0
    # The plan's balance by now assumes every payment so far cost what was expected, this
    # month's included; one not entered yet counts as its expected amount.
    line = ledger.lines.get(month - 1)
    pending = line.expected_spend if line and (month - 1) not in ledger.spending else 0
    short = ledger.planned_balance_before(month) - (balance - pending)
    if balance < 0:
        card["status"] = ("bad", "below zero")
    elif expense.is_running:
        card["status"] = None
    elif next_due is None:
        card["status"] = None
    elif short > 100:
        card["status"] = ("warn", f"short {format_amount(short)}")
    else:
        card["status"] = ("ok", "on track")
    return card


def expense_board(request):
    budget = request.budget
    group = "account" if request.GET.get("group") == "account" else "category"
    state = services.build_state(budget)
    balances = state.current_expense_balances()
    monthly = services.monthly_amounts(state)
    ledgers = {ledger.expense.id: ledger for ledger in state.ledgers}
    now = today()
    cards = []
    for expense in budget.expenses.select_related("account", "category"):
        ledger = ledgers[expense.id]
        card = _card(expense, ledger, balances[expense.id], state.month, now)
        card["monthly"] = monthly[expense.id]
        cards.append(card)
    active = [card for card in cards if not card["ended"]]
    if group == "category":
        columns = [{"key": "", "name": "Uncategorised", "cards": []}]
        columns += [
            {"key": str(c.pk), "name": c.name, "cards": []} for c in budget.categories.all()
        ]
        index = {column["key"]: column for column in columns}
        for card in active:
            index[str(card["expense"].category_id or "")]["cards"].append(card)
        if not columns[0]["cards"]:
            columns[0]["hint"] = "Drop expenses here to remove their category."
    else:
        used = {card["expense"].account_id for card in active}
        columns = [
            {"key": str(a.pk), "name": a.name, "cards": []}
            for a in budget.accounts.all()
            if not a.is_nemkonto or a.pk in used  # only an expense put there earlier
        ]
        index = {column["key"]: column for column in columns}
        for card in active:
            index[str(card["expense"].account_id)]["cards"].append(card)
    for column in columns:
        column["monthly"] = sum(monthly[card["expense"].id] for card in column["cards"])
    context = {
        "group": group,
        "columns": columns,
        "monthly_total": sum(column["monthly"] for column in columns),
        "ended": [card for card in cards if card["ended"]],
        "count": len(active),
    }
    return render(request, "ledger/expenses/board.html", context)


def expense_form(request, pk: int | None = None):
    budget = request.budget
    expense = get_object_or_404(Expense, pk=pk, budget=budget) if pk else Expense(budget=budget)
    initial = {}
    if not pk and request.GET.get("category"):
        initial["category"] = request.GET["category"]
    previous_account = expense.account if pk else None
    balance = (
        services.build_state(budget).current_expense_balances().get(expense.pk, 0) if pk else 0
    )
    pending = _waiting(expense, Move.Type.TOPUP) if pk else None
    if pending:
        initial["topup"] = pending.amount
    started = services.budget_started(budget)
    form = ExpenseForm(request.POST or None, instance=expense, initial=initial)
    if not pk or not started:
        del form.fields["topup"]  # until the budget is started, the setup decides the balances
    if pk or not started:
        del form.fields["fill_from_savings"]
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if previous_account and previous_account.pk != item.account_id:
            note = _balance_move_note(item, previous_account, item.account)
            if note:
                messages.warning(request, note)
        if not item.pk:
            item.sort_order = (budget.expenses.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        if not item.pk and started:
            item.start_month = services.next_close_month(budget).first_day()
        item.save()
        if pk:
            _save_waiting(request, item, Move.Type.TOPUP, form.cleaned_data.get("topup"))
        if form.cleaned_data.get("fill_from_savings"):
            _save_fund(request, item)
        messages.success(request, f"Saved {item.name}.")
        if warning := services.monthly_balance(budget).warning():
            messages.warning(request, warning)
        if "another" in request.POST:
            return redirect("expense-new")
        if next_value(request):
            return redirect(safe_next(request, "expenses"))
        return redirect("expense-detail", pk=item.pk)
    context = {
        "form": form,
        "expense": expense,
        "monthly": services.monthly_balance(budget),
        "balance": balance,
        "next": next_value(request),
    }
    return render(request, "ledger/expenses/form.html", context)


def _waiting(expense: Expense, kind: str) -> Move | None:
    return expense.moves.filter(done=False, kind=kind).first()


def _save_fund(request, expense: Expense) -> None:
    """Fill a new expense from General Savings up to its steady path."""
    state = services.build_state(expense.budget)
    amount = services.fund_amount(state.ledger(expense.pk), state.month)
    if not amount:
        if state.ledger(expense.pk).expense.suggested_starting_balance() is None:
            messages.info(request, "A one-off goal has no steady amount, so nothing is filled.")
        return
    _save_waiting(request, expense, Move.Type.FUND, amount)


def _save_waiting(request, expense: Expense, kind: str, amount: int | None) -> None:
    """Remember (or drop) money to move between General Savings and an expense."""
    pending = _waiting(expense, kind)
    if not amount:
        if pending:
            pending.delete()
        return
    if pending and pending.amount == amount:
        return
    Move.objects.update_or_create(
        budget=expense.budget,
        expense=expense,
        kind=kind,
        done=False,
        defaults={"amount": amount, "account": expense.account, "created_by": request.user},
    )
    direction = "to" if kind != Move.Type.RELEASE else "from"
    messages.info(
        request,
        f"{format_amount(amount)} is waiting to move {direction} {expense.name}. Make the bank "
        "transfer any day under Balance (or at the month-end).",
    )


def expense_detail(request, pk: int):
    budget = request.budget
    expense = get_object_or_404(
        Expense.objects.select_related("account", "category"), pk=pk, budget=budget
    )
    state = services.build_state(budget)
    ledger = state.ledger(expense.id)
    points = services.forecast(budget, 12, state=state)
    balance = state.current_expense_balances()[expense.id]
    history = []
    for line in expense.lines.select_related("close").order_by("close__month"):
        month = YearMonth.of(line.close.month)
        spent = ledger.spending.get(month)
        history.append(
            {
                "month": month,
                "line": line,
                "spent": spent,
                "balance_end": ledger.balance_end_of(month) if spent is not None else None,
            }
        )
    upcoming = ledger.expense.schedule.upcoming(today(), 4)
    plan_rows = [
        {
            "month": point.budget_month,
            "transfer_day": point.close.transfer_date,
            "contribution": point.close.lines[expense.id].contribution,
            "expected": point.close.lines[expense.id].expected_spend,
            "balance": point.expense_balances[expense.id],
        }
        for point in points
    ]
    waiting = [
        item for item in services.balancing(budget, today(), state).moves if item.expense == expense
    ]
    pending_release = next((item for item in waiting if item.kind == Move.Type.RELEASE), None)
    context = {
        "expense": expense,
        "balance": balance,
        "history": list(reversed(history)),
        "upcoming": upcoming,
        "first_payment": (
            expense.first_amount
            if upcoming and expense.first_amount is not None and upcoming[0] == expense.first_due
            else None
        ),
        "plan_rows": plan_rows,
        "next_contribution": points[0].close.lines[expense.id].contribution,
        "waiting": [item for item in waiting if item is not pending_release],
        "pending_release": pending_release,
        "moves": expense.moves.filter(done=True),
        "release_form": ReleaseForm(initial={"amount": max(0, balance)}),
        "can_delete": not _has_history(expense),
        "ended": expense.is_ended(today()),
    }
    return render(request, "ledger/expenses/detail.html", context)


def expense_end(request, pk: int):
    expense = get_object_or_404(Expense, pk=pk, budget=request.budget)
    form = EndExpenseForm(request.POST or None, initial={"end_date": expense.end_date or today()})
    if request.method == "POST" and form.is_valid():
        expense.end_date = form.cleaned_data["end_date"]
        expense.save(update_fields=["end_date", "updated_at"])
        messages.success(
            request,
            f"{expense.name} ends on {expense.end_date:%d %b %Y}. Once it has ended and its last "
            "payment is entered, what is left on it returns to General Savings under Balance.",
        )
        return redirect("expense-detail", pk=expense.pk)
    return render(request, "ledger/expenses/end.html", {"form": form, "expense": expense})


def expense_delete(request, pk: int):
    expense = get_object_or_404(Expense, pk=pk, budget=request.budget)
    blocked = None
    if _has_history(expense):
        blocked = "This expense has history. End it instead, so past months stay correct."
    if request.method == "POST" and not blocked:
        expense.delete()
        messages.success(request, f"Deleted {expense.name}.")
        return redirect(safe_next(request, "expenses"))
    return render(
        request,
        "ledger/confirm_delete.html",
        {"object": expense, "blocked": blocked, "kind": "expense", "next": next_value(request)},
    )


def _has_history(expense: Expense) -> bool:
    return (
        expense.lines.exists()
        or expense.spending.exists()
        or expense.moves.filter(done=True).exists()
    )


def _balance_move_note(expense: Expense, old: Account, new: Account) -> str | None:
    balance = services.build_state(expense.budget).current_expense_balances().get(expense.id, 0)
    if not balance or old.pk == new.pk:
        return None
    return (
        f"{expense.name} moved to {new.name}. Move its balance of {format_amount(balance)} "
        f"from {old.name} to {new.name} in your bank."
    )


@require_POST
def expense_move(request, pk: int):
    """Drag and drop: set the category or the account of an expense, and the order of the
    expenses in the column it was dropped in (``order``: comma-separated ids, top first)."""
    budget = request.budget
    expense = get_object_or_404(Expense, pk=pk, budget=budget)
    field = request.POST.get("field")
    value = request.POST.get("value", "")
    order = [item for item in request.POST.get("order", "").split(",") if item]
    wants_json = request.headers.get("Accept", "").startswith("application/json")
    if (value and not value.isdigit()) or not all(item.isdigit() for item in order):
        return JsonResponse({"ok": False, "error": "Unknown target."}, status=400)
    if field not in {"category", "account"}:
        return JsonResponse({"ok": False, "error": "Unknown field."}, status=400)

    current = str(getattr(expense, f"{field}_id") or "")
    message = note = None
    if value != current:
        if field == "category":
            expense.category = (
                get_object_or_404(Category, pk=value, budget=budget) if value else None
            )
            expense.save(update_fields=["category", "updated_at"])
            target = expense.category.name if expense.category else "Uncategorised"
        else:
            account = get_object_or_404(Account, pk=value, budget=budget)
            if account.is_nemkonto:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Expenses cannot use the NemKonto. What is spent from it is "
                        "entered at each month-end.",
                    },
                    status=400,
                )
            previous = expense.account
            expense.account = account
            expense.save(update_fields=["account", "updated_at"])
            target = account.name
            note = _balance_move_note(expense, previous, account)
        message = note or f"{expense.name} moved to {target}."
    if order:
        with transaction.atomic():
            for position, expense_id in enumerate(order):
                budget.expenses.filter(pk=int(expense_id)).update(sort_order=position)
        message = message or "Order saved."
    message = message or "Nothing changed."
    if wants_json:
        return JsonResponse({"ok": True, "message": message})
    (messages.warning if note else messages.success)(request, message)
    return redirect(safe_next(request, "expenses"))


@require_POST
def expense_release(request, pk: int):
    """Move (part of) an expense's balance to General Savings."""
    expense = get_object_or_404(Expense, pk=pk, budget=request.budget)
    if "cancel" in request.POST:
        expense.moves.filter(done=False, kind=Move.Type.RELEASE).delete()
        messages.success(request, "Cancelled.")
        return redirect("expense-detail", pk=pk)
    form = ReleaseForm(request.POST)
    balance = services.build_state(request.budget).current_expense_balances()[expense.id]
    if form.is_valid():
        amount = form.cleaned_data["amount"]
        if not amount or amount > balance:
            messages.error(request, "Enter an amount up to the current balance.")
        else:
            _save_waiting(request, expense, Move.Type.RELEASE, amount)
    else:
        messages.error(request, " ".join(form.errors.get("amount", ["Enter an amount."])))
    return redirect("expense-detail", pk=pk)


# --- Income -------------------------------------------------------------------------------------


def income_list(request):
    budget = request.budget
    month = services.next_close_month(budget)
    sources = []
    for source in budget.incomes.all():
        engine_source = services.engine_income(source)
        upcoming = next(
            (month + offset for offset in range(0, 37) if engine_source.expected(month + offset)),
            None,
        )
        sources.append(
            {
                "source": source,
                "next": upcoming,
                "last": source.entries.order_by("-month").first(),
                "ended": source.end_month is not None and YearMonth.of(source.end_month) < month,
            }
        )
    return render(request, "ledger/income/list.html", {"sources": sources, "month": month})


def income_form(request, pk: int | None = None):
    budget = request.budget
    source = (
        get_object_or_404(IncomeSource, pk=pk, budget=budget) if pk else IncomeSource(budget=budget)
    )
    initial = {} if pk else {"first_month": services.next_close_month(budget).first_day()}
    form = IncomeSourceForm(request.POST or None, instance=source, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"Saved {item.name}.")
        if warning := services.monthly_balance(budget).warning():
            messages.warning(request, warning)
        return redirect(safe_next(request, "income"))
    context = {"form": form, "source": source, "next": next_value(request)}
    return render(request, "ledger/income/form.html", context)


def income_delete(request, pk: int):
    source = get_object_or_404(IncomeSource, pk=pk, budget=request.budget)
    blocked = None
    if source.entries.filter(
        month__lt=services.next_close_month(request.budget).first_day()
    ).exists():
        blocked = "This income has history. Set a last month instead, so past months stay correct."
    if request.method == "POST" and not blocked:
        try:
            source.delete()
        except ProtectedError:
            blocked = "This income is still in use."
        else:
            messages.success(request, f"Deleted {source.name}.")
            return redirect(safe_next(request, "income"))
    return render(
        request,
        "ledger/confirm_delete.html",
        {
            "object": source,
            "blocked": blocked,
            "kind": "income source",
            "next": next_value(request),
        },
    )
