from django.db import migrations

ACCOUNTS = [
    ("NemKonto", "nemkonto"),
    ("Budget", "normal"),
    ("Food", "normal"),
    ("Savings", "savings"),
]
CATEGORIES = [
    "House",
    "Transport",
    "Insurance",
    "Subscriptions",
    "Children",
    "Food",
    "Entertainment",
    "Savings goals",
]


def create_defaults(apps, schema_editor):
    Account = apps.get_model("ledger", "Account")
    Category = apps.get_model("ledger", "Category")
    if not Account.objects.exists():
        for order, (name, role) in enumerate(ACCOUNTS):
            Account.objects.create(name=name, role=role, sort_order=order)
    if not Category.objects.exists():
        for order, name in enumerate(CATEGORIES):
            Category.objects.create(name=name, sort_order=order)


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]

    operations = [migrations.RunPython(create_defaults, migrations.RunPython.noop)]
