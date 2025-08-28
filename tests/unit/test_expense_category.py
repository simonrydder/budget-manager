import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.allocation_plan import AllocationPlan
from budget_manager.models.expense import Expense
from budget_manager.models.expense_category import ExpenseCategory


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
def groceries_goal() -> AllocationPlan:
    return AllocationPlan(
        target_amount=400,
        target_date=Date(2025, 2, 1),
        repetition=Duration(months=1),
    )


@pytest.fixture
def groceries(groceries_goal: AllocationPlan, expenses: list[Expense]) -> ExpenseCategory:
    return ExpenseCategory("Groceries", groceries_goal, expenses=expenses)


def test_that_total_expenses_for_groceries_in_february_is_280(groceries: ExpenseCategory):
    assert groceries.get_monthly_expense_total(2, 2025) == 280


def test_that_total_expenses_for_groceries_in_march_is_310(groceries: ExpenseCategory):
    assert groceries.get_monthly_expense_total(3, 2025) == 310


def test_that_monthly_saving_for_groceries_in_february_is_400(groceries: ExpenseCategory):
    assert groceries.get_monthly_saving(2, 2025) == 400


def test_that_balance_for_groceries_in_february_is_120(groceries: ExpenseCategory):
    assert groceries.get_monthly_balance(2, 2025) == 120


def test_that_balance_for_phone_in_february_is_45():
    phone = ExpenseCategory(
        "Phone",
        AllocationPlan(target_amount=200, target_date=Date(2025, 2, 1), repetition=None),
        expenses=[Expense("Phone Bill", 155, Date(2025, 2, 14))],
    )

    assert phone.get_monthly_balance(2, 2025) == 45


def test_that_balance_for_groceries_in_march_is_210(groceries: ExpenseCategory):
    assert groceries.get_monthly_balance(3, 2025) == 210  # 120 + 90 (february + march)


def test_that_balance_for_wifi_in_march_is_500():
    wifi = ExpenseCategory(
        "Wifi",
        AllocationPlan(
            target_amount=600,
            target_date=Date(2025, 4, 1),
            repetition=Duration(months=3),
            start_amount=300,
        ),
        expenses=[Expense("Wifi bill", 600, Date(2025, 4, 3))],
    )

    # 500 = 300 + 100 + 100 (starting_amount + 2 * monthly_saving)
    assert wifi.get_monthly_balance(3, 2025) == 500
