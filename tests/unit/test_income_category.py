import pytest
from freezegun import freeze_time
from pendulum import Date

from budget_manager.models.income import Income
from budget_manager.models.income_category import IncomeCategory


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-03-26"):
        yield


@pytest.fixture
def salary() -> IncomeCategory:
    return IncomeCategory(name="Salary")


def test_that_income_is_1000(salary: IncomeCategory):
    new_income = Income(None, 1000)
    salary.incomes.append(new_income)

    assert salary.monthly_income(4, 2025) == 1000


def test_that_income_is_2000(salary: IncomeCategory):
    new_income = Income(None, 2000)
    salary.incomes.append(new_income)

    assert salary.monthly_income(4, 2025) == 2000


def test_that_income_is_1500(salary: IncomeCategory):
    first_income = Income(None, 1000)
    second_income = Income(None, 500)

    salary.incomes.append(first_income)
    salary.incomes.append(second_income)

    assert salary.monthly_income(4, 2025) == 1500


def test_that_income_in_april_is_1000(salary: IncomeCategory):
    first_income = Income(None, 1000)
    salary.incomes.append(first_income)

    second_income = Income(None, 500, Date(2025, 4, 15))
    salary.incomes.append(second_income)

    assert salary.monthly_income(4, 2025) == 1000


def test_that_income_in_may_is_500(salary: IncomeCategory):
    first_income = Income(None, 1000)
    salary.incomes.append(first_income)

    second_income = Income(None, 500, Date(2025, 4, 15))
    salary.incomes.append(second_income)

    assert salary.monthly_income(5, 2025) == 500
