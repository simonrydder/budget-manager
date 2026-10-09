"""Forecast and history."""

from __future__ import annotations

from collections import defaultdict

from django.shortcuts import render

from budget_manager.engine import YearMonth
from budget_manager.ledger import services
from budget_manager.ledger.charts import trend_cards
from budget_manager.ledger.models import (
    ContributionLine,
    MonthClose,
    SpendingEntry,
)
from budget_manager.ledger.views.common import today


def forecast(request):
    budget = request.budget
    state = services.build_state(budget)
    points = services.forecast(budget, budget.forecast_months, state=state)
    index = 0
    if selected := request.GET.get("month"):
        try:
            wanted = YearMonth.parse(selected)
        except ValueError:
            wanted = None
        index = next((i for i, p in enumerate(points) if p.month == wanted), 0)
    point = points[index]

    accounts = list(budget.accounts.all())
    expenses = list(budget.expenses.select_related("category"))
    groups = []
    for account in accounts:
        items = [
            {
                "expense": expense,
                "balance": point.expense_balances[expense.id],
                "contribution": point.close.lines[expense.id].contribution,
                "expected": point.close.lines[expense.id].expected_spend,
            }
            for expense in expenses
            if expense.account_id == account.id
            and (point.expense_balances[expense.id] or point.close.lines[expense.id].contribution)
        ]
        groups.append(
            {
                "account": account,
                "balance": point.account_balances[account.id],
                "transfer": point.close.transfers.get(account.id),
                "items": sorted(items, key=lambda item: item["expense"].name.lower()),
            }
        )
    warnings = []
    for p in points:
        for notice in p.close.notices:
            if notice.level != "info":
                warnings.append({"point": p, "notice": notice})
    context = {
        "points": points,
        "point": point,
        "index": index,
        "plan": point.close,
        "groups": groups,
        "previous": points[index - 1] if index > 0 else None,
        "next": points[index + 1] if index + 1 < len(points) else None,
        "trends": trend_cards(points, accounts, marker=index),
        "warnings": warnings[:12],
        "expected_income": point.close.income,
        "everyday": services.everyday_estimate(budget),
    }
    return render(request, "ledger/forecast.html", context)


def history(request):
    budget = request.budget
    now = today()
    years = sorted(
        {budget.start.year, now.year}
        | {
            d.year
            for d in SpendingEntry.objects.filter(expense__budget=budget).dates("month", "year")
        }
    )
    try:
        year = int(request.GET.get("year", now.year))
    except ValueError:
        year = now.year
    by = request.GET.get("by", "category")
    if by not in {"expense", "category", "account"}:
        by = "category"

    spending = services.spending_by_month(budget, year)
    expected: dict[int, int] = defaultdict(int)
    counted = services.completed_spending_months(budget, year)
    for line in ContributionLine.objects.filter(
        close__budget=budget,
        close__status=MonthClose.Status.CLOSED,
        close__month__year=year,
        close__month__month__in=counted,
    ).values("expense_id", "expected_spend"):
        expected[line["expense_id"]] += line["expected_spend"]

    expenses = list(budget.expenses.select_related("category", "account"))
    if by == "expense":
        keys = {e.id: (e.name, e) for e in expenses}
        key_of = {e.id: e.id for e in expenses}
    elif by == "category":
        keys = {c.id: (c.name, c) for c in budget.categories.all()}
        keys[None] = ("Uncategorised", None)
        key_of = {e.id: e.category_id for e in expenses}
    else:
        keys = {a.id: (a.name, a) for a in budget.accounts.all()}
        key_of = {e.id: e.account_id for e in expenses}

    rows: dict = {}
    for expense in expenses:
        key = key_of[expense.id]
        row = rows.setdefault(
            key,
            {"name": keys[key][0], "object": keys[key][1], "months": [0] * 12, "expected": 0},
        )
        for number, amount in spending.get(expense.id, {}).items():
            row["months"][number - 1] += amount
        row["expected"] += expected.get(expense.id, 0)
    table = []
    for row in rows.values():
        row["total"] = sum(row["months"])
        if not row["total"] and not row["expected"]:
            continue
        row["average"] = row["total"] // len(counted) if counted else None
        row["cells"] = [
            {"amount": amount, "counted": number + 1 in counted}
            for number, amount in enumerate(row["months"])
        ]
        table.append(row)
    table.sort(key=lambda row: -row["total"])
    totals = [sum(row["months"][i] for row in table) for i in range(12)]
    grand = sum(totals)
    context = {
        "year": year,
        "years": years,
        "by": by,
        "table": table,
        "totals": [
            {"amount": amount, "counted": i + 1 in counted} for i, amount in enumerate(totals)
        ],
        "grand_total": grand,
        "grand_expected": sum(row["expected"] for row in table),
        "grand_average": grand // len(counted) if counted else None,
        "counted": counted,
        "month_names": [YearMonth(year, m).name[:3] for m in range(1, 13)],
    }
    return render(request, "ledger/history.html", context)
