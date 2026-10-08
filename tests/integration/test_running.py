"""Running budgets: spent bit by bit through the month, possibly straight from the NemKonto."""

from datetime import date

import pytest
from freezegun import freeze_time

from budget_manager.ledger import services
from budget_manager.ledger.models import Expense, MonthClose

from .test_month_end import month_end, transfers
from .test_setup import add_expense, balances

pytestmark = pytest.mark.django_db


def add_everyday(client, accounts, **changes):
    data = {
        "name": "Everyday",
        "amount": "2.000",
        "interval_months": "1",
        "first_due": "",
        "kind": "running",
        "account": accounts["NemKonto"].id,
        **changes,
    }
    return client.post("/expenses/new/", data)


def test_a_running_budget_can_live_on_the_nemkonto(client, budget, accounts):
    response = add_everyday(client, accounts)
    assert response.status_code == 302
    everyday = Expense.objects.get(name="Everyday")
    # Monthly from the first month-end on, no due date needed.
    assert (everyday.interval_months, everyday.first_due) == (1, date(2025, 5, 1))
    assert everyday.start_month == date(2025, 5, 1)

    month_end(client, "2025-05")
    close = MonthClose.objects.get(month=date(2025, 5, 1))
    assert close.lines.get(expense=everyday).contribution == 200000
    assert "NemKonto" not in transfers("2025-05")  # it stays where it is
    # The NemKonto keeps its maximum free, plus the running budget.
    state = services.build_state(budget)
    assert state.nemkonto == 500000
    nemkonto = accounts["NemKonto"]
    assert state.current_account_balances()[nemkonto.id] == 500000 + 200000

    # Spending from it is entered at the month-end like any other expense.
    month_end(client, "2025-06", spending={"Everyday": "2.300"})
    state = services.build_state(budget)
    assert state.current_expense_balances()[everyday.id] == 200000 - 230000 + 200000
    board = client.get("/expenses/?group=account").content.decode()
    assert "Everyday" in board


def test_only_running_budgets_can_use_the_nemkonto(client, budget, accounts):
    response = add_everyday(client, accounts, kind="fixed", first_due="2025-05-10")
    assert response.status_code == 200
    assert "Only running budgets, like everyday spending, can use the NemKonto." in (
        response.content.decode()
    )
    rent = Expense.objects.get(name="Rent")
    response = client.post(
        f"/expenses/{rent.id}/move/",
        {"field": "account", "value": accounts["NemKonto"].id},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 400
    groceries = Expense.objects.get(name="Groceries")
    groceries.kind = "running"
    groceries.save()
    response = client.post(
        f"/expenses/{groceries.id}/move/",
        {"field": "account", "value": accounts["NemKonto"].id},
        HTTP_ACCEPT="application/json",
    )
    assert response.json()["ok"]


def test_bills_need_a_due_date(client, budget, accounts):
    response = add_everyday(client, accounts, kind="variable", account=accounts["Budget"].id)
    assert response.status_code == 200
    assert b"Enter the date it is due next." in response.content


@freeze_time("2026-10-07")
def test_setup_asks_only_running_budgets_what_was_spent(client, household, accounts):
    client.post("/start/accounts/", balances(accounts))
    add_expense(client, accounts, "Rent", "10.000", "2026-10-01")
    add_expense(client, accounts, "Power", "650", "2026-10-05", kind="variable")
    add_expense(client, accounts, "Heating", "900", "2026-10-25", kind="variable")
    add_expense(client, accounts, "Everyday", "2.000", "", account="NemKonto", kind="running")
    add_expense(client, accounts, "Groceries", "5.500", "", account="Food", kind="running")
    assert Expense.objects.get(name="Groceries").first_due == date(2026, 10, 1)
    client.post("/start/expenses/", {"action": "next"})
    client.post("/start/summary/")
    client.post(
        "/start/income/",
        {
            "action": "add",
            "name": "Salary",
            "amount": "25.000",
            "interval_months": "1",
            "first_month": "2026-11",
        },
    )
    client.post("/start/income/", {"action": "next"})

    page = client.get("/start/transfers/")
    text = page.content.decode()
    assert "Already paid: Rent (1 Oct), Power (5 Oct)." in text
    assert "still on the account: Heating (25 Oct)." in text
    for name in ("Rent", "Power", "Heating"):
        assert f'name="spent-{Expense.objects.get(name=name).id}"' not in text
    for name in ("Everyday", "Groceries"):
        assert f'name="spent-{Expense.objects.get(name=name).id}"' in text

    everyday = Expense.objects.get(name="Everyday")
    plan = client.post(
        "/start/transfers/", {"action": "preview", f"spent-{everyday.id}": "500"}
    ).context["plan"]
    # The NemKonto holds 4.000; 1.500 of it is left for everyday spending this month.
    assert plan.nemkonto == 400000 - 150000
