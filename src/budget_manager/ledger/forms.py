from __future__ import annotations

from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from budget_manager.engine import FREQUENCIES, YearMonth, format_input, parse_amount
from budget_manager.ledger.models import (
    Account,
    BalanceCorrection,
    Budget,
    Category,
    Expense,
    IncomeSource,
)
from budget_manager.ledger.services import first_running_month

FREQUENCY_CHOICES = [(value, label) for value, label in FREQUENCIES.items()]


class AmountInput(forms.TextInput):
    def __init__(self, attrs=None):
        base = {"inputmode": "decimal", "autocomplete": "off", "class": "amount"}
        super().__init__({**base, **(attrs or {})})

    def format_value(self, value):
        if isinstance(value, int):
            return format_input(value)
        return super().format_value(value)


class AmountField(forms.Field):
    """An amount typed like ``1.234,56``; cleaned to hundredths."""

    widget = AmountInput

    def __init__(self, *, allow_negative: bool = True, **kwargs):
        self.allow_negative = allow_negative
        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, int):
            return value
        try:
            amount = parse_amount(value)
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error
        if amount is not None and amount < 0 and not self.allow_negative:
            raise forms.ValidationError("Enter an amount of 0 or more.")
        return amount

    def validate(self, value):
        if value is None and self.required:
            raise forms.ValidationError(self.error_messages["required"], code="required")


class MonthInput(forms.TextInput):
    input_type = "month"

    def format_value(self, value):
        if isinstance(value, date):
            return str(YearMonth.of(value))
        return super().format_value(value)


class MonthField(forms.Field):
    """A month typed as ``2025-05``; cleaned to the first day of the month."""

    widget = MonthInput

    def to_python(self, value):
        if isinstance(value, date):
            return value.replace(day=1)
        if not value:
            return None
        try:
            return YearMonth.parse(value).first_day()
        except ValueError as error:
            raise forms.ValidationError("Enter a month like 2025-05.") from error


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class UniqueNameInBudget:
    """Names are unique within a budget. Checked here so the person gets a clear message."""

    noun = "item"

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        model = type(self.instance)
        clash = model.objects.filter(budget_id=self.instance.budget_id, name__iexact=name)
        if clash.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f"There is already {self.noun} called {name}.")
        return name


KIND_CHOICES = [
    ("fixed", "Fixed"),
    ("variable", "Variable"),
    ("running", "Running"),
]


