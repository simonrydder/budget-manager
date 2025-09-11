import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.allocation_plan import AllocationPlan
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.record import Record


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-09-26"):
        yield


@pytest.fixture
def expenses() -> list[Record]:
    return [
        Record(name="i", amount=10, timestamp=Date(2025, 2, 1) + i * Duration(days=1))
        for i in range(200)
    ]


@pytest.fixture
def groceries_goal() -> AllocationPlan:
    return AllocationPlan(
        target_amount=400,
        target_date=Date(2025, 2, 1),
        repetition=Duration(months=1),
        start_date=Date(2025, 1, 26),
    )


@pytest.fixture
def groceries(groceries_goal: AllocationPlan, expenses: list[Record]) -> ExpenseCategory:
    return ExpenseCategory("Groceries", [groceries_goal], expenses=expenses)


def test_that_total_expenses_for_groceries_in_february_is_280(groceries: ExpenseCategory):
    assert groceries.actual_expense(2, 2025) == 280


def test_that_total_expenses_for_groceries_in_march_is_310(groceries: ExpenseCategory):
    assert groceries.actual_expense(3, 2025) == 310


def test_that_monthly_saving_for_groceries_in_february_is_400(groceries: ExpenseCategory):
    assert groceries.allocation(2, 2025) == 400


def test_that_balance_for_groceries_in_february_is_120(groceries: ExpenseCategory):
    assert groceries.balance(2, 2025) == 120


def test_that_balance_for_phone_in_february_is_45():
    phone = ExpenseCategory(
        "Phone",
        [
            AllocationPlan(
                target_amount=200,
                target_date=Date(2025, 2, 1),
                repetition=None,
                start_date=Date(2025, 1, 26),
            )
        ],
        expenses=[Record(name="Phone Bill", amount=155, timestamp=Date(2025, 2, 14))],
    )

    assert phone.balance(2, 2025) == 45


def test_that_balance_for_groceries_in_march_is_210(groceries: ExpenseCategory):
    assert groceries.balance(3, 2025) == 210  # 120 + 90 (february + march)


def test_that_balance_for_wifi_in_march_is_500():
    wifi = ExpenseCategory(
        "Wifi",
        [
            AllocationPlan(
                target_amount=600,
                target_date=Date(2025, 4, 1),
                repetition=Duration(months=3),
                start_amount=300,
                start_date=Date(2025, 1, 26),
            )
        ],
        expenses=[Record(name="Wifi bill", amount=600, timestamp=Date(2025, 4, 3))],
    )

    # 500 = 300 + 100 + 100 (starting_amount + 2 * monthly_saving)
    assert wifi.balance(3, 2025) == 500


def test_that_saving_for_multiple_allocation_plans_in_may_is_500(groceries: ExpenseCategory):
    new_plan = AllocationPlan(
        target_amount=100,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=1),
        start_date=Date(2025, 4, 1),
    )
    groceries.allocations.append(new_plan)

    assert groceries.allocation(5, 2025) == 500


def test_that_saving_for_multile_allocation_plans_in_february_is_400(groceries: ExpenseCategory):
    new_plan = AllocationPlan(
        target_amount=100,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=1),
        start_date=Date(2025, 4, 1),
    )
    groceries.allocations.append(new_plan)

    assert groceries.allocation(2, 2025) == 400


def test_that_expected_expense_for_groceries_is_400_in_february(groceries: ExpenseCategory):
    assert groceries.expected_expense(2, 2025) == 400


def test_that_expected_expense_for_category_without_allocation_plan_is_0():
    cat = ExpenseCategory("New Cat")

    assert cat.expected_expense(2, 2025) == 0


def test_that_balance_uses_expected_expense_in_future(groceries: ExpenseCategory):
    with freeze_time("2025-04-04"):
        assert groceries.balance(5, 2025) == 310


def test_that_expense_uses_actual_in_current_month(groceries: ExpenseCategory):
    with freeze_time("2025-04-04"):
        groceries.expenses.append(Record(1000))
        assert groceries.expense(4, 2025) == 1300
