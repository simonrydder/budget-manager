"""Running budgets (spent bit by bit, like food) and everyday spending from the NemKonto."""

from datetime import date

import pytest
from freezegun import freeze_time

from budget_manager.ledger import services
from budget_manager.ledger.models import Expense, MonthClose

from .test_month_end import expense, month_end
from .test_setup import add_expense, balances

pytestmark = pytest.mark.django_db


def test_everyday_spending_comes_out_of_the_nemkonto(client, budget, accounts):
    budget.everyday_spending = 300000
    budget.save()
    month_end(client, "2025-05")  # the first month-end: nothing spent yet
    may = MonthClose.objects.get(month=date(2025, 5, 1))
    assert may.nemkonto_end == 500000
    assert may.nemkonto_spent is None  # not entered, so it does not count as an average month

    # Before the June month-end: the NemKonto started with 5.000 and 3.600 was spent from it.
    page = client.get("/month-end/2025-06/spending/").content.decode()
    assert "Spent from the NemKonto in May" in page
    assert "it had 5.000,00 after the last month-end" in page
    assert 'data-balance-of="nemkonto-spent" data-start="500000" value="5.000,00"' in page
    month_end(client, "2025-06", nemkonto="3.600")
    june = MonthClose.objects.get(month=date(2025, 6, 1))
    # 1.400 left; 25.000 arrives; 16.728 is transferred: 9.672, so 4.672 goes to General
    # Savings and the NemKonto starts June with its maximum again.
    assert june.nemkonto_spent == 360000
    assert june.nemkonto_after_transfers == 500000 - 360000 + 2500000 - 1672800
    assert (june.surplus, june.nemkonto_end) == (467200, 500000)
    assert "− Spent from it" in client.get("/closes/2025-06/").content.decode()

    # One month recorded: until there are three, the settings amount fills the gap,
    # (3.600 + 3.000 + 3.000) / 3.
    points = services.forecast(budget, 2)
    assert [point.close.nemkonto_spent for point in points] == [320000, 320000]


def test_the_expected_everyday_spending_follows_the_last_six_month_ends(budget):
    budget.everyday_spending = 300000
    budget.save()
    assert services.everyday_estimate(budget).amount == 300000

    def close(month, spent):
        MonthClose.objects.create(
            budget=budget, month=month, status=MonthClose.Status.CLOSED, nemkonto_spent=spent
        )

    # Started on 30 April: the first month-end only covers one day, so it does not count.
    close(date(2025, 5, 1), 10000)
    assert services.everyday_estimate(budget).months == 0
    close(date(2025, 6, 1), 420000)
    estimate = services.everyday_estimate(budget)
    assert (estimate.amount, estimate.months, estimate.from_history) == (340000, 1, False)
    for number, spent in enumerate([200000, 260000, 330000, 280000, 250000, 400000]):
        close(date(2025, 7 + number, 1), spent)
    # The last six: 2.000, 2.600, 3.300, 2.800, 2.500 and 4.000, 2.866,67 rounded to whole kroner. June is too old.
    estimate = services.everyday_estimate(budget)
    assert (estimate.amount, estimate.months, estimate.from_history) == (286700, 6, True)
    # A month-end without the amount (from before it was asked) is skipped.
    close(date(2026, 1, 1), None)
    assert services.everyday_estimate(budget).amount == 286700


def test_the_month_end_warns_when_nemkonto_spending_is_missing(client, budget):
    month_end(client, "2025-05")
    month_end(client, "2025-06", close=False)
    page = client.get("/month-end/2025-06/transfers/").content.decode()
    assert "What was spent from the NemKonto in May is not entered" in page
    client.post("/month-end/2025-06/spending/", {"nemkonto-spent": "0", "stay": "1"})
    page = client.get("/month-end/2025-06/transfers/").content.decode()
    assert "is not entered" not in page


