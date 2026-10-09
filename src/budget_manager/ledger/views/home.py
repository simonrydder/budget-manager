from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from budget_manager.engine import Kind, YearMonth
from budget_manager.ledger import budgets, services
from budget_manager.ledger.charts import trend_cards
from budget_manager.ledger.forms import NewUserForm
from budget_manager.ledger.scope import budget_free, budget_reverse
from budget_manager.ledger.views.common import today
from budget_manager.ledger.views.setup import STEPS as SETUP_STEPS


@budget_free
@login_not_required
def first_login(request):
    """Create the first login. Only available while there are no users at all."""
    User = get_user_model()
    if User.objects.exists():
        return redirect("login")
    form = NewUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        budget = budgets.give_access(user)
        messages.success(request, "Welcome! Set up your budget step by step.")
        return redirect(budget_reverse(budget.pk, "start"))
    return render(request, "registration/setup.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    @method_decorator(login_not_required)
    def dispatch(self, request, *args, **kwargs):
        if not get_user_model().objects.exists():
            return redirect("first-login")
        return super().dispatch(request, *args, **kwargs)


def upcoming_payments(state, balances, days: int = 60) -> list[dict]:
    start = today()
    end = start + timedelta(days=days)
    rows = []
    for ledger in state.ledgers:
        expense = ledger.expense
        due = expense.schedule.next_due_from(start)
        if due is None or due > end or YearMonth.of(due) < expense.start_month:
            continue
        balance = balances[expense.id]
        rows.append(
            {
                "date": due,
                "expense": expense,
                "balance": balance,
                "amount": expense.amount_on(due),
                "short": max(0, expense.amount_on(due) - balance),
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["expense"].name))


def budget_warning(budget, state) -> list[dict]:
    warning = services.monthly_balance(budget, state).warning()
    if not warning:
        return []
    return [{"level": "warning", "message": warning, "when": None, "is_next": True}]


def attention(points, state, balances) -> list[dict]:
    """Notices worth showing: the next month-end first, then the first time each warning
    appears in the forecast."""
    items = []
    seen = set()
    for index, point in enumerate(points):
        for notice in point.close.notices:
            if notice.level == "info" and index > 0:
                continue
            key = (notice.code, notice.expense_id)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "level": notice.level,
                    "message": notice.message,
                    "when": point.close.transfer_date,
                    "is_next": index == 0,
                }
            )
    for ledger in state.ledgers:
        expense = ledger.expense
        if expense.kind is Kind.FIXED and balances[expense.id] < 0:
            if ("fixed_topped_up", expense.id) not in seen:
                items.append(
                    {
                        "level": "info",
                        "message": f"{expense.name} is below zero. General Savings will cover it "
                        "at the next month-end.",
                        "when": None,
                        "is_next": True,
                    }
                )
    order = {"danger": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda item: (order[item["level"]], not item["is_next"]))


def dashboard(request):
    budget = request.budget
    if not services.budget_started(budget):
        return _setup_overview(request, budget)
    state = services.build_state(budget)
    points = services.forecast(budget, 12, state=state)
    preview = points[0].close
    balances = state.current_expense_balances()
    account_balances = state.current_account_balances()
    accounts = list(budget.accounts.all())
    expenses_by_account = {}
    for expense in budget.expenses.select_related("category"):
        expenses_by_account.setdefault(expense.account_id, []).append(
            {"expense": expense, "balance": balances[expense.id]}
        )
    month = state.month
    transfer_day = (month - 1).last_day()
    draft = services.draft_close(budget, month)
    last = services.last_closed(budget)
    open_transfers = last.transfers.filter(done=False).count() if last else 0
    context = {
        "state": state,
        "preview": preview,
        "month": month,
        "transfer_day": transfer_day,
        "days_left": (transfer_day - today()).days,
        "days_ago": (today() - transfer_day).days,
        "draft": draft,
        "last": last,
        "open_transfers": open_transfers,
        "accounts": [
            {
                "account": account,
                "balance": account_balances[account.id],
                "items": sorted(
                    expenses_by_account.get(account.id, []),
                    key=lambda item: -abs(item["balance"]),
                ),
            }
            for account in accounts
        ],
        "general_savings": state.general_savings,
        "nemkonto": state.nemkonto,
        "nemkonto_bank": account_balances[state.nemkonto_account.id],
        "everyday": state.everyday_spending,
        "set_aside": sum(balances.values()),
        "upcoming": upcoming_payments(state, balances),
        "attention": budget_warning(budget, state) + attention(points, state, balances),
        "trends": trend_cards(points, accounts),
        "start_transfers": budget.start_transfers,
        "balancing": services.balancing(budget, today(), state),
        "transfer_total": sum(t.amount for t in preview.transfers.values() if t.amount > 0),
    }
    return render(request, "ledger/dashboard.html", context)


def _setup_overview(request, budget):
    """Until the budget is started, the overview shows how far the setup has come."""
    reached = min(budget.setup_step, 5)
    steps = [
        {"number": number, "label": label, "slug": slug, "done": number < reached}
        for number, slug, label, _ in SETUP_STEPS
    ]
    context = {
        "steps": steps,
        "reached": reached,
        "next_step": steps[reached - 1],
        "counts": {
            "accounts": budget.accounts.count(),
            "expenses": budget.expenses.count(),
            "incomes": budget.incomes.count(),
        },
    }
    return render(request, "ledger/dashboard_setup.html", context)


@require_POST
def start_transfers_done(request):
    """The bank transfers that even out the accounts after starting have been made."""
    budget = request.budget
    budget.start_transfers = []
    budget.save(update_fields=["start_transfers"])
    messages.success(request, "Good. The accounts now match the budget.")
    return redirect("dashboard")
