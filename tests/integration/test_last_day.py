"""The month-end reads the bank as it stood at the end of the last day: income that arrived
during the month, standing orders on the last bank day and overdrafts the bank covered."""

from datetime import date

import pytest

from budget_manager.ledger import services
from budget_manager.ledger.models import (
    Account,
    Budget,
    Expense,
    IncomeSource,
    MonthClose,
    Move,
    Transfer,
)

from .test_month_end import expense, month_end

pytestmark = pytest.mark.django_db


def state():
    return services.build_state(Budget.objects.get())


def standing(**amounts):
    for name, amount in amounts.items():
        Account.objects.filter(name=name).update(standing_order=amount)


def overdraft(client, expense_name, source, amount, **extra):
    data = {
        "overdraft-expense": expense(expense_name).id,
        "overdraft-source": Account.objects.get(name=source).id,
        "overdraft-amount": amount,
        **extra,
    }
    return client.post("/balance/overdraft/", data)


def test_the_checklist_starts_with_income(client, budget):
    month_end(client, "2025-05")
    assert client.get("/month-end/").url == client.at("/month-end/2025-06/income/")
    page = client.get("/month-end/2025-06/income/").content.decode()
    assert "Step 1" in page and "June income" in page


def test_nemkonto_spending_follows_from_its_balance_on_the_last_day(client, budget, accounts):
    month_end(client, "2025-05")  # the NemKonto starts June's month-end with 5.000
    standing(Budget=900000, Food=400000)
    salary = IncomeSource.objects.get(name="Salary")
    client.post("/month-end/2025-06/income/", {f"income-{salary.id}": "25.000"})
    client.post("/month-end/2025-06/interest/", {f"interest-{accounts['NemKonto'].id}": "10"})

    page = client.get("/month-end/2025-06/spending/").content.decode()
    # 5.000 + 25.000 income + 10 interest - 13.000 standing orders = 17.010 before spending.
    assert 'data-balance-of="nemkonto-spent" data-start="1701000"' in page
    assert "Balance on 31 May" in page
    # Ascension Day is 29 May 2025 and the banks are closed the day after, so the standing
    # orders left on Wednesday 28 May.
    assert "− Standing orders on 28 May" in page
    day = services.nemkonto_day(budget, state())
    assert day.spent(1401000) == 300000  # the bank shows 14.010: 3.000 was spent


def test_standing_orders_leave_only_the_rest_to_transfer(client, budget):
    # The first month-end sends Budget 10.000 and Food 4.000.
    standing(Budget=1050000, Food=400000)
    month_end(client, "2025-05", close=False)
    page = client.get("/month-end/2025-05/transfers/").content.decode()
    assert "The standing order to Food sent it all" in page
    assert "500,00" in page and "Budget → NemKonto · back from the standing order" in page
    assert "Standing orders were sent on 30 April" in page

    client.post("/month-end/2025-05/close/")
    close = MonthClose.objects.get(month=date(2025, 5, 1))
    rows = {t.account.name: t for t in close.transfers.select_related("account")}
    assert (rows["Food"].amount, rows["Food"].standing_order, rows["Food"].done) == (
        400000,
        400000,
        True,
    )
    assert (rows["Budget"].rest, rows["Budget"].done) == (-50000, False)
    assert rows["Savings"].standing_order == 0
    detail = client.get("/closes/2025-05/").content.decode()
    assert "back from the standing order of 10.500,00" in detail


def test_an_account_with_a_standing_order_and_nothing_to_receive_sends_it_back(client, budget):
    holiday = expense("Holiday")
    holiday.account = Account.objects.get(name="Budget")
    holiday.save()
    standing(Savings=100000)
    month_end(client, "2025-05")
    close = MonthClose.objects.get(month=date(2025, 5, 1))
    savings = Transfer.objects.get(close=close, account__name="Savings")
    assert savings.standing_order == 100000
    assert savings.rest == savings.amount - 100000


