from datetime import date

import pytest
from freezegun import freeze_time

from budget_manager.ledger import services
from budget_manager.ledger.models import (
    Account,
    Expense,
    IncomeSource,
    MonthClose,
    Move,
    SpendingEntry,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def today():
    with freeze_time("2026-10-07"):
        yield


BALANCES = {"NemKonto": "4.000", "Budget": "1.500", "Food": "2.000", "Savings": "20.000"}


def balances(accounts, **changes):
    data = {"action": "save", "nemkonto_min": "2.000", "nemkonto_max": "5.000"}
    for name, value in {**BALANCES, **changes}.items():
        data[f"balance_{accounts[name].id}"] = value
    return data


def add_expense(client, accounts, name, amount, due, interval=1, account="Budget", kind="fixed"):
    return client.post(
        "/start/expenses/",
        {
            "action": "add",
            "name": name,
            "amount": amount,
            "interval_months": interval,
            "first_due": due,
            "account": accounts[account].id,
            "category": "",
            "kind": kind,
        },
    )


def walk_to_transfers(client, accounts):
    """Steps 1 to 4 with a small household."""
    client.post("/start/accounts/", balances(accounts))
    add_expense(client, accounts, "Insurance", "1.200", "2026-12-01", 12)
    add_expense(client, accounts, "Phone", "199", "2026-10-20")
    add_expense(client, accounts, "Rent", "10.000", "2026-10-01")
    add_expense(client, accounts, "Groceries", "5.500", "", account="Food", kind="running")
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


def test_a_new_budget_starts_with_the_setup(client, household):
    page = client.get("/")
    assert b"Set up Household" in page.content
    assert b"Step 1 of 5" in page.content
    assert client.get("/start/").url == client.at("/start/accounts/")
    # Later steps open once the earlier ones are done.
    assert client.get("/start/summary/").url == client.at("/start/accounts/")
    menu = client.get("/start/accounts/").content.decode()
    assert 'Set up <span class="badge">Step 1/5</span>' in menu
    # The month-end waits until the budget is started.
    response = client.get("/month-end/", follow=True)
    assert response.redirect_chain[-1][0] == client.at("/start/accounts/")
    assert b"Set up the budget first" in response.content


def test_step_one_asks_for_every_balance_and_can_add_accounts(client, household, accounts):
    response = client.post("/start/accounts/", balances(accounts, Food=""))
    assert response.status_code == 200
    assert b"Enter the balance, 0 if the account is empty." in response.content

    # Adding an account keeps the balances typed so far.
    data = {**balances(accounts, Food=""), "action": "add", "name": "Car"}
    response = client.post("/start/accounts/", data)
    assert response.status_code == 302
    car = household.accounts.get(name="Car")
    assert car.role == "normal"
    assert household.accounts.get(name="Budget").start_balance == 150000
    duplicate = client.post("/start/accounts/", {**data, "name": "car"})
    assert b"There is already an account called car." in duplicate.content

    response = client.post(
        "/start/accounts/", {**balances(accounts), f"balance_{car.id}": "0"}, follow=True
    )
    assert response.redirect_chain[-1][0] == client.at("/start/expenses/")
    household.refresh_from_db()
    assert (household.nemkonto_min, household.nemkonto_max) == (200000, 500000)
    assert household.balances_on == date(2026, 10, 7)
    assert household.setup_step == 2


def test_step_two_adds_and_removes_expenses(client, household, accounts):
    client.post("/start/accounts/", balances(accounts))
    response = add_expense(client, accounts, "Gym", "300", "2026-10-15", account="Food")
    # The next expense starts with the same account, category and frequency.
    assert response.url.startswith(client.at("/start/expenses/?"))
    assert f"account={accounts['Food'].id}" in response.url
    page = client.get(response.url).content.decode()
    assert "Gym" in page and "next due 15 Oct 2026" in page
    assert "Added <b>Gym</b>" in page  # shown by the form, which the page jumps to
    assert "autofocus" in page  # ready for the next one
    # Each category can be collapsed to its header, which shows what it costs a month.
    assert '<details class="entry-group" open data-remember="setup-group-none">' in page
    assert "≈ <b>300</b> a month" in page
    gym = Expense.objects.get(name="Gym")
    assert gym.budget == household and gym.start_month is None
    client.post("/start/expenses/", {"action": "remove", "expense": gym.id})
    assert not Expense.objects.filter(name="Gym").exists()
    # At least one expense is needed to continue.
    client.post("/start/expenses/", {"action": "next"})
    assert household.__class__.objects.get(pk=household.pk).setup_step == 2


def test_summary_shows_categories_and_the_monthly_total(client, household, accounts):
    client.post("/start/accounts/", balances(accounts))
    house = household.categories.get(name="House")
    add_expense(client, accounts, "Insurance", "1.200", "2026-12-01", 12)
    add_expense(client, accounts, "Rent", "10.000", "2026-11-01")
    Expense.objects.filter(name="Rent").update(category=house)
    add_expense(client, accounts, "New car", "60.000", "2027-10-01", 0, account="Savings")
    client.post("/start/expenses/", {"action": "next"})
    page = client.get("/start/summary/")
    summary = page.context["summary"]
    names = [group.name for group in summary.groups]
    assert names == ["House", "Uncategorised"]
    # Insurance 100 + rent 10.000 + the car spread over 12 months (November to October) 5.000.
    assert summary.monthly == 1510000
    assert b"15.100" in page.content
    assert dict((account.name, amount) for account, amount in summary.accounts) == {
        "Budget": 1010000,
        "Food": 0,
        "Savings": 500000,
    }


def test_the_whole_setup_starts_the_budget_mid_month(client, household, accounts):
    walk_to_transfers(client, accounts)
    page = client.get("/start/income/")
    assert b"Left over for General Savings" in page.content

    page = client.get("/start/transfers/")
    assert page.status_code == 200
    groceries = Expense.objects.get(name="Groceries")
    # Fixed payments follow their due dates; only variable expenses ask what was spent.
    text = page.content.decode()
    assert "Already paid: Rent (1 Oct)." in text
    assert "so the money is still on the account: Phone (20 Oct)." in text
    assert f'name="spent-{groceries.id}"' in text
    rent = Expense.objects.get(name="Rent")
    assert f'name="spent-{rent.id}"' not in text
    preview = client.post(
        "/start/transfers/", {"action": "preview", f"spent-{groceries.id}": "3.200"}
    )
    plan = preview.context["plan"]
    rows = {row.expense.name: row for row in plan.rows}
    assert rows["Insurance"].suggested == 100000  # 100 a month, two transfers left
    assert rows["Rent"].spent == 1000000  # due 1 October, already paid
    assert rows["Phone"].now == 19900  # due 20 October, still to pay
    assert rows["Groceries"].now == 230000
    assert plan.general_savings == 2000100
    assert plan.moves == [("Budget", "Savings", 30100), ("Savings", "Food", 30000)]
    # The first month-end: insurance 100, phone 199 and rent on Budget; groceries on Food. The
    # NemKonto keeps its maximum and the rest goes to General Savings.
    first = preview.context["preview"]
    sent = {t["account"].name: t["plan"] for t in preview.context["first_transfers"]}
    assert sent["Budget"].amount == 10000 + 19900 + 1000000
    assert sent["Food"].amount == 550000
    assert sent["Savings"].general_savings == 400000 + 2500000 - 1579900 - 500000
    assert first.nemkonto_end == 500000
    assert b"Your first month-end, 31 October" in preview.content

    response = client.post(
        "/start/transfers/",
        {"action": "start", f"spent-{groceries.id}": "3.200"},
        follow=True,
    )
    assert response.redirect_chain[-1][0] == client.at("/")
    text = response.content.decode()
    assert "Finish starting: even out the accounts" in text
    assert "301,00</b> Budget → Savings" in text
    household.refresh_from_db()
    assert household.start_month == date(2026, 11, 1)
    assert household.opening_month == date(2026, 10, 1)
    assert household.started_on == date(2026, 10, 7)
    assert household.general_savings_opening == 2000100
    assert household.nemkonto_opening == 400000
    assert Expense.objects.get(name="Insurance").starting_balance == 100000
    assert SpendingEntry.objects.get(expense__name="Groceries").amount == 320000
    assert Account.objects.get(budget=household, name="Food").start_balance == 200000

    client.post("/done-starting/")
    household.refresh_from_db()
    assert household.start_transfers == []

    # Until the first month-end the setup can be done again, starting from what was chosen.
    again = client.get("/start/transfers/")
    assert b"Start again" in again.content
    plan = again.context["plan"]
    assert {row.expense.name: row.spent for row in plan.rows}["Groceries"] == 320000
    assert plan.moves == [("Budget", "Savings", 30100), ("Savings", "Food", 30000)]

    # First month-end: October spending (since the start) is entered, then November is paid.
    phone = Expense.objects.get(name="Phone")
    rent = Expense.objects.get(name="Rent")
    page = client.get("/month-end/2026-11/spending/")
    assert "You started the budget on 7 October" in page.content.decode()
    assert "it had 4.000,00 when you started the budget on 7 October" in page.content.decode()
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
    assert close.lines.get(expense=groceries).balance_before == 10000  # 5.500 − 5.400
    assert close.nemkonto_before == 400000

    # Now the budget runs and the setup is closed.
    assert client.get("/start/").url == client.at("/")
    assert b"Set up" not in client.get("/accounts/").content.split(b"<main")[0]


def test_start_refuses_when_money_is_missing(client, household, accounts):
    walk_to_transfers(client, accounts)
    client.post("/start/accounts/", balances(accounts, Food="0", Savings="0"))
    page = client.get("/start/transfers/")
    assert b"less than the expenses should have by now" in page.content
    client.post("/start/transfers/", {"action": "start"})
    household.refresh_from_db()
    assert household.started_on is None


def test_old_balances_are_pointed_out(client, household, accounts):
    walk_to_transfers(client, accounts)
    with freeze_time("2026-10-09"):
        page = client.get("/start/transfers/")
    assert b"The balances were entered on 7 October" in page.content


def test_categories_can_be_added_renamed_and_removed_in_the_setup(client, household, accounts):
    client.post("/start/accounts/", balances(accounts))
    response = client.post("/start/expenses/", {"action": "add_category", "category-name": "Pets"})
    assert response.url == client.at("/start/expenses/") + "#categories"
    pets = household.categories.get(name="Pets")
    form = client.get("/start/expenses/").context["form"]
    assert pets in form.fields["category"].queryset
    duplicate = client.post("/start/expenses/", {"action": "add_category", "category-name": "pets"})
    assert b"There is already a category called pets." in duplicate.content

    add_expense(client, accounts, "Vet", "1.500", "2027-02-01", 12)
    Expense.objects.filter(name="Vet").update(category=pets)
    setup = client.at("/start/expenses/")
    response = client.post(
        f"/categories/{pets.id}/edit/", {"name": "Animals", "next": setup + "#categories"}
    )
    assert response.url == setup + "#categories"
    response = client.post(
        "/start/expenses/", {"action": "remove_category", "category": pets.id}, follow=True
    )
    assert b"Removed Animals. Its 1 expense is now uncategorised." in response.content
    assert Expense.objects.get(name="Vet").category is None
    assert not household.categories.filter(pk=pets.pk).exists()


def test_a_next_payment_that_covers_two_months(client, household, accounts):
    """Starting on 7 October with a subscription of 1.000 a month whose payment on 1 November
    covers October and November."""
    walk_to_transfers(client, accounts)
    data = {
        "action": "add",
        "name": "Streaming",
        "amount": "1.000",
        "interval_months": 1,
        "first_due": "2026-11-01",
        "first_amount": "2.000",
        "account": accounts["Budget"].id,
        "category": "",
        "kind": "fixed",
    }
    client.post("/start/expenses/", data)
    streaming = Expense.objects.get(name="Streaming")
    assert (streaming.amount, streaming.first_amount) == (100000, 200000)
    assert "next due 1 Nov 2026 (2.000)" in client.get("/start/expenses/").content.decode()

    preview = client.post("/start/transfers/", {"action": "preview"})
    rows = {row.expense.name: row for row in preview.context["plan"].rows}
    # The extra 1.000 is set aside from General Savings now, so the transfer stays 1.000.
    assert rows["Streaming"].set_aside == 100000
    line = preview.context["preview"].lines[streaming.id]
    assert (line.contribution, line.expected_spend) == (100000, 200000)

    # A running budget, or the same amount, has no separate first payment.
    client.post("/start/expenses/", {**data, "name": "Fuel", "kind": "running", "first_due": ""})
    assert Expense.objects.get(name="Fuel").first_amount is None
    client.post("/start/expenses/", {**data, "name": "Gym", "first_amount": "1.000"})
    assert Expense.objects.get(name="Gym").first_amount is None


def test_a_running_budget_ignores_the_hidden_due_date(client, household, accounts):
    """Choosing Running hides the due date, but a date typed before still comes along."""
    walk_to_transfers(client, accounts)
    add_expense(client, accounts, "Fuel", "900", "2026-11-01", account="Food", kind="running")
    fuel = Expense.objects.get(name="Fuel")
    assert fuel.first_due == date(2026, 10, 1)  # it covers October, whose money is on Food

    # One saved with November before this was fixed is moved back in step 5, so October's
    # spending is asked and the first month-end refills it.
    Expense.objects.filter(pk=fuel.pk).update(first_due=date(2026, 11, 1))
    page = client.post("/start/transfers/", {"action": "preview", f"spent-{fuel.id}": "300"})
    fuel.refresh_from_db()
    assert fuel.first_due == date(2026, 10, 1)
    assert f'name="spent-{fuel.id}"' in page.content.decode()
    assert page.context["preview"].lines[fuel.id].contribution == 90000


def test_starting_makes_the_setup_the_ground_truth(client, household, accounts):
    """Nothing waits under Balance after Start: today's bank balances already hold it all."""
    walk_to_transfers(client, accounts)
    rent = Expense.objects.get(name="Rent")
    # No top-ups while setting up: the setup decides what each expense has.
    form = client.get(f"/expenses/{rent.id}/edit/").context["form"]
    assert "topup" not in form.fields
    Move.objects.create(budget=household, kind=Move.Type.TOPUP, expense=rent, amount=50000)
    # An expense that has already ended needs nothing set aside.
    Expense.objects.filter(name="Phone").update(end_date=date(2026, 10, 5))
    groceries = Expense.objects.get(name="Groceries")
    response = client.post(
        "/start/transfers/", {"action": "start", f"spent-{groceries.id}": "3.200"}, follow=True
    )
    assert response.redirect_chain[-1][0] == client.at("/")
    assert not Move.objects.filter(budget=household).exists()
    assert Expense.objects.get(name="Phone").starting_balance == 0
    assert client.get("/balance/").context["plan"].moves == []


def test_starting_again_sets_aside_the_steady_amount(client, household, accounts):
    """The money moved when starting is what keeps every transfer the same from the first
    month-end on, also when starting again after an earlier start set aside less."""
    walk_to_transfers(client, accounts)
    groceries = Expense.objects.get(name="Groceries")
    client.post("/start/transfers/", {"action": "start", f"spent-{groceries.id}": "3.200"})
    insurance = Expense.objects.get(name="Insurance")
    Expense.objects.filter(pk=insurance.pk).update(starting_balance=0)  # e.g. an older start

    page = client.get("/start/transfers/")
    assert b"Adjust what each expense had" not in page.content
    rows = {row.expense.name: row for row in page.context["plan"].rows}
    assert rows["Insurance"].set_aside == rows["Insurance"].suggested == 100000
    budget_line = next(t for t in page.context["first_transfers"] if t["account"].name == "Budget")
    # Insurance 100, phone 199 and rent 10.000: the transfer is the usual monthly amount.
    assert budget_line["plan"].contributions == budget_line["usual"] == 1029900
    assert "Usually about 10.299 a month" in page.content.decode()
    client.post("/start/transfers/", {"action": "start", f"spent-{groceries.id}": "3.200"})
    insurance.refresh_from_db()
    assert insurance.starting_balance == 100000


def test_starting_again_follows_a_moved_due_date(client, household, accounts):
    """A bill paid earlier this month at the first start, whose next due date is then moved to
    next month, is no longer paid this month when starting again (it was set aside nothing)."""
    walk_to_transfers(client, accounts)
    groceries = Expense.objects.get(name="Groceries")
    client.post("/start/transfers/", {"action": "start", f"spent-{groceries.id}": "3.200"})
    rent = Expense.objects.get(name="Rent")
    assert SpendingEntry.objects.get(expense=rent).amount == 1000000  # due 1 October, paid
    Expense.objects.filter(pk=rent.pk).update(first_due=date(2026, 11, 1))

    plan = client.get("/start/transfers/").context["plan"]
    rows = {row.expense.name: row for row in plan.rows}
    assert (rows["Rent"].set_aside, rows["Rent"].spent, rows["Rent"].now) == (0, 0, 0)
    assert rows["Groceries"].spent == 320000  # what was typed for a running budget stays
    client.post("/start/transfers/", {"action": "start", f"spent-{groceries.id}": "3.200"})
    assert not SpendingEntry.objects.filter(expense=rent).exists()
    assert not any(
        balance < 0
        for balance in services.build_state(household).current_expense_balances().values()
    )


def test_step_five_takes_what_is_left_of_a_running_budget(client, household, accounts):
    walk_to_transfers(client, accounts)
    groceries = Expense.objects.get(name="Groceries")
    page = client.get("/start/transfers/").content.decode()
    assert f'data-balance-of="spent-{groceries.id}" data-start="550000"' in page
