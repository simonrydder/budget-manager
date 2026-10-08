import django.db.models.deletion
from django.db import migrations, models

SCOPED = [
    ("account", "accounts"),
    ("category", "categories"),
    ("expense", "expenses"),
    ("incomesource", "incomes"),
    ("balancecorrection", "corrections"),
    ("monthclose", "closes"),
    ("move", "moves"),
]


class Migration(migrations.Migration):
    dependencies = [("ledger", "0008_budget_data")]

    operations = [
        migrations.RemoveConstraint(model_name="account", name="one_nemkonto"),
        migrations.RemoveConstraint(model_name="account", name="one_savings_account"),
        *[
            migrations.AlterField(
                model_name=model,
                name="budget",
                field=models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name=related,
                    to="ledger.budget",
                ),
            )
            for model, related in SCOPED
        ],
        migrations.AlterField(
            model_name="account", name="name", field=models.CharField(max_length=60)
        ),
        migrations.AlterField(
            model_name="category", name="name", field=models.CharField(max_length=60)
        ),
        migrations.AlterField(
            model_name="incomesource", name="name", field=models.CharField(max_length=80)
        ),
        migrations.AlterField(model_name="monthclose", name="month", field=models.DateField()),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                fields=("budget", "name"), name="account_name_per_budget"
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "nemkonto")),
                fields=("budget", "role"),
                name="one_nemkonto",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "savings")),
                fields=("budget", "role"),
                name="one_savings_account",
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("budget", "name"), name="category_name_per_budget"
            ),
        ),
        migrations.AddConstraint(
            model_name="incomesource",
            constraint=models.UniqueConstraint(
                fields=("budget", "name"), name="income_name_per_budget"
            ),
        ),
        migrations.AddConstraint(
            model_name="monthclose",
            constraint=models.UniqueConstraint(
                fields=("budget", "month"), name="one_close_per_month"
            ),
        ),
        migrations.DeleteModel(name="BudgetSettings"),
    ]
