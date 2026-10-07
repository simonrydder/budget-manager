import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def decisions_to_moves(apps, schema_editor):
    """Top-ups, fillings and releases planned for the next month-end become pending moves."""
    Decision = apps.get_model("ledger", "Decision")
    Move = apps.get_model("ledger", "Move")
    planned = Decision.objects.filter(
        close__status="draft", kind__in=["fund", "topup", "release"]
    ).select_related("expense")
    for decision in planned:
        Move.objects.create(
            kind=decision.kind,
            expense=decision.expense,
            account_id=decision.expense.account_id,
            amount=decision.amount,
        )
    planned.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0005_line_funding"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Move",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("fund", "Fill from General Savings"),
                            ("topup", "Top up from General Savings"),
                            ("release", "Return to General Savings"),
                            ("refund", "Refund to General Savings"),
                        ],
                        max_length=10,
                    ),
                ),
                ("amount", models.BigIntegerField()),
                ("note", models.CharField(blank=True, max_length=200)),
                ("done", models.BooleanField(default=False)),
                (
                    "month",
                    models.DateField(
                        blank=True,
                        help_text="Once made: the budget month of the next month-end.",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("done_at", models.DateTimeField(blank=True, null=True)),
                (
                    "account",
                    models.ForeignKey(
                        blank=True,
                        help_text="For a refund: the account the money arrived on.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="ledger.account",
                    ),
                ),
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
                    "done_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "expense",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="moves",
                        to="ledger.expense",
                    ),
                ),
            ],
            options={"ordering": ["-done_at", "-created_at"]},
        ),
        migrations.RunPython(decisions_to_moves, migrations.RunPython.noop),
    ]
