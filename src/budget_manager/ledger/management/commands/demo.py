"""Create a budget with made-up example data, to try the app out."""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budget_manager.engine import YearMonth
from budget_manager.ledger import budgets, services
from budget_manager.ledger.models import (
    Budget,
    Expense,
    IncomeEntry,
    IncomeSource,
    InterestEntry,
    SpendingEntry,
)

# name, amount, months between payments (0 = once), first due, category, account, kind
EXPENSES = [
    ("Rent", 9500, 1, (0, 1), "House", "Budget", "fixed"),
    ("Electricity", 650, 1, (0, 10), "House", "Budget", "variable"),
    ("Internet", 1050, 3, (1, 5), "House", "Budget", "fixed"),
    ("Car insurance", 4800, 12, (5, 1), "Insurance", "Budget", "fixed"),
    ("Home insurance", 1250, 12, (8, 15), "Insurance", "Budget", "fixed"),
    ("Streaming", 129, 1, (0, 12), "Subscriptions", "Budget", "fixed"),
    ("Phone", 199, 1, (0, 20), "Subscriptions", "Budget", "fixed"),
    ("Fuel and parking", 900, 1, (0, 1), "Transport", "Budget", "variable"),
    ("Football club", 1400, 6, (2, 1), "Children", "Budget", "fixed"),
    ("Groceries", 5500, 1, (0, 1), "Food", "Food", "variable"),
    ("Summer holiday", 24000, 12, (6, 1), "Savings goals", "Savings", "fixed"),
    ("Christmas gifts", 3500, 12, (9, 1), "Savings goals", "Savings", "variable"),
    ("New car", 60000, 0, (36, 1), "Savings goals", "Savings", "fixed"),
]
INCOME = [
    ("Salary Alex", 26500, 1, 0),
    ("Salary Sam", 23800, 1, 0),
    ("Child benefit", 4600, 3, 1),
]


class Command(BaseCommand):
    help = "Create a budget with made-up example data (for trying the app)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months", type=int, default=3, help="Month-ends to close with example actuals."
        )
        parser.add_argument("--user", default="demo", help="Username to create (password: demo).")
        parser.add_argument("--name", default="Demo", help="Name of the new budget.")

    @transaction.atomic
    def handle(self, *args, months: int, user: str, name: str, **options):
        User = get_user_model()
        person = User.objects.filter(username=user).first()
        if person is None:
            person = User.objects.create_user(user, password="demo", first_name=user.title())
        if Budget.objects.filter(members=person, name=name).exists():
            raise CommandError(f"{user} already has a budget called {name}. Use --name.")

        start = YearMonth.of(date.today()) - months + 1
        budget = budgets.create_budget(name, [person], person)
        budget.start_month = start.first_day()
        budget.started_on = start.first_day()
        budget.setup_step = 5
        budget.nemkonto_min = 200000
        budget.nemkonto_max = 500000
        budget.nemkonto_opening = 350000
        budget.general_savings_opening = 2500000
        budget.save()

        accounts = {account.name: account for account in budget.accounts.all()}
        categories = {category.name: category for category in budget.categories.all()}
        for name, amount, interval, (offset, day), category, account, kind in EXPENSES:
            first_due = (start + offset).day(day)
            Expense.objects.create(
                budget=budget,
                name=name,
                amount=amount * 100,
                interval_months=interval,
                first_due=first_due,
                category=categories.get(category),
                account=accounts[account],
                kind=kind,
                starting_balance=amount * 100 // 3 if interval >= 12 else 0,
            )
        for name, amount, interval, offset in INCOME:
            IncomeSource.objects.create(
                budget=budget,
                name=name,
                amount=amount * 100,
                interval_months=interval,
                first_month=(start + offset).first_day(),
            )

        wobble = [0.97, 1.04, 0.92, 1.08, 1.0, 0.95]
        for number in range(months):
            month = services.next_close_month(budget)
            previous = month - 1
            state = services.build_state(budget)
            for ledger in state.ledgers:
                line = ledger.lines.get(previous)
                if not line or not line.expected_spend:
                    continue
                factor = (
                    1
                    if ledger.expense.kind == "fixed"
                    else wobble[(number + ledger.expense.id) % 6]
                )
                SpendingEntry.objects.create(
                    expense_id=ledger.expense.id,
                    month=previous.first_day(),
                    amount=round(line.expected_spend * factor),
                    updated_by=person,
                )
            for source in budget.incomes.all():
                expected = services.engine_income(source).expected(month)
                if expected:
                    IncomeEntry.objects.create(
                        source=source, month=month.first_day(), amount=expected, updated_by=person
                    )
            InterestEntry.objects.create(
                account=accounts["Savings"], month=previous.first_day(), amount=4150 + number * 120
            )
            services.start_draft(budget, month, person)
            services.finalize_close(budget, month, person)
            self.stdout.write(f"Closed {month.label}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo budget {budget.name} ready. Log in as '{user}' with password 'demo'."
            )
        )
