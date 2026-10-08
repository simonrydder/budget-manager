from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from budget_manager.ledger import budgets
from budget_manager.ledger.models import Expense, IncomeSource
from budget_manager.ledger.scope import budget_url

# Pages that do not belong to one budget.
GLOBAL_PAGES = ("/b/", "/login/", "/logout/", "/setup/", "/budgets/", "/users/", "/static/")


class BudgetClient(Client):
    """A logged-in browser looking at one budget. Like the app's own links, requests for a
    budget's pages (``/accounts/``) go to that budget (``/b/<id>/accounts/``)."""

    budget = None

    def at(self, path: str) -> str:
        """Where ``path`` lives inside the budget, e.g. to compare with a redirect."""
        return budget_url(self.budget.pk, path)

    def generic(self, method, path, *args, **kwargs):
        if self.budget is not None and path.startswith("/") and not path.startswith(GLOBAL_PAGES):
            path = self.at(path)
        return super().generic(method, path, *args, **kwargs)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        "alex", password="a-long-password", first_name="Alex"
    )


@pytest.fixture
def household(user):
    """A new budget with the default accounts and categories."""
    return budgets.create_budget("Household", [user], user)


@pytest.fixture
def client(user, household):
    client = BudgetClient()
    client.force_login(user)
    client.budget = household
    return client


@pytest.fixture
def accounts(household):
    return {account.name: account for account in household.accounts.all()}


@pytest.fixture
def budget(household, accounts):
    """Running from May 2025, with a small household."""
    household.start_month = date(2025, 5, 1)
    household.started_on = date(2025, 4, 30)
    household.setup_step = 5
    household.nemkonto_min = 200000
    household.nemkonto_max = 500000
    household.nemkonto_opening = 300000
    household.general_savings_opening = 1000000
    household.save()
    house = household.categories.get(name="House")
    Expense.objects.create(
        budget=household,
        name="Rent",
        amount=1000000,
        interval_months=1,
        first_due=date(2025, 5, 1),
        account=accounts["Budget"],
        category=house,
        kind="fixed",
    )
    Expense.objects.create(
        budget=household,
        name="Groceries",
        amount=400000,
        interval_months=1,
        first_due=date(2025, 5, 1),
        account=accounts["Food"],
        kind="variable",
    )
    Expense.objects.create(
        budget=household,
        name="Holiday",
        amount=3000000,
        interval_months=12,
        first_due=date(2026, 3, 1),
        account=accounts["Savings"],
        kind="fixed",
    )
    IncomeSource.objects.create(
        budget=household,
        name="Salary",
        amount=2500000,
        interval_months=1,
        first_month=date(2025, 5, 1),
    )
    return household
