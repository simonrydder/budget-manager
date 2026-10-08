import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import budget_manager.ledger.models

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
    dependencies = [
        ("ledger", "0006_move"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Budget",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                (
                    "start_month",
                    models.DateField(
                        default=budget_manager.ledger.models.next_month_start,
                        help_text="The first month you budget for. Its transfers happen on the last day of the month before.",
                    ),
                ),
                (
                    "opening_month",
                    models.DateField(
                        blank=True,
                        help_text="Set when the budget is started mid-month: the month the starting balances refer to the start of.",
                        null=True,
                    ),
                ),
                ("started_on", models.DateField(blank=True, null=True)),
                ("nemkonto_min", models.BigIntegerField(default=0)),
                ("nemkonto_max", models.BigIntegerField(default=0)),
                ("nemkonto_opening", models.BigIntegerField(default=0)),
                ("general_savings_opening", models.BigIntegerField(default=0)),
                ("forecast_months", models.PositiveSmallIntegerField(default=24)),
                (
                    "setup_step",
                    models.PositiveSmallIntegerField(
                        default=1, help_text="The furthest step of the setup reached so far."
                    ),
                ),
                (
                    "balances_on",
                    models.DateField(
                        blank=True,
                        help_text="When the bank balances in the setup were entered.",
                        null=True,
                    ),
                ),
                (
                    "start_transfers",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Bank transfers that even out the accounts after starting, until done.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "members",
                    models.ManyToManyField(
                        blank=True,
                        related_name="budgets",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="People",
                    ),
                ),
            ],
            options={"ordering": ["name", "id"]},
        ),
        *[
            migrations.AddField(
                model_name=model,
                name="budget",
                field=models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name=related,
                    to="ledger.budget",
                ),
            )
            for model, related in SCOPED
        ],
        migrations.AddField(
            model_name="account",
            name="start_balance",
            field=models.BigIntegerField(
                blank=True,
                help_text="The bank balance entered when setting up the budget.",
                null=True,
            ),
        ),
    ]
