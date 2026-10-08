from django.conf import settings
from django.db import migrations

SCOPED = [
    "Account",
    "Category",
    "Expense",
    "IncomeSource",
    "BalanceCorrection",
    "MonthClose",
    "Move",
]
SETTINGS = [
    "start_month",
    "opening_month",
    "started_on",
    "nemkonto_min",
    "nemkonto_max",
    "nemkonto_opening",
    "general_savings_opening",
    "forecast_months",
]


def into_one_budget(apps, schema_editor):
    """Everything entered so far becomes the budget "My budget", shared by everyone who can
    log in. A new installation starts without budgets: each budget gets its own defaults."""
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Budget = apps.get_model("ledger", "Budget")
    BudgetSettings = apps.get_model("ledger", "BudgetSettings")
    MonthClose = apps.get_model("ledger", "MonthClose")
    users = list(User.objects.all())
    has_data = any(
        apps.get_model("ledger", name).objects.exists()
        for name in ("Expense", "IncomeSource", "MonthClose", "Move", "BalanceCorrection")
    )
    if not users and not has_data:
        apps.get_model("ledger", "Account").objects.all().delete()
        apps.get_model("ledger", "Category").objects.all().delete()
        return
    config = BudgetSettings.objects.order_by("pk").first()
    values = {name: getattr(config, name) for name in SETTINGS} if config else {}
    started = bool(values.get("started_on")) or MonthClose.objects.filter(status="closed").exists()
    budget = Budget.objects.create(name="My budget", setup_step=5 if started else 1, **values)
    budget.members.set(users)
    for name in SCOPED:
        apps.get_model("ledger", name).objects.update(budget=budget)


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0007_budget"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(into_one_budget, migrations.RunPython.noop)]
