from datetime import date

import pytest

from budget_manager.ledger import services
from budget_manager.ledger.models import Expense, MonthClose, Move

from .test_month_end import expense, month_end

pytestmark = pytest.mark.django_db


def general_savings() -> int:
    return services.build_state().general_savings


def balance_of(name: str) -> int:
    return services.build_state().current_expense_balances()[expense(name).id]


def bank_moves(client) -> list[tuple[str, str, int]]:
    plan = client.get("/balance/").context["plan"]
    return [(m.source.name, m.target.name, m.amount) for m in plan.bank_moves]


def test_new_expense_is_filled_from_general_savings_any_day(client, budget, accounts):
    month_end(client, "2025-05")  # the budget is running; next month-end pays for June
    data = {
        "name": "New insurance",
        "amount": "600",
        "interval_months": "12",
        "first_due": "2025-07-07",
        "kind": "fixed",
        "account": accounts["Budget"].id,
    }
    assert b"Fill from General Savings" in client.get("/expenses/new/").content
    client.post("/expenses/new/", {**data, "fill_from_savings": "on"})
    client.post("/expenses/new/", {**data, "name": "Not filled"})
    insurance = expense("New insurance")
    assert Move.objects.get(kind="fund", done=False, expense=insurance).amount == 50000
    assert not Move.objects.filter(expense__name="Not filled").exists()

    # Nothing changes until the transfer is made.
    assert balance_of("New insurance") == 0
    assert bank_moves(client) == [("Savings", "Budget", 50000)]
    before = general_savings()
    assert b"Money waiting to be moved" in client.get("/").content

    client.post("/balance/made/")
    assert balance_of("New insurance") == 50000
    assert general_savings() == before - 50000
    assert not Move.objects.filter(done=False).exists()

    month_end(client, "2025-06")
    june = MonthClose.objects.get(month=date(2025, 6, 1))
    filled = june.lines.get(expense=insurance)
    assert (filled.balance_before, filled.contribution, filled.balance_after) == (
        50000,
        5000,
        55000,
    )
    assert june.lines.get(expense__name="Not filled").contribution == 30000
    month_end(client, "2025-07")
    july = MonthClose.objects.get(month=date(2025, 7, 1))
    assert july.lines.get(expense=insurance).contribution == 5000
    assert july.lines.get(expense__name="Not filled").contribution == 30000


def test_top_up_chosen_while_editing_a_variable_expense(client, budget, accounts):
    month_end(client, "2025-05")
    month_end(client, "2025-06", spending={"Groceries": "8.500"})  # balance -500
    groceries = expense("Groceries")
    page = client.get(f"/expenses/{groceries.id}/edit/")
    assert b"To bring it back to 0, top it up with 500,00" in page.content
    form = {
        "name": "Groceries",
        "amount": "4.000",
        "interval_months": "1",
        "first_due": "2025-05-01",
        "kind": "variable",
        "account": accounts["Food"].id,
        "topup": "500",
    }
    assert client.post(f"/expenses/{groceries.id}/edit/", form).status_code == 302
    assert Move.objects.get(kind="topup", done=False).amount == 50000
    assert bank_moves(client) == [("Savings", "Food", 50000)]
    client.post("/balance/made/")
    assert balance_of("Groceries") == 0

    month_end(client, "2025-07")
    line = MonthClose.objects.get(month=date(2025, 7, 1)).lines.get(expense=groceries)
    assert (line.balance_before, line.topup, line.balance_after) == (0, 0, 400000)

    # Saving without a top-up removes a waiting one.
    client.post(f"/expenses/{groceries.id}/edit/", {**form, "topup": "100"})
    assert Move.objects.filter(kind="topup", done=False).exists()
    client.post(f"/expenses/{groceries.id}/edit/", {**form, "topup": ""})
    assert not Move.objects.filter(kind="topup", done=False).exists()


def test_money_left_on_an_ended_expense_returns_to_general_savings(client, budget, accounts):
    month_end(client, "2025-05")
    old = Expense.objects.create(
        name="Old subscription",
        amount=8900,
        interval_months=1,
        first_due=date(2025, 1, 5),
        end_date=date(2025, 4, 30),
        starting_balance=15000,
        account=accounts["Budget"],
    )
    assert bank_moves(client) == [("Budget", "Savings", 15000)]
    page = client.get(f"/expenses/{old.id}/").content.decode()
    assert "is waiting to move to General Savings because the expense has ended" in page

    # Returning part of it by hand replaces the automatic suggestion.
    client.post(f"/expenses/{old.id}/release/", {"amount": "100"})
    assert bank_moves(client) == [("Budget", "Savings", 10000)]
    client.post(f"/expenses/{old.id}/release/", {"cancel": "1"})

    before = general_savings()
    client.post("/balance/made/")
    assert balance_of("Old subscription") == 0
    assert general_savings() == before + 15000
    assert bank_moves(client) == []


