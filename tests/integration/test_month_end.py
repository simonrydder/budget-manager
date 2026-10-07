from datetime import date

import pytest

from budget_manager.ledger.models import (
    Account,
    BudgetSettings,
    Decision,
    Expense,
    IncomeSource,
    MonthClose,
    Transfer,
)

pytestmark = pytest.mark.django_db


def expense(name: str) -> Expense:
    return Expense.objects.get(name=name)


def transfers(month: str) -> dict[str, int]:
    close = MonthClose.objects.get(month=f"{month}-01")
    return {t.account.name: t.amount for t in close.transfers.select_related("account")}


def month_end(client, month: str, *, spending=None, interest=None, income="25.000", close=True):
    base = f"/month-end/{month}/"
    assert client.get(base + "spending/").status_code == 200
    data = {f"spent-{expense(name).id}": value for name, value in (spending or {}).items()}
    response = client.post(base + "spending/", data)
    assert response.status_code == 302, response.content
    assert response.url == base + "interest/"
    data = {
        f"interest-{Account.objects.get(name=name).id}": value
        for name, value in (interest or {}).items()
    }
    assert client.post(base + "interest/", data).url == base + "income/"
    salary = IncomeSource.objects.get(name="Salary")
    assert client.post(base + "income/", {f"income-{salary.id}": income}).url == base + "transfers/"
    assert client.get(base + "transfers/").status_code == 200
    response = client.post(base + "transfers/", {"action": "continue"})
    if not close:
        return response
    assert response.url == base + "check/"
    assert client.get(base + "check/").status_code == 200
    response = client.post(base + "close/")
    assert response.status_code == 302
    assert response.url == f"/closes/{month}/"
    return response


def test_first_month_end_moves_the_surplus_to_general_savings(client, budget):
    response = client.get("/month-end/", follow=True)
    assert response.redirect_chain[-1][0] == "/month-end/2025-05/spending/"
    assert b"Nothing to enter this time" in response.content

    month_end(client, "2025-05")

    close = MonthClose.objects.get(month=date(2025, 5, 1))
    assert close.is_closed
    assert close.nemkonto_before == 300000
    assert close.surplus == 627200
    assert close.nemkonto_end == 500000
    assert close.general_savings_after == 1627200
    assert transfers("2025-05") == {"Budget": 1000000, "Food": 400000, "Savings": 272800 + 627200}
    assert close.lines.count() == 3
    assert client.get("/closes/2025-05/").status_code == 200


def test_fixed_expense_costing_more_is_topped_up_and_can_be_reopened(client, budget):
    month_end(client, "2025-05")
    month_end(
        client,
        "2025-06",
        spending={"Rent": "10.500,00", "Groceries": "3.900"},
        interest={"Budget": "12,50"},
    )
    line = MonthClose.objects.get(month=date(2025, 6, 1)).lines.get(expense__name="Rent")
    assert line.balance_before == -50000
    assert line.topup == 50000
    assert line.amount_after == 1050000
    assert line.contribution == 1050000
    assert expense("Rent").amount == 1050000
    assert transfers("2025-06") == {
        "Budget": 1050000 + 50000 - 1250,
        "Food": 400000,
        "Savings": 272800 + (778450 - 50000),
    }

    close = MonthClose.objects.get(month=date(2025, 6, 1))
    assert client.get("/closes/2025-06/reopen/").status_code == 200
    response = client.post("/closes/2025-06/reopen/")
    assert response.url == "/month-end/2025-06/transfers/"
    close.refresh_from_db()
    assert not close.is_closed
    assert close.lines.count() == 0
    assert expense("Rent").amount == 1000000

    assert client.post("/month-end/2025-06/transfers/", {"action": "continue"}).status_code == 302
    client.post("/month-end/2025-06/close/")
    assert expense("Rent").amount == 1050000


def test_only_the_latest_month_end_can_be_reopened(client, budget):
    month_end(client, "2025-05")
    month_end(client, "2025-06")
    client.post("/closes/2025-05/reopen/")
    assert MonthClose.objects.get(month=date(2025, 5, 1)).is_closed


def test_shortfall_below_zero_must_be_covered(client, budget):
    budget.general_savings_opening = 0
    budget.save()
    response = month_end(client, "2025-05", income="5.000", close=False)
    assert response.url == "/month-end/2025-05/transfers/"
    page = client.get("/month-end/2025-05/transfers/")
    assert b"Where should the money come from?" in page.content
    assert client.post("/month-end/2025-05/close/").url == "/month-end/2025-05/transfers/"
    assert not MonthClose.objects.filter(status="closed").exists()

    covers = {
        f"cover-{expense('Holiday').id}": "2.728",
        f"cover-{expense('Groceries').id}": "4.000",
        f"cover-{expense('Rent').id}": "2.000",
        "action": "covers",
    }
    client.post("/month-end/2025-05/transfers/", covers)
    assert Decision.objects.filter(kind="cover").count() == 3
    assert client.post("/month-end/2025-05/transfers/", {"action": "continue"}).url.endswith(
        "/check/"
    )
    client.post("/month-end/2025-05/close/")
    close = MonthClose.objects.get(month=date(2025, 5, 1))
    assert close.is_closed
    assert close.nemkonto_end == 0
    assert transfers("2025-05") == {"Budget": 800000}


def test_cover_larger_than_the_balance_is_rejected(client, budget):
    budget.general_savings_opening = 0
    budget.save()
    month_end(client, "2025-05", income="5.000", close=False)
    response = client.post(
        "/month-end/2025-05/transfers/",
        {f"cover-{expense('Holiday').id}": "9.999", "action": "covers"},
    )
    assert response.status_code == 200
    assert b"Enter up to 2.728,00" in response.content
    assert not Decision.objects.exists()


