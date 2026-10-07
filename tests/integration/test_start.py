from datetime import date

import pytest
from freezegun import freeze_time

from budget_manager.ledger.models import (
    BudgetSettings,
    Expense,
    IncomeSource,
    MonthClose,
    SpendingEntry,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def household(accounts):
    def add(name, amount, first_due, interval, account, kind="fixed"):
        return Expense.objects.create(
            name=name,
            amount=amount * 100,
            interval_months=interval,
            first_due=first_due,
            account=accounts[account],
            kind=kind,
        )

    add("Insurance", 1200, date(2026, 12, 1), 12, "Budget")
    add("Phone", 199, date(2026, 10, 20), 1, "Budget")
    add("Rent", 10000, date(2026, 10, 1), 1, "Budget")
    add("Groceries", 5500, date(2026, 10, 1), 1, "Food", "variable")
    IncomeSource.objects.create(
        name="Salary", amount=2500000, interval_months=1, first_month=date(2026, 11, 1)
    )
    config = BudgetSettings.load()
    config.nemkonto_min, config.nemkonto_max = 200000, 500000
    config.save()


def form(accounts, **values):
    data = {
        f"bank-{accounts['NemKonto'].id}": "4.000",
        f"bank-{accounts['Budget'].id}": "1.500",
        f"bank-{accounts['Food'].id}": "2.000",
        f"bank-{accounts['Savings'].id}": "20.000",
        f"spent-{Expense.objects.get(name='Groceries').id}": "3.200",
    }
    data.update(values)
    return data


@freeze_time("2026-10-07")
def test_starting_mid_month_tops_up_and_evens_out_the_accounts(client, accounts, household):
    page = client.get("/start/")
    assert page.status_code == 200
    text = page.content.decode()
    assert "suggested 1.000,00" in text  # insurance: 100 a month, two transfers left
    assert "first month-end is on 31 October" in text

    preview = client.post("/start/", {**form(accounts), "action": "preview"})
    plan = preview.context["plan"]
    rows = {row.expense.name: row for row in plan.rows}
    assert rows["Rent"].spent == 1000000  # due 1 October, already paid
    assert rows["Phone"].now == 19900  # due 20 October, still to pay
    assert rows["Groceries"].now == 230000
    assert plan.general_savings == 2000100
    assert plan.moves == [("Budget", "Savings", 30100), ("Savings", "Food", 30000)]

    response = client.post("/start/", {**form(accounts), "action": "start"}, follow=True)
    assert "Move 301,00 from Budget to Savings now." in response.content.decode()
    config = BudgetSettings.load()
    assert config.start_month == date(2026, 11, 1)
    assert config.opening_month == date(2026, 10, 1)
    assert config.general_savings_opening == 2000100
    assert config.nemkonto_opening == 400000
    assert Expense.objects.get(name="Insurance").starting_balance == 100000
    assert SpendingEntry.objects.get(expense__name="Groceries").amount == 320000

    # First month-end: October spending (since the start) is entered, then November is paid.
    groceries = Expense.objects.get(name="Groceries")
    phone = Expense.objects.get(name="Phone")
    rent = Expense.objects.get(name="Rent")
    page = client.get("/month-end/2026-11/spending/")
    assert "You started the budget on 7 October" in page.content.decode()
    client.post(
        "/month-end/2026-11/spending/",
        {
            f"spent-{groceries.id}": "5.400",
            f"spent-{phone.id}": "199",
            f"spent-{rent.id}": "10.000",
        },
    )
    client.post(
        "/month-end/2026-11/income/",
        {f"income-{IncomeSource.objects.get().id}": "25.000"},
    )
    client.post("/month-end/2026-11/transfers/", {"action": "continue"})
    client.post("/month-end/2026-11/close/")
    close = MonthClose.objects.get(month=date(2026, 11, 1))
    contributions = {line.expense.name: line.contribution for line in close.lines.all()}
    assert contributions == {
        "Insurance": 10000,
        "Phone": 19900,
        "Rent": 1000000,
        "Groceries": 550000,
    }
    groceries_line = close.lines.get(expense=groceries)
    assert groceries_line.balance_before == 10000  # 5.500 − 5.400
    assert close.nemkonto_before == 400000


@freeze_time("2026-10-07")
def test_start_refuses_when_money_is_missing(client, accounts, household):
    data = form(accounts, **{f"bank-{accounts['Savings'].id}": "0"})
    data[f"bank-{accounts['Food'].id}"] = "0"
    client.post("/start/", {**data, "action": "start"})
    assert BudgetSettings.load().started_on is None


def test_start_is_closed_once_the_budget_runs(client, budget):
    from .test_month_end import month_end

    month_end(client, "2025-05")
    assert client.get("/start/").url == "/"
