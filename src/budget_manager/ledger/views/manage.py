"""Create, edit and end accounts, categories, expenses and income sources."""

from __future__ import annotations

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Max, ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
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
    Decision,
    Expense,
    IncomeSource,
)
from budget_manager.ledger.views.common import today


def _safe_next(request, fallback: str) -> str:
    """The ``next`` field, only if it points back into this app."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse(fallback)


# --- Accounts -----------------------------------------------------------------------------------


def account_list(request):
    state = services.build_state()
    balances = state.current_expense_balances()
    account_balances = state.current_account_balances()
    rows = []
    for account in Account.objects.all():
        expenses = [
            {"expense": expense, "balance": balances[expense.id]}
            for expense in account.expenses.select_related("category")
        ]
        rows.append(
            {
                "account": account,
                "balance": account_balances[account.id],
                "expenses": sorted(expenses, key=lambda item: item["expense"].name.lower()),
            }
        )
    context = {
        "rows": rows,
        "nemkonto": state.nemkonto,
        "general_savings": state.general_savings,
        "corrections": BalanceCorrection.objects.select_related("created_by")[:10],
    }
    return render(request, "ledger/accounts/list.html", context)


def _save_account(form: AccountForm) -> Account:
    with transaction.atomic():
        account = form.save(commit=False)
        wants_savings = form.cleaned_data.get("holds_general_savings")
        if wants_savings and not account.holds_general_savings:
            Account.objects.filter(role=Role.SAVINGS.value).update(role=Role.NORMAL.value)
            account.role = Role.SAVINGS.value
        if not account.pk:
            account.sort_order = (Account.objects.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        account.save()
    return account


def account_form(request, pk: int | None = None):
    account = get_object_or_404(Account, pk=pk) if pk else Account()
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        previous_holder = Account.objects.filter(role=Role.SAVINGS.value).first()
        saved = _save_account(form)
        if previous_holder and previous_holder.pk != saved.pk and saved.holds_general_savings:
            messages.warning(
                request,
                f"General Savings now lives on {saved.name}. Move its money from "
                f"{previous_holder.name} in your bank.",
            )
        messages.success(request, f"Saved {saved.name}.")
        return redirect("accounts")
    return render(request, "ledger/accounts/form.html", {"form": form, "account": account})


def account_delete(request, pk: int):
    account = get_object_or_404(Account, pk=pk)
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
        return redirect("accounts")
    return render(
        request,
        "ledger/confirm_delete.html",
        {"object": account, "blocked": blocked, "kind": "account"},
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
        item.target = target
        upcoming = services.next_close_month()
        item.month = (upcoming if after_transfers else upcoming - 1).first_day()
        item.created_by = request.user
        item.save()
        messages.success(request, f"{label} corrected.")
        return redirect(_safe_next(request, "accounts"))
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
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.sort_order = (Category.objects.aggregate(m=Max("sort_order"))["m"] or 0) + 1
        category.save()
        messages.success(request, f"Added {category.name}.")
        return redirect("categories")
    categories = Category.objects.all()
    return render(request, "ledger/categories/list.html", {"form": form, "categories": categories})


def category_edit(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Renamed.")
        return redirect("categories")
    return render(request, "ledger/categories/form.html", {"form": form, "category": category})


def category_delete(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        category.delete()
        messages.success(request, f"Deleted {category.name}. Its expenses are now uncategorised.")
        return redirect("categories")
    return render(request, "ledger/confirm_delete.html", {"object": category, "kind": "category"})


@require_POST
def category_move(request, pk: int, direction: str):
    get_object_or_404(Category, pk=pk)
    categories = list(Category.objects.all())
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


def expense_board(request):
    group = "account" if request.GET.get("group") == "account" else "category"
    state = services.build_state()
    balances = state.current_expense_balances()
    ledgers = {ledger.expense.id: ledger for ledger in state.ledgers}
    now = today()
    cards = []
    for expense in Expense.objects.select_related("account", "category"):
        ledger = ledgers[expense.id]
        cards.append(
            {
                "expense": expense,
                "balance": balances[expense.id],
                "next_due": ledger.expense.schedule.next_due_from(now),
                "ended": expense.is_ended(now),
            }
        )
    active = [card for card in cards if not card["ended"]]
    if group == "category":
        columns = [{"key": "", "name": "Uncategorised", "cards": []}]
        columns += [{"key": str(c.pk), "name": c.name, "cards": []} for c in Category.objects.all()]
        index = {column["key"]: column for column in columns}
        for card in active:
            index[str(card["expense"].category_id or "")]["cards"].append(card)
        if not columns[0]["cards"]:
            columns[0]["hint"] = "Drop expenses here to remove their category."
    else:
        columns = [
            {"key": str(a.pk), "name": a.name, "cards": []}
            for a in Account.objects.exclude(role=Role.NEMKONTO.value)
        ]
        index = {column["key"]: column for column in columns}
        for card in active:
            index[str(card["expense"].account_id)]["cards"].append(card)
    for column in columns:
        column["monthly"] = sum(card["expense"].monthly_equivalent for card in column["cards"])
    context = {
        "group": group,
        "columns": columns,
        "ended": [card for card in cards if card["ended"]],
        "count": len(active),
    }
    return render(request, "ledger/expenses/board.html", context)


def expense_form(request, pk: int | None = None):
    expense = get_object_or_404(Expense, pk=pk) if pk else Expense()
    initial = {}
    if not pk and request.GET.get("category"):
        initial["category"] = request.GET["category"]
    previous_account = expense.account if pk else None
    form = ExpenseForm(request.POST or None, instance=expense, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if previous_account and previous_account.pk != item.account_id:
            note = _balance_move_note(item, previous_account, item.account)
            if note:
                messages.warning(request, note)
        if not item.pk and services.last_closed() is not None:
            item.start_month = services.next_close_month().first_day()
        item.save()
        messages.success(request, f"Saved {item.name}.")
        if "another" in request.POST:
            return redirect("expense-new")
        return redirect("expense-detail", pk=item.pk)
    return render(request, "ledger/expenses/form.html", {"form": form, "expense": expense})


def expense_detail(request, pk: int):
    expense = get_object_or_404(Expense.objects.select_related("account", "category"), pk=pk)
    state = services.build_state()
    ledger = state.ledger(expense.id)
    points = services.forecast(12, state=state)
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
    draft = services.draft_close()
    pending_release = (
        draft.decisions.filter(expense=expense, kind=Decision.Type.RELEASE).first()
        if draft
        else None
    )
    context = {
        "expense": expense,
        "balance": balance,
        "history": list(reversed(history)),
        "upcoming": upcoming,
        "plan_rows": plan_rows,
        "next_contribution": points[0].close.lines[expense.id].contribution,
        "pending_release": pending_release,
        "release_form": ReleaseForm(initial={"amount": max(0, balance)}),
        "can_delete": not expense.lines.exists() and not expense.spending.exists(),
        "ended": expense.is_ended(today()),
    }
    return render(request, "ledger/expenses/detail.html", context)


def expense_end(request, pk: int):
    expense = get_object_or_404(Expense, pk=pk)
    form = EndExpenseForm(request.POST or None, initial={"end_date": expense.end_date or today()})
    if request.method == "POST" and form.is_valid():
        expense.end_date = form.cleaned_data["end_date"]
        expense.save(update_fields=["end_date", "updated_at"])
        messages.success(request, f"{expense.name} ends on {expense.end_date:%d %b %Y}.")
        return redirect("expense-detail", pk=expense.pk)
    return render(request, "ledger/expenses/end.html", {"form": form, "expense": expense})


def expense_delete(request, pk: int):
    expense = get_object_or_404(Expense, pk=pk)
    blocked = None
    if expense.lines.exists() or expense.spending.exists():
        blocked = "This expense has history. End it instead, so past months stay correct."
    if request.method == "POST" and not blocked:
        expense.delete()
        messages.success(request, f"Deleted {expense.name}.")
        return redirect("expenses")
    return render(
        request,
        "ledger/confirm_delete.html",
        {"object": expense, "blocked": blocked, "kind": "expense"},
    )


def _balance_move_note(expense: Expense, old: Account, new: Account) -> str | None:
    balance = services.build_state().current_expense_balances().get(expense.id, 0)
    if not balance or old.pk == new.pk:
        return None
    return (
        f"{expense.name} moved to {new.name}. Move its balance of {format_amount(balance)} "
        f"from {old.name} to {new.name} in your bank."
    )


@require_POST
def expense_move(request, pk: int):
    """Drag and drop: set the category or the account of an expense."""
    expense = get_object_or_404(Expense, pk=pk)
    field = request.POST.get("field")
    value = request.POST.get("value", "")
    if value and not value.isdigit():
        return JsonResponse({"ok": False, "error": "Unknown target."}, status=400)
    if field == "category":
        expense.category = get_object_or_404(Category, pk=value) if value else None
        expense.save(update_fields=["category", "updated_at"])
        target = expense.category.name if expense.category else "Uncategorised"
    elif field == "account":
        account = get_object_or_404(Account, pk=value)
        if account.is_nemkonto:
            return JsonResponse(
                {"ok": False, "error": "Expenses cannot use the NemKonto."}, status=400
            )
        previous = expense.account
        expense.account = account
        expense.save(update_fields=["account", "updated_at"])
        target = account.name
        note = _balance_move_note(expense, previous, account)
        if note:
            if request.headers.get("Accept", "").startswith("application/json"):
                return JsonResponse({"ok": True, "message": note})
            messages.warning(request, note)
    else:
        return JsonResponse({"ok": False, "error": "Unknown field."}, status=400)
    if request.headers.get("Accept", "").startswith("application/json"):
        return JsonResponse({"ok": True, "message": f"{expense.name} moved to {target}."})
    messages.success(request, f"{expense.name} moved to {target}.")
    return redirect(_safe_next(request, "expenses"))


@require_POST
def expense_release(request, pk: int):
    """Move (part of) an expense's balance to General Savings at the next month-end."""
    expense = get_object_or_404(Expense, pk=pk)
    month = services.next_close_month()
    close = services.start_draft(month, request.user)
    if "cancel" in request.POST:
        close.decisions.filter(expense=expense, kind=Decision.Type.RELEASE).delete()
        messages.success(request, "Cancelled.")
        return redirect("expense-detail", pk=pk)
    form = ReleaseForm(request.POST)
    state = services.build_state()
    balance = state.current_expense_balances()[expense.id]
    if form.is_valid():
        amount = form.cleaned_data["amount"]
        if not amount or amount > balance:
            messages.error(request, "Enter an amount up to the current balance.")
        else:
            try:
                Decision.objects.update_or_create(
                    close=close,
                    expense=expense,
                    kind=Decision.Type.RELEASE,
                    defaults={"amount": amount},
                )
            except IntegrityError:
                messages.error(request, "Could not save. Try again.")
            else:
                messages.success(
                    request,
                    f"The amount moves to General Savings at the month-end on "
                    f"{(month - 1).last_day():%d %b %Y}.",
                )
    else:
        messages.error(request, " ".join(form.errors.get("amount", ["Enter an amount."])))
    return redirect("expense-detail", pk=pk)


# --- Income -------------------------------------------------------------------------------------


def income_list(request):
    month = services.next_close_month()
    sources = []
    for source in IncomeSource.objects.all():
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
    source = get_object_or_404(IncomeSource, pk=pk) if pk else IncomeSource()
    initial = {} if pk else {"first_month": services.next_close_month().first_day()}
    form = IncomeSourceForm(request.POST or None, instance=source, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"Saved {item.name}.")
        return redirect("income")
    return render(request, "ledger/income/form.html", {"form": form, "source": source})


def income_delete(request, pk: int):
    source = get_object_or_404(IncomeSource, pk=pk)
    blocked = None
    if source.entries.filter(month__lt=services.next_close_month().first_day()).exists():
        blocked = "This income has history. Set a last month instead, so past months stay correct."
    if request.method == "POST" and not blocked:
        try:
            source.delete()
        except ProtectedError:
            blocked = "This income is still in use."
        else:
            messages.success(request, f"Deleted {source.name}.")
            return redirect("income")
    return render(
        request,
        "ledger/confirm_delete.html",
        {"object": source, "blocked": blocked, "kind": "income source"},
    )
