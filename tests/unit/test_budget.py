import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.exeptions import DuplicateCategoryName
from budget_manager.models.allocation_plan import AllocationPlan
from budget_manager.models.budget import Budget
from budget_manager.models.expense import Expense
from budget_manager.models.expense_category import ExpenseCategory
from budget_manager.models.income import Income
from budget_manager.models.income_category import IncomeCategory
from budget_manager.models.income_plan import ScheduledIncomePlan


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-09-03"):
        yield


@pytest.fixture
def budget() -> Budget:
    return Budget(name="My Budget", start_saving=200, start_date=Date(2025, 4, 16))


def test_that_expenses_has_added_expense_category(budget: Budget):
    rent = ExpenseCategory("Rent")

    budget.add_expense_category(rent)

    assert rent in budget.expenses


def test_that_expenses_can_not_have_two_categories_with_the_same_name(budget: Budget):
    rent = ExpenseCategory("Rent")
    rent2 = ExpenseCategory("Rent")

    budget.add_expense_category(rent)

    with pytest.raises(DuplicateCategoryName):
        budget.add_expense_category(rent2)


def test_that_incomes_has_added_income_category(budget: Budget):
    salary = IncomeCategory("Salary")
    budget.add_income_category(salary)

    assert salary in budget.incomes


def test_that_incomes_can_not_have_two_categories_with_the_same_name(budget: Budget):
    salary1 = IncomeCategory("Salary")
    salary2 = IncomeCategory("Salary")

    budget.add_income_category(salary1)

    with pytest.raises(DuplicateCategoryName):
        budget.add_income_category(salary2)


def test_that_saving_include_start_saving(budget: Budget):
    assert budget.saving(1, 1) == 200


def test_that_saving_include_income_category(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-03
    income = IncomeCategory("Salary", [ScheduledIncomePlan(200)])
    budget.add_income_category(income)

    assert budget.saving(9, 2025) == 200
    assert budget.saving(10, 2025) == 400


def test_that_saving_include_income_category_recurssive(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-03
    income = IncomeCategory("Salary", [ScheduledIncomePlan(200)])
    budget.add_income_category(income)

    assert budget.saving(12, 2025) == 800


def test_that_saving_include_expense_category(budget: Budget):
    expense = ExpenseCategory("Rent", [AllocationPlan(100, Date(2025, 10, 1), Duration(months=1))])
    budget.add_expense_category(expense)

    assert budget.saving(11, 2025) == 0


def test_that_saving_include_actual_income(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-03
    income_cat = IncomeCategory(
        "Salary",
        [ScheduledIncomePlan(350, start_date=Date(2025, 5, 1))],
        [Income("First", 300, Date(2025, 7, 31)), Income("Second", 349, Date(2025, 8, 29))],
    )
    budget.add_income_category(income_cat)

    assert budget.saving(9, 2025) == 849  # 200 + 300 + 349


def test_that_saving_include_acutal_expense(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-03
    expense = ExpenseCategory(
        "Rent",
        [AllocationPlan(50, Date(2025, 6, 1), Duration(months=1))],
        [Expense("First", 55, Date(2025, 6, 1)), Expense("Second", 40, Date(2025, 7, 1))],
    )
    budget.add_expense_category(expense)

    assert budget.saving(8, 2025) == 105  # 200 - 55 - 40
    assert budget.saving(10, 2025) == 5  # 200 - 55 - 40 - 50 - 50


def test_that_budget_has_income_function(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-0
    income_cat = IncomeCategory(
        "Salary",
        [ScheduledIncomePlan(350, start_date=Date(2025, 5, 1))],
        [Income("First", 300, Date(2025, 7, 31)), Income("Second", 349, Date(2025, 8, 29))],
    )
    budget.add_income_category(income_cat)

    assert budget.income(8, 2025) == 300
    assert budget.income(10, 2025) == 350


def test_that_budget_has_expense_function(budget: Budget):
    # Start date = 2025-04-16, Current date = 2025-09-03
    expense = ExpenseCategory(
        "Rent",
        [AllocationPlan(50, Date(2025, 6, 1), Duration(months=1))],
        [Expense("First", 55, Date(2025, 6, 1)), Expense("Second", 40, Date(2025, 7, 1))],
    )
    budget.add_expense_category(expense)

    assert budget.expense(7, 2025) == 40
    assert budget.expense(9, 2025) == 50
    assert budget.expense(10, 2025) == 50


def test_that_expense_for_account_household_is_75(budget: Budget):
    car = ExpenseCategory("Car", [AllocationPlan(65, Date(2025, 6, 1), Duration(months=1))])

    rent = ExpenseCategory("Rent", [AllocationPlan(75, Date(2025, 6, 1), Duration(months=1))])

    budget.add_expense_category(car)
    budget.add_expense_category(rent, "Household")

    assert budget.expense(10, 2025, "Household") == 75


def test_that_expense_is_max_of_expected_and_actual_in_current_month(budget: Budget):
    rent = ExpenseCategory(
        "Rent",
        [AllocationPlan(25, Date(2025, 6, 1), Duration(months=1))],
        [Expense("First", 80, Date(2025, 9, 1))],
    )
    car = ExpenseCategory(
        "Car",
        [AllocationPlan(25, Date(2025, 6, 1), Duration(months=1))],
        [Expense("First", 20, Date(2025, 9, 1))],
    )

    budget.add_expense_category(rent, "Household")
    budget.add_expense_category(car, "Other")

    assert budget.expense(9, 2025, "Household") == 80
    assert budget.expense(9, 2025, "Other") == 25


def test_that_budget_has_account_none(budget: Budget):
    rent = ExpenseCategory("Rent")
    budget.add_expense_category(rent)

    assert None in budget.accounts


def test_that_budget_has_account_household(budget: Budget):
    rent = ExpenseCategory("Rent")
    budget.add_expense_category(rent, "Household")

    assert "Household" in budget.accounts
