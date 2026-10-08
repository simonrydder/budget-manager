"""Upgrading a database from before budgets existed."""

from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("ledger", "0006_move")]
AFTER = [("ledger", "0009_budget_required")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.fixture
def old_apps(transactional_db):
    apps = migrate(BEFORE)
    yield apps
    migrate(executor_leaf_nodes())


def executor_leaf_nodes():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


def test_existing_data_becomes_one_shared_budget(old_apps):
    User = old_apps.get_model("auth", "User")
    Settings = old_apps.get_model("ledger", "BudgetSettings")
    Account = old_apps.get_model("ledger", "Account")
    Expense = old_apps.get_model("ledger", "Expense")
    MonthClose = old_apps.get_model("ledger", "MonthClose")
    Move = old_apps.get_model("ledger", "Move")
    alex = User.objects.create(username="alex")
    sam = User.objects.create(username="sam")
    Settings.objects.create(
        start_month=date(2025, 5, 1), nemkonto_min=100, nemkonto_max=500, general_savings_opening=7
    )
    budget_account = Account.objects.create(name="Budget", role="normal")
    Account.objects.create(name="NemKonto", role="nemkonto")
    Account.objects.create(name="Savings", role="savings")
    rent = Expense.objects.create(
        name="Rent", amount=100, first_due=date(2025, 5, 1), account=budget_account
    )
    MonthClose.objects.create(month=date(2025, 5, 1), status="closed")
    Move.objects.create(kind="refund", account=budget_account, amount=10)

    apps = migrate(AFTER)
    Budget = apps.get_model("ledger", "Budget")
    budget = Budget.objects.get()
    assert budget.name == "My budget"
    assert set(budget.members.values_list("username", flat=True)) == {alex.username, sam.username}
    assert (budget.start_month, budget.nemkonto_max, budget.general_savings_opening) == (
        date(2025, 5, 1),
        500,
        7,
    )
    assert budget.setup_step == 5  # it has had a month-end, so the setup is done
    for name in ("Account", "Expense", "MonthClose", "Move"):
        model = apps.get_model("ledger", name)
        assert model.objects.filter(budget=budget).count() == model.objects.count() > 0
    assert apps.get_model("ledger", "Expense").objects.get(pk=rent.pk).budget_id == budget.pk


def test_a_new_installation_starts_without_budgets(old_apps):
    Account = old_apps.get_model("ledger", "Account")
    Category = old_apps.get_model("ledger", "Category")
    Account.objects.create(name="NemKonto", role="nemkonto")
    Category.objects.create(name="House")
    apps = migrate(AFTER)
    assert not apps.get_model("ledger", "Budget").objects.exists()
    assert not apps.get_model("ledger", "Account").objects.exists()
    assert not apps.get_model("ledger", "Category").objects.exists()