class ExpenseForm(forms.ModelForm):
    amount = AmountField(
        allow_negative=False,
        label="Amount",
        help_text="The expected amount each time it is due; for a running budget, a month.",
    )
    kind = forms.ChoiceField(
        choices=KIND_CHOICES,
        initial="fixed",
        widget=forms.RadioSelect,
        label="Type",
    )
    first_amount = AmountField(
        required=False,
        allow_negative=False,
        label="First payment, if different",
        help_text="Only when the payment on the first due date is a different amount, for "
        "example one that covers two months. Later payments are the normal amount.",
    )
    starting_balance = AmountField(
        required=False,
        label="Already saved",
        help_text="Money already in the linked account for this expense.",
    )
    interval_months = forms.TypedChoiceField(
        choices=FREQUENCY_CHOICES, coerce=int, initial=1, label="Frequency"
    )

    class Meta:
        model = Expense
        fields = [
            "name",
            "amount",
            "interval_months",
            "first_due",
            "first_amount",
            "kind",
            "category",
            "account",
            "starting_balance",
            "end_date",
            "notes",
        ]
        labels = {
            "first_due": "First due date",
            "kind": "Type",
            "end_date": "End date",
        }
        help_texts = {
            "first_due": "For a savings goal: the date the money must be ready.",
            "end_date": "Optional. No payments after this date, so contributions stop.",
            "category": "You can also drag the expense between categories later.",
        }
        widgets = {
            "first_due": DateInput(),
            "end_date": DateInput(),
            "kind": forms.RadioSelect,
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        budget = self.instance.budget
        # Everyday spending from the NemKonto is entered at each month-end instead. An expense
        # put on it before that keeps it as a choice, so it can be moved.
        accounts = budget.accounts.exclude(role="nemkonto")
        if self.instance.account_id:
            accounts = accounts | budget.accounts.filter(pk=self.instance.account_id)
        self.fields["account"].queryset = accounts
        self.fields["account"].empty_label = None
        self.fields["first_due"].required = False
        self.fields["category"].queryset = budget.categories.all()
        self.fields["category"].empty_label = "Uncategorised"
        self.fields["category"].required = False
        if not self.instance.pk and not self.initial.get("account"):
            default = budget.accounts.filter(name__iexact="budget").first()
            if default:
                self.initial["account"] = default.pk

    fill_from_savings = forms.BooleanField(
        required=False,
        label="Fill from General Savings",
        help_text="Moves in what a steady monthly amount would already have saved, so it saves "
        "the same every month. Without it, the first payment is split over the months left. "
        "The transfer waits under Balance until you make it.",
    )
    topup = AmountField(
        required=False,
        allow_negative=False,
        label="Top up from General Savings",
        help_text="Moves this amount from General Savings to the expense.",
    )

    def clean_starting_balance(self):
        return self.cleaned_data.get("starting_balance") or 0

    def clean(self):
        data = super().clean()
        account = data.get("account")
        if data.get("kind") == "running":
            # Monthly, available from the first of the month.
            data["interval_months"] = 1
            first = data.get("first_due") or self.instance.first_due
            if first is None:
                first = first_running_month(self.instance.budget, date.today()).first_day()
            data["first_due"] = first.replace(day=1)
        elif not data.get("first_due") and "first_due" not in self.errors:
            self.add_error("first_due", "Enter the date it is due next.")
        if data.get("kind") == "running" or data.get("first_amount") == data.get("amount"):
            data["first_amount"] = None
        if account and account.is_nemkonto:
            self.add_error(
                "account",
                "Expenses cannot use the NemKonto. What is spent from it is entered at each "
                "month-end, so choose another account.",
            )
        first_due, end_date = data.get("first_due"), data.get("end_date")
        if first_due and end_date and end_date < first_due:
            self.add_error("end_date", "The end date must be on or after the first due date.")
        return data


class EndExpenseForm(forms.Form):
    end_date = forms.DateField(
        widget=DateInput(),
        label="Last day",
        help_text="No payments are expected after this date.",
    )


class ReleaseForm(forms.Form):
    amount = AmountField(allow_negative=False, label="Amount to move")


class RefundForm(forms.Form):
    amount = AmountField(allow_negative=False, label="Amount")
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        empty_label=None,
        label="Arrived on",
        help_text="The account the money came back to.",
    )
    note = forms.CharField(
        max_length=200, required=False, label="Note", help_text="For example: insurance surplus."
    )

    def __init__(self, *args, budget: Budget, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = budget.accounts.all()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if not amount:
            raise forms.ValidationError("Enter an amount above 0.")
        return amount


class IncomeSourceForm(UniqueNameInBudget, forms.ModelForm):
    noun = "an income"

    amount = AmountField(allow_negative=False, label="Expected amount")
    interval_months = forms.TypedChoiceField(
        choices=FREQUENCY_CHOICES, coerce=int, initial=1, label="Frequency"
    )
    first_month = MonthField(label="First month", help_text="The month this income is for.")
    end_month = MonthField(required=False, label="Last month", help_text="Optional.")

    class Meta:
        model = IncomeSource
        fields = ["name", "amount", "interval_months", "first_month", "end_month", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        first, end = data.get("first_month"), data.get("end_month")
        if first and end and end < first:
            self.add_error("end_month", "The last month must be on or after the first month.")
        return data


class AccountForm(UniqueNameInBudget, forms.ModelForm):
    noun = "an account"

    holds_general_savings = forms.BooleanField(
        required=False,
        label="This account holds General Savings",
        help_text="Only one account can. Savings goals usually live here too.",
    )

    class Meta:
        model = Account
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["holds_general_savings"].initial = self.instance.holds_general_savings
        if self.instance.is_nemkonto:
            del self.fields["holds_general_savings"]

    def clean_holds_general_savings(self):
        value = self.cleaned_data["holds_general_savings"]
        if self.instance.holds_general_savings and not value:
            raise forms.ValidationError(
                "One account must hold General Savings. Choose another account for it instead."
            )
        return value


class CategoryForm(UniqueNameInBudget, forms.ModelForm):
    noun = "a category"

    class Meta:
        model = Category
        fields = ["name"]


class PeopleField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        kwargs.setdefault("queryset", get_user_model().objects.order_by("username"))
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", "People who can use it")
        super().__init__(**kwargs)

    def label_from_instance(self, obj):
        return obj.first_name or obj.username


class BudgetNameMixin:
    """Each person sees their budgets by name, so a name is used once per person."""

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Budget.objects.filter(members=self.user, name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(f"You already have a budget called {name}.")
        return name

    def clean_members(self):
        """You always keep access to a budget you create or change."""
        members = list(self.cleaned_data.get("members") or [])
        if self.user not in members:
            members.append(self.user)
        return members


class BudgetForm(BudgetNameMixin, forms.ModelForm):
    """A new budget, or a budget's name and the people who can use it."""

    members = PeopleField()

    class Meta:
        model = Budget
        fields = ["name", "members"]
        labels = {"name": "Name"}
        help_texts = {"name": "For example: Household, Private or My company."}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not self.instance.pk:
            self.initial.setdefault("members", [user.pk])


class SettingsForm(BudgetNameMixin, forms.ModelForm):
    members = PeopleField(help_text="You always keep access yourself.")
    nemkonto_min = AmountField(allow_negative=False, label="NemKonto minimum (X)")
    nemkonto_max = AmountField(allow_negative=False, label="NemKonto maximum (Y)")
    everyday_spending = AmountField(
        required=False,
        allow_negative=False,
        label="Everyday spending from the NemKonto, a month",
        help_text="Roughly what is spent with its card. The forecast uses it until three month-ends "
        "have recorded what was spent; after that it uses the average of the last six.",
    )
    forecast_months = forms.IntegerField(min_value=3, max_value=120, label="Forecast length")

    class Meta:
        model = Budget
        fields = [
            "name",
            "members",
            "nemkonto_min",
            "nemkonto_max",
            "everyday_spending",
            "forecast_months",
        ]
        labels = {"name": "Name"}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_everyday_spending(self):
        return self.cleaned_data.get("everyday_spending") or 0

    def clean(self):
        data = super().clean()
        low, high = data.get("nemkonto_min"), data.get("nemkonto_max")
        if low is not None and high is not None and high < low:
            self.add_error("nemkonto_max", "The maximum must be at least the minimum.")
        return data


class CopyBudgetForm(BudgetNameMixin, forms.Form):
    SETUP = "setup"
    EVERYTHING = "everything"

    name = forms.CharField(max_length=80, label="Name of the copy")
    what = forms.ChoiceField(
        label="What to copy",
        widget=forms.RadioSelect,
        initial=SETUP,
        choices=[
            (SETUP, "Accounts, categories, expenses and income, then set it up from scratch"),
            (EVERYTHING, "Everything, including all month-ends and history"),
        ],
    )
    members = PeopleField()

    def __init__(self, *args, user, source: Budget, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance = Budget()
        self.initial.setdefault("name", f"Copy of {source.name}")
        self.initial.setdefault("members", list(source.members.values_list("pk", flat=True)))


class DeleteBudgetForm(forms.Form):
    confirm = forms.CharField(label="Type the name of the budget to delete it")

    def __init__(self, *args, budget: Budget, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget

    def clean_confirm(self):
        value = self.cleaned_data["confirm"].strip()
        if value != self.budget.name:
            raise forms.ValidationError(f"Type {self.budget.name} exactly.")
        return value


class CorrectionForm(forms.ModelForm):
    amount = AmountField(
        label="Correction",
        help_text="Positive adds money, negative removes it (e.g. -25,00 for a bank fee).",
    )

    class Meta:
        model = BalanceCorrection
        fields = ["amount", "note"]
        labels = {"note": "Reason"}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if not amount:
            raise forms.ValidationError("Enter an amount other than 0.")
        return amount


class NewUserForm(UserCreationForm):
    budgets = forms.ModelMultipleChoiceField(
        queryset=Budget.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Budgets they can use",
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["username", "first_name"]
        labels = {"first_name": "Name"}

    def __init__(self, *args, budgets=None, **kwargs):
        super().__init__(*args, **kwargs)
        if budgets is None:
            del self.fields["budgets"]
        else:
            self.fields["budgets"].queryset = budgets

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit and "budgets" in self.fields:
            for budget in self.cleaned_data.get("budgets") or []:
                budget.members.add(user)
        return user


# --- Setting up a budget --------------------------------------------------------------------


class BalancesForm(forms.Form):
    """Step 1 of the setup: today's balance of every account and the NemKonto limits."""

    nemkonto_min = AmountField(
        allow_negative=False,
        label="Keep at least (X)",
        help_text="After each month-end the NemKonto should hold at least this.",
    )
    nemkonto_max = AmountField(
        allow_negative=False,
        label="Keep at most (Y)",
        help_text="More than this is moved to General Savings.",
    )
    everyday_spending = AmountField(
        required=False,
        allow_negative=False,
        label="Spent from it in a month, roughly",
        help_text="Everyday spending with its card, for the forecast. At each month-end you "
        "enter what was really spent, and after three month-ends the forecast uses those.",
    )

    def __init__(self, *args, budget: Budget, accounts, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget
        self.accounts = accounts
        for account in accounts:
            self.fields[self.key(account)] = AmountField(
                label=account.name,
                initial=account.start_balance,
                error_messages={"required": "Enter the balance, 0 if the account is empty."},
                widget=AmountInput(attrs={"placeholder": "0,00"}),
            )
        if budget.nemkonto_max:
            self.fields["nemkonto_min"].initial = budget.nemkonto_min
            self.fields["nemkonto_max"].initial = budget.nemkonto_max
        if budget.everyday_spending:
            self.fields["everyday_spending"].initial = budget.everyday_spending

    @staticmethod
    def key(account: Account) -> str:
        return f"balance_{account.pk}"

    def clean(self):
        data = super().clean()
        low, high = data.get("nemkonto_min"), data.get("nemkonto_max")
        if low is not None and high is not None and high < low:
            self.add_error("nemkonto_max", "The maximum must be at least the minimum.")
        return data

    def save(self, today: date) -> None:
        for account in self.accounts:
            account.start_balance = self.cleaned_data[self.key(account)]
            account.save(update_fields=["start_balance"])
        self.budget.nemkonto_min = self.cleaned_data["nemkonto_min"]
        self.budget.nemkonto_max = self.cleaned_data["nemkonto_max"]
        self.budget.everyday_spending = self.cleaned_data["everyday_spending"] or 0
        self.budget.balances_on = today
        self.budget.save(
            update_fields=["nemkonto_min", "nemkonto_max", "everyday_spending", "balances_on"]
        )

    def keep_typed_balances(self) -> None:
        """Remember the balances typed so far, e.g. before adding another account."""
        for account in self.accounts:
            try:
                value = self.fields[self.key(account)].clean(self.data.get(self.key(account)))
            except forms.ValidationError:
                continue
            account.start_balance = value
            account.save(update_fields=["start_balance"])


class NewAccountForm(UniqueNameInBudget, forms.ModelForm):
    noun = "an account"

    class Meta:
        model = Account
        fields = ["name"]
        labels = {"name": "Name of the new account"}


class QuickExpenseForm(ExpenseForm):
    """Step 2 of the setup: the essentials of an expense on one line."""

    starting_balance = None
    fill_from_savings = None
    topup = None
    first_amount = AmountField(
        required=False,
        allow_negative=False,
        label="Amount of that payment",
        help_text="For example 2.000 when the payment on the next due date covers two months. "
        "Later payments are the normal amount.",
    )

    class Meta(ExpenseForm.Meta):
        fields = [
            "name",
            "amount",
            "interval_months",
            "first_due",
            "first_amount",
            "account",
            "category",
            "kind",
        ]
        labels = {**ExpenseForm.Meta.labels, "first_due": "Next due date"}
        help_texts = {}
        widgets = {"first_due": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].widget = forms.Select(choices=KIND_CHOICES)


class QuickIncomeForm(IncomeSourceForm):
    """Step 4 of the setup: an income on one line."""

    end_month = None
    first_month = MonthField(label="First month it is for")

    class Meta(IncomeSourceForm.Meta):
        fields = ["name", "amount", "interval_months", "first_month"]
