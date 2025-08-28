import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.expense import Expense
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.saving_goal import SavingGoal


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-01-26"):
        yield


@pytest.fixture
def expenses() -> list[Expense]:
    return [
        Expense(name="i", amount=10, timestamp=Date(2025, 2, 1) + i * Duration(days=1))
        for i in range(200)
    ]


@pytest.fixture
def groceries_goal() -> SavingGoal:
    return SavingGoal(
        target_amount=400,
        target_date=Date(2025, 2, 1),
        repetition=Duration(months=1),
    )


@pytest.fixture
def groceries(groceries_goal: SavingGoal, expenses: list[Expense]) -> ExpenseCategory:
    return ExpenseCategory("Groceries", groceries_goal, expenses=expenses)


def test_that_total_expenses_for_groceries_in_february_is_280(groceries: ExpenseCategory):
    assert groceries.get_monthly_expense_total(2, 2025) == 280


def test_that_total_expenses_for_groceries_in_march_is_310(groceries: ExpenseCategory):
    assert groceries.get_monthly_expense_total(3, 2025) == 310


def test_that_monthly_saving_for_groceries_in_february_is_400(groceries: ExpenseCategory):
    assert groceries.get_monthly_saving(2, 2025) == 400