def test_ended_expense_keeps_its_money_until_the_last_payment_is_entered(client, budget):
    month_end(client, "2025-05")
    rent = expense("Rent")
    rent.end_date = date(2025, 6, 2)
    rent.save()
    month_end(client, "2025-06", spending={"Rent": "10.000"})  # sets aside June's rent
    assert balance_of("Rent") == 1000000
    assert bank_moves(client) == []  # June's payment is entered at the next month-end
    month_end(client, "2025-07", spending={"Rent": "10.000"})
    assert balance_of("Rent") == 0
    assert bank_moves(client) == []


def test_refund_goes_to_general_savings(client, budget, accounts):
    month_end(client, "2025-05")
    response = client.post(
        "/balance/",
        {"amount": "350", "account": accounts["Budget"].id, "note": "Insurance surplus"},
    )
    assert response.status_code == 302
    assert bank_moves(client) == [("Budget", "Savings", 35000)]
    before = general_savings()
    client.post("/balance/made/")
    assert general_savings() == before + 35000
    assert b"Insurance surplus" in client.get("/balance/").content

    # Refunds on the savings account need no bank transfer.
    client.post("/balance/", {"amount": "50", "account": accounts["Savings"].id})
    page = client.get("/balance/")
    assert page.context["plan"].bank_moves == []
    assert b"No bank transfer needed" in page.content
    assert (
        client.post("/balance/", {"amount": "0", "account": accounts["Savings"].id}).status_code
        == 200
    )


def test_moves_net_into_one_transfer_per_account(client, budget, accounts):
    month_end(client, "2025-05")
    client.post("/balance/", {"amount": "300", "account": accounts["Budget"].id})
    client.post(f"/expenses/{expense('Rent').id}/release/", {"amount": "1.000"})
    client.post(f"/expenses/{expense('Groceries').id}/release/", {"amount": "200"})
    assert bank_moves(client) == [("Budget", "Savings", 130000), ("Food", "Savings", 20000)]


def test_made_moves_can_be_undone_until_the_next_month_end(client, budget, accounts):
    month_end(client, "2025-05")
    client.post("/balance/", {"amount": "300", "account": accounts["Budget"].id})
    before = general_savings()
    client.post("/balance/made/")
    move = Move.objects.get()
    client.post(f"/balance/{move.id}/undo/")
    assert general_savings() == before
    assert Move.objects.get().done is False
    client.post("/balance/made/")
    month_end(client, "2025-06")
    response = client.post(f"/balance/{move.id}/undo/", follow=True)
    assert b"can no longer be undone" in response.content


def test_the_month_end_waits_for_moves(client, budget, accounts):
    month_end(client, "2025-05")
    client.post("/balance/", {"amount": "300", "account": accounts["Budget"].id})
    response = month_end(client, "2025-06", close=False)
    assert response.url == "/month-end/2025-06/check/"
    assert b"still waiting" in client.get("/month-end/2025-06/check/").content
    response = client.post("/month-end/2025-06/close/", follow=True)
    assert b"Make those transfers" in response.content
    assert not MonthClose.objects.get(month=date(2025, 6, 1)).is_closed
    client.post(f"/balance/{Move.objects.get().id}/cancel/")
    client.post("/month-end/2025-06/close/")
    assert MonthClose.objects.get(month=date(2025, 6, 1)).is_closed


def test_moves_need_enough_general_savings(client, budget, accounts):
    month_end(client, "2025-05")
    rent = expense("Rent")
    Move.objects.create(kind="topup", expense=rent, account=rent.account, amount=10**9)
    response = client.post("/balance/made/", follow=True)
    assert b"too little for these moves" in response.content
    assert not Move.objects.filter(done=True).exists()


def test_moves_wait_until_the_budget_is_started(client, budget, accounts):
    client.post("/balance/", {"amount": "300", "account": accounts["Budget"].id})
    response = client.post("/balance/made/", follow=True)
    assert b"Start the budget before moving money" in response.content
