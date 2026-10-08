from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from budget_manager.ledger import budgets, services
from budget_manager.ledger.models import (
    Account,
    Budget,
    Category,
    ContributionLine,
    Expense,
    MonthClose,
    Move,
    SpendingEntry,
)

from .test_month_end import month_end

pytestmark = pytest.mark.django_db


@pytest.fixture
def sam(db):
    return get_user_model().objects.create_user("sam", password="a-long-password")


@pytest.fixture
def company(sam):
    """A budget only Sam can use."""
    budget = budgets.create_budget("Company", [sam], sam)
    Expense.objects.create(
        budget=budget,
        name="Accountant",
        amount=500000,
        interval_months=12,
        first_due=date(2026, 3, 1),
        account=budget.accounts.get(name="Budget"),
    )
    return budget


def test_people_only_see_their_own_budgets(client, budget, company):
    assert client.get(company.get_absolute_url()).status_code == 404
    assert client.get(f"{company.get_absolute_url()}accounts/").status_code == 404
    page = client.get("/budgets/").content.decode()
    assert "Household" in page and "Company" not in page
    assert client.get(f"/budgets/{company.pk}/copy/").status_code == 404


def test_things_from_another_budget_cannot_be_reached(client, budget, company):
    accountant = company.expenses.get()
    assert client.get(f"/expenses/{accountant.id}/").status_code == 404
    assert client.post(f"/expenses/{accountant.id}/delete/").status_code == 404
    rent = Expense.objects.get(name="Rent")
    other_account = company.accounts.get(name="Food")
    response = client.post(
        f"/expenses/{rent.id}/move/",
        {"field": "account", "value": other_account.id},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 404
    rent.refresh_from_db()
    assert rent.account.budget == budget
    form = client.get("/expenses/new/").context["form"]
    assert other_account not in form.fields["account"].queryset
    assert not set(form.fields["category"].queryset) & set(company.categories.all())


def test_pages_without_a_budget_open_the_last_used_one(budget, user):
    second = budgets.create_budget("Holiday house", [user], user)
    browser = Client()
    browser.force_login(user)
    assert browser.get("/accounts/").url == f"/b/{second.pk}/accounts/"  # the first by name
    browser.get(f"/b/{budget.pk}/")
    assert browser.get("/accounts/?x=1").url == f"/b/{budget.pk}/accounts/?x=1"
    menu = browser.get(f"/b/{budget.pk}/").content.decode()
    assert "Holiday house" in menu and f'href="/b/{second.pk}/"' in menu


def test_someone_without_budgets_is_asked_to_create_one(sam):
    visitor = Client()
    visitor.force_login(sam)
    assert visitor.get("/").url == "/budgets/"
    assert b"You have no budgets yet" in visitor.get("/budgets/").content


def test_a_new_budget_has_the_defaults_and_opens_the_setup(client, budget, user):
    response = client.post("/budgets/new/", {"name": "Company"})
    company = Budget.objects.get(name="Company")
    assert response.url == f"/b/{company.pk}/start/"
    assert list(company.members.all()) == [user]
    assert company.accounts.count() == 4 and company.categories.count() == 8
    assert not company.expenses.exists()
    duplicate = client.post("/budgets/new/", {"name": "household"})
    assert b"You already have a budget called household." in duplicate.content


def test_copying_the_setup_starts_a_fresh_budget(client, budget, user):
    month_end(client, "2025-05")
    rent = Expense.objects.get(name="Rent")
    Expense.objects.create(
        budget=budget,
        name="Old gym",
        amount=30000,
        first_due=date(2025, 1, 1),
        end_date=date(2025, 4, 30),
        account=rent.account,
    )
    response = client.post(
        f"/budgets/{budget.pk}/copy/",
        {"name": "Next year", "what": "setup", "members": [user.id]},
    )
    copy = Budget.objects.get(name="Next year")
    assert response.url == f"/b/{copy.pk}/start/"
    assert sorted(copy.expenses.values_list("name", flat=True)) == ["Groceries", "Holiday", "Rent"]
    copied_rent = copy.expenses.get(name="Rent")
    assert copied_rent.account.budget == copy and copied_rent.category.budget == copy
    assert copied_rent.category.name == "House"
    assert copied_rent.starting_balance == 0 and copied_rent.start_month is None
    assert copy.incomes.get().name == "Salary"
    assert not copy.closes.exists()
    assert not services.budget_started(copy)
    assert (copy.nemkonto_min, copy.nemkonto_max) == (budget.nemkonto_min, budget.nemkonto_max)
    # The original is untouched.
    assert budget.expenses.count() == 4 and budget.closes.count() == 1


def test_copying_everything_gives_an_identical_independent_budget(client, budget, user):
    month_end(client, "2025-05")
    month_end(client, "2025-06", spending={"Rent": "10.000", "Groceries": "4.100"})
    client.post("/balance/", {"amount": "350", "account": Account.objects.get(name="Budget").id})
    client.post("/balance/made/")
    client.post("/accounts/correct/nemkonto/", {"amount": "-25", "note": "Fee"})
    client.post(
        f"/budgets/{budget.pk}/copy/",
        {"name": "Try-out", "what": "everything", "members": [user.id]},
    )
    copy = Budget.objects.get(name="Try-out")
    original, copied = services.build_state(budget), services.build_state(copy)
    assert copied.month == original.month
    assert (copied.nemkonto, copied.general_savings) == (
        original.nemkonto,
        original.general_savings,
    )
    names = {e.id: e.name for e in Expense.objects.all()}
    assert {names[k]: v for k, v in copied.current_expense_balances().items()} == {
        names[k]: v for k, v in original.current_expense_balances().items()
    }
    assert ContributionLine.objects.filter(close__budget=copy).count() == 6
    assert SpendingEntry.objects.filter(expense__budget=copy).count() == 2
    assert Move.objects.filter(budget=copy, done=True).count() == 1
    done = copy.closes.get(month=date(2025, 5, 1)).transfers.values_list(
        "account__budget", flat=True
    )
    assert set(done) == {copy.pk}

    # Changing the copy leaves the original alone.
    copied_rent = copy.expenses.get(name="Rent")
    copied_rent.amount = 1
    copied_rent.save()
    assert Expense.objects.get(budget=budget, name="Rent").amount == 1000000


def test_deleting_a_budget_needs_its_name(client, budget, user):
    month_end(client, "2025-05")
    client.post("/balance/", {"amount": "350", "account": Account.objects.get(name="Budget").id})
    other = budgets.create_budget("Company", [user], user)
    response = client.post("/settings/delete/", {"confirm": "household"})
    assert b"Type Household exactly." in response.content
    assert Budget.objects.filter(pk=budget.pk).exists()
    response = client.post("/settings/delete/", {"confirm": "Household"})
    assert response.url == "/budgets/"
    assert not Budget.objects.filter(pk=budget.pk).exists()
    assert not Expense.objects.filter(budget_id=budget.pk).exists()
    assert not MonthClose.objects.filter(budget_id=budget.pk).exists()
    assert list(Budget.objects.all()) == [other]
    assert other.accounts.count() == 4 and Category.objects.filter(budget=other).count() == 8


def test_a_budget_can_be_shared_from_its_settings(client, budget, user, sam):
    response = client.post(
        "/settings/",
        {
            "name": "Household",
            "members": [sam.id],
            "nemkonto_min": "2.000",
            "nemkonto_max": "5.000",
            "forecast_months": "24",
        },
    )
    assert response.status_code == 302
    assert set(budget.members.all()) == {user, sam}  # you always keep access yourself
    visitor = Client()
    visitor.force_login(sam)
    assert visitor.get(f"/b/{budget.pk}/").status_code == 200


def test_people_can_be_given_access_when_added(client, budget):
    client.post(
        "/users/",
        {
            "username": "sam",
            "first_name": "Sam",
            "password1": "correct horse battery",
            "password2": "correct horse battery",
            "budgets": [budget.pk],
        },
    )
    sam = get_user_model().objects.get(username="sam")
    assert list(sam.budgets.all()) == [budget]
    page = client.get("/users/").content.decode()
    assert "Household" in page


def test_the_only_person_of_a_budget_cannot_be_deleted(client, budget, company, sam):
    response = client.post(f"/users/{sam.id}/delete/")
    assert response.status_code == 200
    assert b"the only person who can use one of the budgets" in response.content
    assert get_user_model().objects.filter(pk=sam.pk).exists()