def test_expenses_cannot_use_the_nemkonto(client, budget, accounts):
    form = client.get("/expenses/new/").context["form"]
    assert accounts["NemKonto"] not in form.fields["account"].queryset
    response = client.post(
        "/expenses/new/",
        {
            "name": "Everyday",
            "amount": "2.000",
            "kind": "running",
            "account": accounts["NemKonto"].id,
        },
    )
    assert response.status_code == 200
    assert not Expense.objects.filter(name="Everyday").exists()
    response = client.post(
        f"/expenses/{expense('Groceries').id}/move/",
        {"field": "account", "value": accounts["NemKonto"].id},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 400
    # An expense put on the NemKonto before keeps working, and its form asks to move it.
    old = Expense.objects.create(
        budget=budget,
        name="Pocket money",
        amount=100000,
        first_due=date(2025, 5, 1),
        account=accounts["NemKonto"],
        kind="running",
    )
    month_end(client, "2025-05")
    form = {
        "name": "Pocket money",
        "amount": "1.000",
        "kind": "running",
        "account": accounts["NemKonto"].id,
    }
    response = client.post(f"/expenses/{old.id}/edit/", form)
    assert b"Expenses cannot use the NemKonto." in response.content
    assert "Pocket money" in client.get("/expenses/?group=account").content.decode()


def test_a_running_budget_needs_no_due_date_but_a_bill_does(client, budget, accounts):
    data = {
        "name": "Fuel",
        "amount": "900",
        "interval_months": "3",
        "first_due": "",
        "kind": "running",
        "account": accounts["Budget"].id,
    }
    assert client.post("/expenses/new/", data).status_code == 302
    fuel = Expense.objects.get(name="Fuel")
    # Monthly from the first month-end on.
    assert (fuel.interval_months, fuel.first_due) == (1, date(2025, 5, 1))
    response = client.post("/expenses/new/", {**data, "name": "Power", "kind": "variable"})
    assert b"Enter the date it is due next." in response.content


@freeze_time("2026-10-07")
def test_setup_asks_only_running_budgets_what_was_spent(client, household, accounts):
    data = balances(accounts)
    data["everyday_spending"] = "3.000"
    client.post("/start/accounts/", data)
    household.refresh_from_db()
    assert household.everyday_spending == 300000
    add_expense(client, accounts, "Rent", "10.000", "2026-10-01")
    add_expense(client, accounts, "Power", "650", "2026-10-05", kind="variable")
    add_expense(client, accounts, "Heating", "900", "2026-10-25", kind="variable")
    add_expense(client, accounts, "Groceries", "5.500", "", account="Food", kind="running")
    assert Expense.objects.get(name="Groceries").first_due == date(2026, 10, 1)
    client.post("/start/expenses/", {"action": "next"})
    summary = client.get("/start/summary/").context["summary"]
    assert summary.everyday == 300000
    assert summary.monthly == summary.expenses + 300000
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
    assert f'name="spent-{Expense.objects.get(name="Groceries").id}"' in text
    # The NemKonto keeps today's balance for everyday spending until the month-end, where
    # the rest of October's everyday spending (24 of 31 days) is expected to come out of it.
    plan = page.context["plan"]
    assert plan.nemkonto == 400000
    assert page.context["preview"].nemkonto_spent == 300000 * 24 // 31


def test_spent_and_balance_after_are_both_editable(client, budget):
    """Every spending row has what was spent and the balance after, and typing either one works
    out the other from what the expense had (in app.js). Without JavaScript the balance is only
    shown."""
    month_end(client, "2025-05")
    page = client.get("/month-end/2025-06/spending/").content.decode()
    groceries = expense("Groceries")
    assert "it had 4.000,00" in page
    assert f'data-balance-of="spent-{groceries.id}" data-start="400000" value="4.000,00"' in page
    assert f'data-balance-of="spent-{expense("Rent").id}"' in page
    assert "readonly" in page
