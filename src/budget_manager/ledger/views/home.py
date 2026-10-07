from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator

from budget_manager.engine import Kind, YearMonth
from budget_manager.ledger import services
from budget_manager.ledger.charts import trend_cards
from budget_manager.ledger.forms import NewUserForm
from budget_manager.ledger.models import Account, BudgetSettings, Expense, IncomeSource
from budget_manager.ledger.views.common import today


@login_not_required
def setup(request):
    """Create the first login. Only available while there are no users at all."""
    User = get_user_model()
    if User.objects.exists():
        return redirect("login")
    form = NewUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Start by checking your accounts and settings.")
        return redirect("dashboard")
    return render(request, "registration/setup.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    @method_decorator(login_not_required)
    def dispatch(self, request, *args, **kwargs):
        if not get_user_model().objects.exists():
            return redirect("setup")
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
                "short": max(0, expense.amount - balance),
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["expense"].name))


def budget_warning(state) -> list[dict]:
    warning = services.monthly_balance(state).warning()
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
    state = services.build_state()
    points = services.forecast(12, state=state)
    preview = points[0].close
    balances = state.current_expense_balances()
    account_balances = state.current_account_balances()
    accounts = list(Account.objects.all())
    expenses_by_account = {}
    for expense in Expense.objects.select_related("category"):
        expenses_by_account.setdefault(expense.account_id, []).append(
            {"expense": expense, "balance": balances[expense.id]}
        )
    month = state.month
    transfer_day = (month - 1).last_day()
    draft = services.draft_close(month)
    last = services.last_closed()
    open_transfers = last.transfers.filter(done=False).count() if last else 0
    config = BudgetSettings.load()

    checklist = [
        ("Set the NemKonto minimum and maximum", config.nemkonto_max > 0, "settings"),
        ("Add your expenses", Expense.objects.exists(), "expense-new"),
        ("Add your income", IncomeSource.objects.exists(), "income-new"),
        (
            "Start the budget with today's account balances",
            config.started_on is not None or last is not None,
            "start",
        ),
        ("Do your first month-end", last is not None, "month-end"),
    ]
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
        "set_aside": sum(balances.values()),
        "upcoming": upcoming_payments(state, balances),
        "attention": budget_warning(state) + attention(points, state, balances),
        "trends": trend_cards(points, accounts),
        "checklist": checklist,
        "setup_done": all(done for _, done, _ in checklist),
        "transfer_total": sum(t.amount for t in preview.transfers.values() if t.amount > 0),
    }
    return render(request, "ledger/dashboard.html", context)