def test_ticking_transfers_is_remembered(client, budget):
    month_end(client, "2025-05", close=False)
    budget_account = Account.objects.get(name="Budget")
    client.post("/month-end/2025-05/transfers/", {"action": "tick", "account": budget_account.id})
    client.post("/month-end/2025-05/close/")
    transfer = Transfer.objects.get(account=budget_account)
    assert transfer.done
    client.post("/closes/2025-05/", {"transfer": transfer.id})
    transfer.refresh_from_db()
    assert not transfer.done


def test_wrong_amounts_are_shown_again(client, budget):
    month_end(client, "2025-05")
    response = client.post(
        "/month-end/2025-06/spending/", {f"spent-{expense('Rent').id}": "ten thousand"}
    )
    assert response.status_code == 200
    assert b"Enter a number" in response.content
    assert b'value="ten thousand"' in response.content


def test_visiting_an_old_or_future_month_redirects(client, budget):
    month_end(client, "2025-05")
    assert client.get("/month-end/2025-05/income/").url == "/closes/2025-05/"
    assert client.get("/month-end/2025-09/income/").url == "/month-end/"
    assert client.get("/month-end/nonsense/income/").status_code == 404


def test_release_moves_an_ended_expense_to_general_savings(client, budget, accounts):
    old = Expense.objects.create(
        name="Old subscription",
        amount=8900,
        interval_months=1,
        first_due=date(2025, 1, 5),
        end_date=date(2025, 4, 30),
        starting_balance=15000,
        account=accounts["Budget"],
    )
    client.post(f"/expenses/{old.id}/release/", {"amount": "150"})
    assert Decision.objects.get(kind="release").amount == 15000
    month_end(client, "2025-05")
    close = MonthClose.objects.get(month=date(2025, 5, 1))
    assert close.lines.get(expense=old).release == 15000
    assert close.general_savings_after == 1627200 + 15000
    assert transfers("2025-05")["Budget"] == 1000000 - 15000


def test_nemkonto_correction_changes_the_next_month_end(client, budget):
    response = client.post("/accounts/correct/nemkonto/", {"amount": "-25,00", "note": "Fee"})
    assert response.status_code == 302
    month_end(client, "2025-05")
    assert MonthClose.objects.get(month=date(2025, 5, 1)).nemkonto_before == 300000 - 2500


def test_correction_after_the_transfers_counts_from_the_next_month_end(client, budget):
    month_end(client, "2025-05", close=False)
    client.post(
        "/accounts/correct/general_savings/",
        {"amount": "100", "note": "Bank bonus", "after": "1"},
    )
    client.post("/month-end/2025-05/close/")
    assert MonthClose.objects.get(month=date(2025, 5, 1)).general_savings_before == 1000000
    month_end(client, "2025-06")
    june = MonthClose.objects.get(month=date(2025, 6, 1))
    assert june.general_savings_before == 1627200 + 10000


def test_settings_are_locked_after_the_first_month_end(client, budget):
    month_end(client, "2025-05")
    client.post(
        "/settings/",
        {
            "start_month": "2024-01",
            "nemkonto_min": "1.000",
            "nemkonto_max": "4.000",
            "nemkonto_opening": "0",
            "general_savings_opening": "0",
            "forecast_months": "12",
        },
    )
    config = BudgetSettings.load()
    assert config.start_month == date(2025, 5, 1)
    assert config.nemkonto_opening == 300000
    assert config.nemkonto_max == 400000


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
    assert Decision.objects.get(kind="topup").amount == 50000
    month_end(client, "2025-07")
    line = MonthClose.objects.get(month=date(2025, 7, 1)).lines.get(expense=groceries)
    assert line.topup == 50000
    assert line.balance_after == 400000

    # Saving without a top-up removes a planned one.
    client.post(f"/expenses/{groceries.id}/edit/", {**form, "topup": "100"})
    client.post(f"/expenses/{groceries.id}/edit/", {**form, "topup": ""})
    assert not Decision.objects.filter(kind="topup", close__status="draft").exists()


def test_new_expense_can_be_filled_from_general_savings(client, budget, accounts):
    month_end(client, "2025-05")  # the budget is running; next month-end pays for June
    data = {
        "name": "New insurance",
        "amount": "600",
        "interval_months": "12",
        "first_due": "2025-07-07",
        "kind": "fixed",
        "account": accounts["Budget"].id,
    }
    page = client.get("/expenses/new/")
    assert b"Fill from General Savings" in page.content
    client.post("/expenses/new/", {**data, "fill_from_savings": "on"})
    client.post("/expenses/new/", {**data, "name": "Not filled"})
    insurance = expense("New insurance")
    assert Decision.objects.get(kind="fund", expense=insurance).amount == 50000
    assert not Decision.objects.filter(expense__name="Not filled").exists()

    month_end(client, "2025-06")
    june = MonthClose.objects.get(month=date(2025, 6, 1))
    filled = june.lines.get(expense=insurance)
    assert (filled.funding, filled.contribution) == (50000, 5000)
    assert june.lines.get(expense__name="Not filled").contribution == 30000

    month_end(client, "2025-07")
    july = MonthClose.objects.get(month=date(2025, 7, 1))
    assert july.lines.get(expense=insurance).contribution == 5000
    assert july.lines.get(expense__name="Not filled").contribution == 30000
