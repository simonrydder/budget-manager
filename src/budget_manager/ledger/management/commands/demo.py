"""Fill an empty budget with made-up example data, to try the app out."""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budget_manager.engine import YearMonth
from budget_manager.ledger import services
from budget_manager.ledger.models import (
    Account,
    BudgetSettings,
    Category,
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
    help = "Fill an empty budget with made-up example data (for trying the app)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months", type=int, default=3, help="Month-ends to close with example actuals."
        )
        parser.add_argument("--user", default="demo", help="Username to create (password: demo).")

    @transaction.atomic
    def handle(self, *args, months: int, user: str, **options):
        if Expense.objects.exists() or IncomeSource.objects.exists():
            raise CommandError("The budget already has data. The demo only fills an empty one.")
        User = get_user_model()
        person = User.objects.filter(username=user).first()
        if person is None:
            person = User.objects.create_user(user, password="demo", first_name=user.title())

        start = YearMonth.of(date.today()) - months + 1
        config = BudgetSettings.load()
        config.start_month = start.first_day()
        config.nemkonto_min = 200000
        config.nemkonto_max = 500000
        config.nemkonto_opening = 350000
        config.general_savings_opening = 2500000
        config.save()

        accounts = {account.name: account for account in Account.objects.all()}
        categories = {category.name: category for category in Category.objects.all()}
        for name, amount, interval, (offset, day), category, account, kind in EXPENSES:
            first_due = (start + offset).day(day)
            Expense.objects.create(
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
                name=name,
                amount=amount * 100,
                interval_months=interval,
                first_month=(start + offset).first_day(),
            )

        wobble = [0.97, 1.04, 0.92, 1.08, 1.0, 0.95]
        for number in range(months):
            month = services.next_close_month()
            previous = month - 1
            state = services.build_state()
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
            for source in IncomeSource.objects.all():
                expected = services.engine_income(source).expected(month)
                if expected:
                    IncomeEntry.objects.create(
                        source=source, month=month.first_day(), amount=expected, updated_by=person
                    )
            InterestEntry.objects.create(
                account=accounts["Savings"], month=previous.first_day(), amount=4150 + number * 120
            )
            services.start_draft(month, person)
            services.finalize_close(month, person)
            self.stdout.write(f"Closed {month.label}")
        self.stdout.write(
            self.style.SUCCESS(f"Demo budget ready. Log in as '{user}' with password 'demo'.")
        )
