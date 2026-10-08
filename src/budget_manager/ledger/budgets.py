"""Creating, copying and deleting whole budgets."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from budget_manager.engine import YearMonth
from budget_manager.ledger.models import (
    Account,
    BalanceCorrection,
    Budget,
    Category,
    ContributionLine,
    Decision,
    Expense,
    IncomeEntry,
    IncomeSource,
    InterestEntry,
    MonthClose,
    Move,
    SpendingEntry,
    Transfer,
)

DEFAULT_ACCOUNTS = [
    ("NemKonto", "nemkonto"),
    ("Budget", "normal"),
    ("Food", "normal"),
    ("Savings", "savings"),
]
DEFAULT_CATEGORIES = [
    "House",
    "Transport",
    "Insurance",
    "Subscriptions",
    "Children",
    "Food",
    "Entertainment",
    "Savings goals",
]
# Copied as they are when a budget is copied, on top of the name and the people.
SETTINGS = ["nemkonto_min", "nemkonto_max", "forecast_months"]
HISTORY = [
    "start_month",
    "opening_month",
    "started_on",
    "nemkonto_opening",
    "general_savings_opening",
    "setup_step",
    "balances_on",
    "start_transfers",
]


@transaction.atomic
def create_budget(name: str, members, user) -> Budget:
    """A new budget with the default accounts and categories, ready to be set up."""
    budget = Budget.objects.create(name=name, created_by=user)
    budget.members.set(members)
    for order, (account, role) in enumerate(DEFAULT_ACCOUNTS):
        Account.objects.create(budget=budget, name=account, role=role, sort_order=order)
    for order, category in enumerate(DEFAULT_CATEGORIES):
        Category.objects.create(budget=budget, name=category, sort_order=order)
    return budget


def give_access(user) -> Budget | None:
    """For the first person: budgets nobody can use yet become theirs. Returns a budget they can
    use, creating one when there is none."""
    for orphan in Budget.objects.filter(members=None):
        orphan.members.add(user)
    return user.budgets.first() or create_budget("My budget", [user], user)


def _clone(instance, **changes):
    """An unsaved copy of ``instance`` with ``changes`` (by attribute name, e.g. ``budget_id``)."""
    fields = instance._meta.concrete_fields
    values = {f.attname: getattr(instance, f.attname) for f in fields if not f.primary_key}
    values.update(changes)
    return type(instance)(**values)


@transaction.atomic
def copy_budget(source: Budget, name: str, members, user, *, everything: bool) -> Budget:
    """Copy ``source``. Without ``everything`` only what the budget is made of is copied
    (accounts, categories, current expenses and income) and the copy is set up from scratch;
    with it, all month-ends and history come along as well."""
    copied = {field: getattr(source, field) for field in SETTINGS}
    if everything:
        copied.update({field: getattr(source, field) for field in HISTORY})
    budget = Budget.objects.create(name=name, created_by=user, **copied)
    budget.members.set(members)

    accounts = {}
    for account in source.accounts.all():
        start_balance = account.start_balance if everything else None
        accounts[account.pk] = _clone(account, budget_id=budget.pk, start_balance=start_balance)
        accounts[account.pk].save()
    categories = {}
    for category in source.categories.all():
        categories[category.pk] = _clone(category, budget_id=budget.pk)
        categories[category.pk].save()

    today = date.today()
    expenses = {}
    for expense in source.expenses.all():
        if not everything and _finished(expense, today):
            continue
        changes = {
            "budget_id": budget.pk,
            "account_id": accounts[expense.account_id].pk,
            "category_id": categories[expense.category_id].pk if expense.category_id else None,
        }
        if not everything:
            changes.update(starting_balance=0, start_month=None)
        expenses[expense.pk] = _clone(expense, **changes)
        expenses[expense.pk].save()
    incomes = {}
    this_month = YearMonth.of(today).first_day()
    for source_income in source.incomes.all():
        if not everything and source_income.end_month and source_income.end_month < this_month:
            continue
        incomes[source_income.pk] = _clone(source_income, budget_id=budget.pk)
        incomes[source_income.pk].save()
    if everything:
        _copy_history(source, budget, accounts, expenses, incomes)
    return budget


def _finished(expense: Expense, today: date) -> bool:
    if expense.is_ended(today):
        return True
    return expense.interval_months == 0 and expense.first_due < today


def _copy_history(source: Budget, budget: Budget, accounts, expenses, incomes) -> None:
    def account(pk):
        return accounts[pk].pk

    def expense(pk):
        return expenses[pk].pk

    SpendingEntry.objects.bulk_create(
        _clone(entry, expense_id=expense(entry.expense_id))
        for entry in SpendingEntry.objects.filter(expense__budget=source)
    )
    IncomeEntry.objects.bulk_create(
        _clone(entry, source_id=incomes[entry.source_id].pk)
        for entry in IncomeEntry.objects.filter(source__budget=source)
    )
    InterestEntry.objects.bulk_create(
        _clone(entry, account_id=account(entry.account_id))
        for entry in InterestEntry.objects.filter(account__budget=source)
    )
    BalanceCorrection.objects.bulk_create(
        _clone(item, budget_id=budget.pk) for item in source.corrections.all()
    )
    closes = {}
    for close in source.closes.all():
        done = [account(pk) for pk in close.done_accounts or [] if pk in accounts]
        closes[close.pk] = _clone(close, budget_id=budget.pk, done_accounts=done)
        closes[close.pk].save()
    ContributionLine.objects.bulk_create(
        _clone(line, close_id=closes[line.close_id].pk, expense_id=expense(line.expense_id))
        for line in ContributionLine.objects.filter(close__budget=source)
    )
    Transfer.objects.bulk_create(
        _clone(item, close_id=closes[item.close_id].pk, account_id=account(item.account_id))
        for item in Transfer.objects.filter(close__budget=source)
    )
    Decision.objects.bulk_create(
        _clone(item, close_id=closes[item.close_id].pk, expense_id=expense(item.expense_id))
        for item in Decision.objects.filter(close__budget=source)
    )
    Move.objects.bulk_create(
        _clone(
            move,
            budget_id=budget.pk,
            expense_id=expense(move.expense_id) if move.expense_id else None,
            account_id=account(move.account_id) if move.account_id else None,
        )
        for move in source.moves.all()
    )


@transaction.atomic
def delete_budget(budget: Budget) -> None:
    """Delete a budget and everything in it. History is protected against accidental
    deletion, so it is removed in order, newest links first."""
    budget.moves.all().delete()
    Decision.objects.filter(close__budget=budget).delete()
    Transfer.objects.filter(close__budget=budget).delete()
    ContributionLine.objects.filter(close__budget=budget).delete()
    MonthClose.objects.filter(budget=budget).delete()
    Expense.objects.filter(budget=budget).delete()
    IncomeSource.objects.filter(budget=budget).delete()
    budget.corrections.all().delete()
    budget.categories.all().delete()
    budget.accounts.all().delete()
    budget.delete()
