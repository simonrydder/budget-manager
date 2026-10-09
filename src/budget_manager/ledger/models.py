"""Database tables. Amounts are whole numbers in hundredths (øre); months are stored as the
first day of the month."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Q

from budget_manager.engine import Kind, Role, YearMonth, frequency_label


def next_month_start() -> date:
    today = date.today()
    return (YearMonth.of(today) + 1).first_day()


class Budget(models.Model):
    """One budget with its own accounts, expenses, income and month-ends. People only see the
    budgets they are members of."""

    name = models.CharField(max_length=80)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="budgets", blank=True, verbose_name="People"
    )
    start_month = models.DateField(
        default=next_month_start,
        help_text="The first month you budget for. Its transfers happen on the last day of the "
        "month before.",
    )
    opening_month = models.DateField(
        null=True,
        blank=True,
        help_text="Set when the budget is started mid-month: the month the starting balances "
        "refer to the start of.",
    )
    started_on = models.DateField(null=True, blank=True)
    nemkonto_min = models.BigIntegerField(default=0)
    nemkonto_max = models.BigIntegerField(default=0)
    nemkonto_opening = models.BigIntegerField(default=0)
    general_savings_opening = models.BigIntegerField(default=0)
    everyday_spending = models.BigIntegerField(
        default=0,
        help_text="Expected spending from the NemKonto itself in a month, for the forecast.",
    )
    forecast_months = models.PositiveSmallIntegerField(default=24)
    setup_step = models.PositiveSmallIntegerField(
        default=1, help_text="The furthest step of the setup reached so far."
    )
    balances_on = models.DateField(
        null=True, blank=True, help_text="When the bank balances in the setup were entered."
    )
    start_transfers = models.JSONField(
        default=list,
        blank=True,
        help_text="Bank transfers that even out the accounts after starting, until done.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from budget_manager.ledger.scope import budget_url

        return budget_url(self.pk)

    @property
    def start(self) -> YearMonth:
        return YearMonth.of(self.start_month)

    @property
    def opening(self) -> YearMonth:
        """The first month whose spending belongs to the budget."""
        return (
            min(YearMonth.of(self.opening_month), self.start) if self.opening_month else self.start
        )


class Account(models.Model):
    ROLE_CHOICES = [
        (Role.NEMKONTO.value, "NemKonto"),
        (Role.SAVINGS.value, "Savings (holds General Savings)"),
        (Role.NORMAL.value, "Normal"),
    ]

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=60)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=Role.NORMAL.value)
    sort_order = models.PositiveIntegerField(default=0)
    start_balance = models.BigIntegerField(
        null=True, blank=True, help_text="The bank balance entered when setting up the budget."
    )

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["budget", "name"], name="account_name_per_budget"),
            models.UniqueConstraint(
                fields=["budget", "role"], condition=Q(role="nemkonto"), name="one_nemkonto"
            ),
            models.UniqueConstraint(
                fields=["budget", "role"], condition=Q(role="savings"), name="one_savings_account"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_nemkonto(self) -> bool:
        return self.role == Role.NEMKONTO

    @property
    def holds_general_savings(self) -> bool:
        return self.role == Role.SAVINGS


class Category(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["budget", "name"], name="category_name_per_budget")
        ]

    def __str__(self) -> str:
        return self.name


class Expense(models.Model):
    KIND_CHOICES = [
        (Kind.FIXED.value, "Fixed"),
        (Kind.VARIABLE.value, "Variable"),
        (Kind.RUNNING.value, "Running"),
    ]

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="expenses")
    name = models.CharField(max_length=80)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses"
    )
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="expenses")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=Kind.FIXED.value)
    amount = models.BigIntegerField()
    first_amount = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="The payment on the first due date, when it is a different amount (for "
        "example one that covers two months). Empty: the normal amount.",
    )
    interval_months = models.PositiveSmallIntegerField(default=1)
    first_due = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    starting_balance = models.BigIntegerField(default=0)
    start_month = models.DateField(
        null=True, blank=True, help_text="First month with a contribution. Empty: from the start."
    )
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def frequency(self) -> str:
        return frequency_label(self.interval_months)

    @property
    def is_fixed(self) -> bool:
        return self.kind == Kind.FIXED

    @property
    def is_running(self) -> bool:
        """Spent bit by bit through the month (food, fuel, everyday spending), rather than paid
        on a due date like a bill."""
        return self.kind == Kind.RUNNING

    def is_ended(self, on: date | None = None) -> bool:
        return self.end_date is not None and self.end_date < (on or date.today())

    def amount_on(self, due: date | None) -> int:
        """The amount of the payment due on ``due``."""
        if due is not None and due == self.first_due and self.first_amount is not None:
            return self.first_amount
        return self.amount

    @property
    def monthly_equivalent(self) -> int:
        """The amount spread over its interval, for comparing expenses."""
        return self.amount // self.interval_months if self.interval_months else 0


class IncomeSource(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="incomes")
    name = models.CharField(max_length=80)
    amount = models.BigIntegerField(help_text="Expected amount each time it arrives.")
    interval_months = models.PositiveSmallIntegerField(default=1)
    first_month = models.DateField(help_text="The first month this income is for.")
    end_month = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["budget", "name"], name="income_name_per_budget")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def frequency(self) -> str:
        return frequency_label(self.interval_months)


class SpendingEntry(models.Model):
    """What was actually spent on an expense in a calendar month."""

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="spending")
    month = models.DateField()
    amount = models.BigIntegerField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "month"], name="one_spending_per_month")
        ]


class IncomeEntry(models.Model):
    """What actually arrived on the NemKonto for a budget month."""

    source = models.ForeignKey(IncomeSource, on_delete=models.CASCADE, related_name="entries")
    month = models.DateField()
    amount = models.BigIntegerField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "month"], name="one_income_per_month")
        ]


class InterestEntry(models.Model):
    """Interest that landed on an account during a calendar month (negative if paid)."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="interest")
    month = models.DateField()
    amount = models.BigIntegerField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "month"], name="one_interest_per_month")
        ]


