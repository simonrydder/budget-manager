from datetime import date

import pytest
from django.contrib.auth import get_user_model

from budget_manager.ledger.models import Account, BudgetSettings, Category, Expense, IncomeSource


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        "alex", password="a-long-password", first_name="Alex"
    )


@pytest.fixture
def client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def accounts(db):
    return {account.name: account for account in Account.objects.all()}


@pytest.fixture
def budget(db, accounts):
    """Settings starting in May 2025 plus a small household."""
    config = BudgetSettings.load()
    config.start_month = date(2025, 5, 1)
    config.nemkonto_min = 200000
    config.nemkonto_max = 500000
    config.nemkonto_opening = 300000
    config.general_savings_opening = 1000000
    config.save()
    house = Category.objects.get(name="House")
    Expense.objects.create(
        name="Rent",
        amount=1000000,
        interval_months=1,
        first_due=date(2025, 5, 1),
        account=accounts["Budget"],
        category=house,
        kind="fixed",
    )
    Expense.objects.create(
        name="Groceries",
        amount=400000,
        interval_months=1,
        first_due=date(2025, 5, 1),
        account=accounts["Food"],
        kind="variable",
    )
    Expense.objects.create(
        name="Holiday",
        amount=3000000,
        interval_months=12,
        first_due=date(2026, 3, 1),
        account=accounts["Savings"],
        kind="fixed",
    )
    IncomeSource.objects.create(
        name="Salary", amount=2500000, interval_months=1, first_month=date(2025, 5, 1)
    )
    return config
