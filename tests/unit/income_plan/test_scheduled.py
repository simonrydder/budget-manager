import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.income_category import IncomeCategory
from budget_manager.models.income_plan import ScheduledIncomePlan


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-04-05"):
        yield


@pytest.fixture
def category() -> IncomeCategory:
    return IncomeCategory("Salary")


def test_that_expected_income_for_may_is_500(category: IncomeCategory):
    plan = ScheduledIncomePlan(500)
    assert plan.monthly_expected_income(category, 5, 2025) == 500


def test_that_exptected_income_for_may_is_1000(category: IncomeCategory):
    plan = ScheduledIncomePlan(1000)

    assert plan.monthly_expected_income(category, 5, 2025) == 1000


def test_that_expected_income_before_start_date_of_today_is_0(category: IncomeCategory):
    plan = ScheduledIncomePlan(1000)
    assert plan.monthly_expected_income(category, 3, 2025) == 0


def test_that_expected_income_before_start_date_is_0(category: IncomeCategory):
    plan = ScheduledIncomePlan(400, start_date=Date(2025, 6, 2))

    assert plan.monthly_expected_income(category, 5, 2025) == 0


def test_that_expexted_income_same_month_as_start_date_is_0(category: IncomeCategory):
    plan = ScheduledIncomePlan(400, start_date=Date(2025, 5, 1))

    assert plan.monthly_expected_income(category, 5, 2025) == 0


def test_that_expected_income_after_end_date_is_0(category: IncomeCategory):
    # Start time is 2025-04-05 -> last salary is 2025-05-05
    plan = ScheduledIncomePlan(300, end_date=Date(2025, 6, 1))

    assert plan.monthly_expected_income(category, 7, 2025) == 0


def test_that_expexted_incomes_at_end_date_is_included(category: IncomeCategory):
    plan = ScheduledIncomePlan(300, start_date=Date(2025, 3, 1), end_date=Date(2025, 6, 1))

    assert plan.monthly_expected_income(category, 7, 2025) == 300


def test_that_expeted_income_in_may_is_0_with_repetiontion_2_months_and_start_march(
    category: IncomeCategory,
):
    plan = ScheduledIncomePlan(500, repetition=Duration(months=2), start_date=Date(2025, 3, 1))

    assert plan.monthly_expected_income(category, 5, 2025) == 0


def test_one_time_income_not_on_start_month(category: IncomeCategory):
    plan = ScheduledIncomePlan(750, repetition=None, start_date=Date(2025, 5, 15))
    # Should pay because requested month/year matches start_date
    assert plan.monthly_expected_income(category, 5, 2025) == 0


def test_one_time_income_on_month_after_start_month(category: IncomeCategory):
    plan = ScheduledIncomePlan(750, repetition=None, start_date=Date(2025, 5, 15))
    # Should not pay because requested month/year does not match
    assert plan.monthly_expected_income(category, 6, 2025) == 750


def test_recurring_income_exact_occurrence(category: IncomeCategory):
    plan = ScheduledIncomePlan(500, repetition=Duration(months=1), start_date=Date(2025, 3, 1))
    # Should pay 500 in May (3 -> 4 -> 5)
    assert plan.monthly_expected_income(category, 5, 2025) == 500


def test_recurring_income_multiple_occurrences_in_month(category: IncomeCategory):
    # Example: repetition = 15 days, may have two payments in May
    plan = ScheduledIncomePlan(200, repetition=Duration(days=15), start_date=Date(2025, 4, 20))
    # May has payments on 2025-05-05 and 2025-05-20 -> used in june
    assert plan.monthly_expected_income(category, 6, 2025) == 400


def test_recurring_income_respecting_end_date(category: IncomeCategory):
    plan = ScheduledIncomePlan(
        300, repetition=Duration(months=1), start_date=Date(2025, 3, 1), end_date=Date(2025, 5, 1)
    )
    # May is still within end_date, should get payment used in June
    assert plan.monthly_expected_income(category, 6, 2025) == 300
    # June has no payment as it is after end_date, should be 0
    assert plan.monthly_expected_income(category, 7, 2025) == 0
