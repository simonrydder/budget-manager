import pytest
from freezegun import freeze_time
from pendulum import Date

from budget_manager.models.income_category import IncomeCategory
from budget_manager.models.income_plan import HistoricalIncomePlan
from budget_manager.models.record import Record


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-03-26"):
        yield


@pytest.fixture
def salary() -> IncomeCategory:
    return IncomeCategory(name="Salary", income_plans=[HistoricalIncomePlan()])


def test_that_income_is_1000(salary: IncomeCategory):
    new_income = Record(1000)
    salary.incomes.append(new_income)

    assert salary.actual_income(4, 2025) == 1000


def test_that_income_is_2000(salary: IncomeCategory):
    new_income = Record(2000)
    salary.incomes.append(new_income)

    assert salary.actual_income(4, 2025) == 2000


def test_that_income_is_1500(salary: IncomeCategory):
    first_income = Record(1000)
    second_income = Record(500)

    salary.incomes.append(first_income)
    salary.incomes.append(second_income)

    assert salary.actual_income(4, 2025) == 1500


def test_that_income_in_april_is_1000(salary: IncomeCategory):
    first_income = Record(1000)
    salary.incomes.append(first_income)

    second_income = Record(500, Date(2025, 4, 15))
    salary.incomes.append(second_income)

    assert salary.actual_income(4, 2025) == 1000


def test_that_income_in_may_is_500(salary: IncomeCategory):
    first_income = Record(1000)
    salary.incomes.append(first_income)

    second_income = Record(500, Date(2025, 4, 15))
    salary.incomes.append(second_income)

    assert salary.actual_income(5, 2025) == 500


def test_that_income_in_may_is_1000_and_in_june_is_500(salary: IncomeCategory):
    first_income = Record(1000, Date(2025, 4, 1))
    second_income = Record(500, Date(2025, 5, 1))
    salary.incomes.append(first_income)
    salary.incomes.append(second_income)

    assert salary.actual_income(5, 2025) == 1000
    assert salary.actual_income(6, 2025) == 500


def test_that_expected_income_in_may_is_1000(salary: IncomeCategory):
    salary.incomes.append(Record(1000, Date(2025, 3, 15)))

    assert salary.expected_income(5, 2025) == 1000


def test_that_expected_income_in_may_is_500(salary: IncomeCategory):
    salary.incomes.append(Record(500, Date(2025, 3, 31)))

    assert salary.expected_income(5, 2025) == 500


def test_that_expected_income_with_two_income_plans_sum(salary: IncomeCategory):
    salary.incomes.append(Record(500, Date(2025, 3, 31)))
    salary.income_plans.append(HistoricalIncomePlan())

    assert salary.expected_income(5, 2025) == 1000