def test_an_overdraft_covered_from_general_savings(client, budget):
    month_end(client, "2025-05")
    before = state()
    response = overdraft(client, "Groceries", "Savings", "300")
    assert response.url == client.at("/balance/")
    after = state()
    assert after.general_savings == before.general_savings - 30000
    assert after.nemkonto == before.nemkonto
    groceries = expense("Groceries").id
    assert (
        after.current_expense_balances()[groceries]
        == before.current_expense_balances()[groceries] + 30000
    )
    # Step 3 starts Groceries from what it had plus the cover.
    page = client.get("/month-end/2025-06/spending/").content.decode()
    assert "The bank covered 300,00 for Groceries from Savings" in page
    assert 'aria-label="Balance after for Groceries" data-balance-of' in page
    assert f'data-start="{400000 + 30000}"' in page


def test_an_overdraft_covered_from_the_nemkonto_is_not_everyday_spending(client, budget):
    month_end(client, "2025-05")
    before = state()
    overdraft(client, "Groceries", "NemKonto", "200", **{"overdraft-note": "Card at the shop"})
    after = state()
    assert after.nemkonto == before.nemkonto - 20000
    assert after.general_savings == before.general_savings
    day = services.nemkonto_day(budget, after)
    assert (day.after_close, day.overdrafts) == (500000, 20000)
    page = client.get("/month-end/2025-06/spending/").content.decode()
    assert "− Overdrafts the bank covered from it" in page
    assert 'data-balance-of="nemkonto-spent" data-start="480000"' in page

    # It can be removed again until the next month-end.
    move = Move.objects.get(kind=Move.Type.OVERDRAFT)
    client.post(f"/balance/{move.id}/undo/")
    assert not Move.objects.exists()
    assert state().nemkonto == before.nemkonto


def test_an_overdraft_must_come_from_another_account(client, budget):
    month_end(client, "2025-05")
    response = overdraft(client, "Holiday", "Savings", "100")
    assert response.status_code == 200
    assert b"The money has to come from another account." in response.content
    response = overdraft(client, "Groceries", "Budget", "100")
    assert response.status_code == 200
    assert not Move.objects.exists()


def test_an_overdraft_goes_into_the_next_month_end(client, budget):
    month_end(client, "2025-05")
    overdraft(client, "Groceries", "NemKonto", "200")
    month_end(client, "2025-06", spending={"Groceries": "4.200", "Rent": "10.000"}, nemkonto="0")
    june = MonthClose.objects.get(month=date(2025, 6, 1))
    assert june.nemkonto_before == 480000
    # Groceries spent 4.200 of 4.000 + 200 covered: it needs its usual 4.000 again.
    assert june.lines.get(expense__name="Groceries").contribution == 400000
    # The overdraft is fixed in the past once the month-end is closed.
    assert not client.get("/balance/").context["recent"][0].month == state().month.first_day()


def test_check_warns_about_payments_drawn_after_a_weekend(client, budget, accounts):
    # 31 May 2025 is a Saturday, so the bank draws it on Monday 2 June.
    Expense.objects.create(
        budget=budget,
        name="Streaming",
        amount=12900,
        interval_months=1,
        first_due=date(2025, 5, 31),
        account=accounts["Budget"],
        kind="fixed",
    )
    month_end(client, "2025-05")
    month_end(
        client,
        "2025-06",
        spending={"Rent": "10.000", "Streaming": "129", "Groceries": "4.000"},
        nemkonto="0",
        close=False,
    )
    page = client.get("/month-end/2025-06/check/").content.decode()
    assert "<b>Streaming</b> 129,00 (due Sat 31 May, drawn Mon 2 Jun)" in page
    late = services.late_payments(budget, state().month)
    assert [item.expense.name for item in late] == ["Streaming"]


def test_a_standing_order_is_set_on_the_account(client, budget, accounts):
    food = accounts["Food"]
    response = client.post(
        f"/accounts/{food.id}/edit/", {"name": "Food", "standing_order": "4.000"}
    )
    assert response.status_code == 302
    food.refresh_from_db()
    assert food.standing_order == 400000
    form = client.get(f"/accounts/{accounts['NemKonto'].id}/edit/").context["form"]
    assert "standing_order" not in form.fields
