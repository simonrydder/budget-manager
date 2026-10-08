"""Budget settings and the people who can log in."""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import get_object_or_404, redirect, render

from budget_manager.engine import CloseError, format_amount, format_input
from budget_manager.ledger import services
from budget_manager.ledger.forms import NewUserForm, SettingsForm
from budget_manager.ledger.models import Account, BudgetSettings, Expense
from budget_manager.ledger.views.common import read_amounts


def settings_view(request):
    config = BudgetSettings.load()
    started = services.last_closed() is not None
    form = SettingsForm(request.POST or None, instance=config, started=started)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "ledger/settings.html", {"form": form, "started": started})


def start_budget(request):
    """Start the budget from today's balances ("top up all")."""
    if services.last_closed() is not None:
        messages.info(request, "The budget is already running.")
        return redirect("dashboard")
    today = date.today()
    accounts = list(Account.objects.all())
    expenses = list(Expense.objects.all())
    errors = {}
    bank = set_aside = spent = None
    if request.method == "POST":
        bank, errors_bank = read_amounts(request.POST, "bank-", [a.id for a in accounts])
        set_aside, errors_aside = read_amounts(request.POST, "aside-", [e.id for e in expenses])
        spent, errors_spent = read_amounts(request.POST, "spent-", [e.id for e in expenses])
        errors = {
            **{f"bank-{k}": v for k, v in errors_bank.items()},
            **{f"aside-{k}": v for k, v in errors_aside.items()},
            **{f"spent-{k}": v for k, v in errors_spent.items()},
        }
    plan = services.plan_start(today, bank, set_aside, spent)
    if request.method == "POST" and request.POST.get("action") == "start" and not errors:
        try:
            services.apply_start(plan, request.user)
        except CloseError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"The budget is started. Its first month-end is on "
                f"{plan.opening.last_day():%d %B}.",
            )
            for source, target, amount in plan.moves:
                messages.warning(
                    request, f"Move {format_amount(amount)} from {source} to {target} now."
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

    for item in plan.accounts:
        item.field = field(f"bank-{item.account.id}", item.bank)
    for row in plan.rows:
        row.aside_field = field(f"aside-{row.expense.id}", row.set_aside)
        row.spent_field = field(f"spent-{row.expense.id}", row.spent or None)
    context = {"plan": plan, "errors": errors, "has_expenses": bool(expenses)}
    return render(request, "ledger/start.html", context)


def user_list(request):
    User = get_user_model()
    form = NewUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.username} can now log in.")
        return redirect("users")
    users = User.objects.order_by("username")
    return render(request, "ledger/users/list.html", {"form": form, "users": users})


def user_password(request, pk: int):
    user = get_object_or_404(get_user_model(), pk=pk)
    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if user == request.user:
            update_session_auth_hash(request, user)
        messages.success(request, f"Password changed for {user.username}.")
        return redirect("users")
    return render(request, "ledger/users/password.html", {"form": form, "person": user})


def user_delete(request, pk: int):
    user = get_object_or_404(get_user_model(), pk=pk)
    blocked = "You cannot delete yourself." if user == request.user else None
    if request.method == "POST" and not blocked:
        user.delete()
        messages.success(request, f"{user.username} can no longer log in.")
        return redirect("users")
    return render(
        request, "ledger/confirm_delete.html", {"object": user, "blocked": blocked, "kind": "user"}
    )
