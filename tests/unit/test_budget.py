import pytest
from freezegun import freeze_time

from budget_manager.exeptions import DuplicateCategoryName
from budget_manager.models.budget import Budget
from budget_manager.models.expense_category import ExpenseCategory


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-09-03"):
        yield


@pytest.fixture
def budget() -> Budget:
    return Budget(name="My Budget", start_saving=0)


def test_that_expenses_has_rent_expense_category(budget: Budget):
    rent = ExpenseCategory("Rent")

    budget.add_expense_category(rent)

    assert rent in budget.expenses


def test_that_expenses_can_not_have_two_categories_with_the_same_name(budget: Budget):
    rent = ExpenseCategory("Rent")
    rent2 = ExpenseCategory("Rent")

    budget.add_expense_category(rent)

    with pytest.raises(DuplicateCategoryName):
        budget.add_expense_category(rent2)