class BalanceCorrection(models.Model):
    """A manual correction of the NemKonto or General Savings, e.g. a bank fee."""

    class Target(models.TextChoices):
        NEMKONTO = "nemkonto", "NemKonto"
        GENERAL_SAVINGS = "general_savings", "General Savings"

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="corrections")
    target = models.CharField(max_length=20, choices=Target.choices)
    month = models.DateField(help_text="Applies from the month-end after this month.")
    amount = models.BigIntegerField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MonthClose(models.Model):
    """The month-end for a budget month: its transfers happen on the last day of the month before."""

    class Status(models.TextChoices):
        DRAFT = "draft", "In progress"
        CLOSED = "closed", "Closed"

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="closes")
    month = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    step = models.PositiveSmallIntegerField(default=1)
    done_accounts = models.JSONField(default=list, blank=True)

    nemkonto_before = models.BigIntegerField(default=0)
    nemkonto_spent = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Spent from the NemKonto itself since the last month-end; empty until entered.",
    )
    income = models.BigIntegerField(default=0)
    interest = models.BigIntegerField(default=0)
    contributions = models.BigIntegerField(default=0)
    nemkonto_after_transfers = models.BigIntegerField(default=0)
    surplus = models.BigIntegerField(default=0)
    taken = models.BigIntegerField(default=0)
    nemkonto_end = models.BigIntegerField(default=0)
    general_savings_before = models.BigIntegerField(default=0)
    general_savings_after = models.BigIntegerField(default=0)
    notices = models.JSONField(default=list, blank=True)

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["budget", "month"], name="one_close_per_month")
        ]

    def __str__(self) -> str:
        return f"Month-end {self.transfer_day:%d %b %Y}"

    @property
    def budget_month(self) -> YearMonth:
        return YearMonth.of(self.month)

    @property
    def is_closed(self) -> bool:
        return self.status == self.Status.CLOSED

    @property
    def transfer_day(self) -> date:
        return (self.budget_month - 1).last_day()


class ContributionLine(models.Model):
    """What one closed month did to one expense."""

    close = models.ForeignKey(MonthClose, on_delete=models.CASCADE, related_name="lines")
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="lines")
    contribution = models.BigIntegerField(default=0)
    expected_spend = models.BigIntegerField(default=0)
    topup = models.BigIntegerField(default=0)
    cover = models.BigIntegerField(default=0)
    release = models.BigIntegerField(default=0)
    funding = models.BigIntegerField(default=0)
    balance_before = models.BigIntegerField(default=0)
    planned_before = models.BigIntegerField(default=0)
    amount_before = models.BigIntegerField(default=0)
    amount_after = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["close", "expense"], name="one_line_per_expense")
        ]

    @property
    def balance_after(self) -> int:
        return self.balance_before + self.topup - self.cover - self.release + self.contribution


class Transfer(models.Model):
    """A bank transfer made at a month-end. Positive: from the NemKonto to the account."""

    close = models.ForeignKey(MonthClose, on_delete=models.CASCADE, related_name="transfers")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transfers")
    amount = models.BigIntegerField()
    contributions = models.BigIntegerField(default=0)
    interest = models.BigIntegerField(default=0)
    topups = models.BigIntegerField(default=0)
    covers = models.BigIntegerField(default=0)
    releases = models.BigIntegerField(default=0)
    general_savings = models.BigIntegerField(default=0)
    done = models.BooleanField(default=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["account__sort_order", "account_id"]


class Decision(models.Model):
    """Money taken from an expense at a month-end: to the NemKonto (cover) or to General Savings
    (release)."""

    class Type(models.TextChoices):
        COVER = "cover", "Cover the NemKonto"
        RELEASE = "release", "Move to General Savings"
        TOPUP = "topup", "Top up from General Savings"
        FUND = "fund", "Fill a new expense from General Savings"

    close = models.ForeignKey(MonthClose, on_delete=models.CASCADE, related_name="decisions")
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="decisions")
    kind = models.CharField(max_length=10, choices=Type.choices)
    amount = models.BigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["close", "expense", "kind"], name="one_decision_each")
        ]


class Move(models.Model):
    """Money moved between General Savings and an expense (or a refund put into General
    Savings) any day, not only at a month-end. It waits until the bank transfers are made."""

    class Type(models.TextChoices):
        FUND = "fund", "Fill from General Savings"
        TOPUP = "topup", "Top up from General Savings"
        RELEASE = "release", "Return to General Savings"
        REFUND = "refund", "Refund to General Savings"

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="moves")
    kind = models.CharField(max_length=10, choices=Type.choices)
    expense = models.ForeignKey(
        Expense, null=True, blank=True, on_delete=models.CASCADE, related_name="moves"
    )
    account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="For a refund: the account the money arrived on.",
    )
    amount = models.BigIntegerField()
    note = models.CharField(max_length=200, blank=True)
    done = models.BooleanField(default=False)
    month = models.DateField(
        null=True, blank=True, help_text="Once made: the budget month of the next month-end."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-done_at", "-created_at"]

    @property
    def to_expense(self) -> int:
        """What the move adds to its expense (negative: taken from it)."""
        if self.kind in (self.Type.FUND, self.Type.TOPUP):
            return self.amount
        if self.kind == self.Type.RELEASE:
            return -self.amount
        return 0

    @property
    def to_general_savings(self) -> int:
        if self.kind == self.Type.REFUND:
            return self.amount
        return -self.to_expense
