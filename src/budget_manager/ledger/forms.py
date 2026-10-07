from __future__ import annotations

from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from budget_manager.engine import FREQUENCIES, YearMonth, format_input, parse_amount
from budget_manager.ledger.models import (
    Account,
    BalanceCorrection,
    BudgetSettings,
    Category,
    Expense,
    IncomeSource,
)

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


class ExpenseForm(forms.ModelForm):
    amount = AmountField(
        allow_negative=False,
        label="Amount",
        help_text="The expected amount each time it is due.",
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
        self.fields["account"].queryset = Account.objects.exclude(role="nemkonto")
        self.fields["account"].empty_label = None
        self.fields["category"].empty_label = "Uncategorised"
        self.fields["category"].required = False
        if not self.instance.pk:
            budget = Account.objects.filter(name__iexact="budget").first()
            if budget:
                self.fields["account"].initial = budget.pk

    fill_from_savings = forms.BooleanField(
        required=False,
        label="Fill from General Savings",
        help_text="Moves in what a steady monthly amount would already have saved, so it saves "
        "the same every month. Without it, the first payment is split over the months left.",
    )
    topup = AmountField(
        required=False,
        allow_negative=False,
        label="Top up from General Savings",
        help_text="Moves this amount from General Savings to the expense at the next month-end.",
    )

    def clean_starting_balance(self):
        return self.cleaned_data.get("starting_balance") or 0

    def clean(self):
        data = super().clean()
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


class IncomeSourceForm(forms.ModelForm):
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


class AccountForm(forms.ModelForm):
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


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]


class SettingsForm(forms.ModelForm):
    start_month = MonthField(
        label="First budget month",
        help_text="Its transfers are made on the last day of the month before.",
    )
    nemkonto_min = AmountField(allow_negative=False, label="NemKonto minimum (X)")
    nemkonto_max = AmountField(allow_negative=False, label="NemKonto maximum (Y)")
    nemkonto_opening = AmountField(
        label="NemKonto balance at the start",
        help_text="What is on the NemKonto before the first income arrives.",
    )
    general_savings_opening = AmountField(label="General Savings at the start")
    forecast_months = forms.IntegerField(min_value=3, max_value=120, label="Forecast length")

    class Meta:
        model = BudgetSettings
        fields = [
            "start_month",
            "nemkonto_min",
            "nemkonto_max",
            "nemkonto_opening",
            "general_savings_opening",
            "forecast_months",
        ]

    def __init__(self, *args, started: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = started
        if started:
            for name in ("start_month", "nemkonto_opening", "general_savings_opening"):
                self.fields[name].disabled = True
                self.fields[name].help_text = "Locked after the first month-end. Use a correction."

    def clean(self):
        data = super().clean()
        low, high = data.get("nemkonto_min"), data.get("nemkonto_max")
        if low is not None and high is not None and high < low:
            self.add_error("nemkonto_max", "The maximum must be at least the minimum.")
        return data


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
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["username", "first_name"]
        labels = {"first_name": "Name"}
