import pytest
from freezegun import freeze_time
from pendulum import Date

from budget_manager.models.record import Record
from budget_manager.models.saving_category import SavingCategory


@pytest.fixture(scope="function", autouse=True)
def freeze_today():
    with freeze_time("2025-09-11"):
        yield


@pytest.fixture
def saving() -> SavingCategory:
    return SavingCategory("Saving")


def test_that_deposits_for_may_is_100(saving: SavingCategory):
    saving.records.append(Record(100, Date(2025, 5, 3)))

    assert saving.deposits(5, 2025) == 100


def test_that_deposits_for_april_is_400(saving: SavingCategory):
    saving.records.append(Record(400, Date(2025, 4, 14)))

    assert saving.deposits(4, 2025) == 400


def test_that_deposits_for_april_include_sum_of_multiple_records(saving: SavingCategory):
    saving.records.append(Record(400, Date(2025, 4, 1)))
    saving.records.append(Record(400, Date(2025, 4, 15)))

    assert saving.deposits(4, 2025) == 800


def test_that_deposits_for_april_only_include_april_records(saving: SavingCategory):
    saving.records.append(Record(300, Date(2025, 4, 30)))
    saving.records.append(Record(400, Date(2025, 5, 14)))

    assert saving.deposits(4, 2025) == 300


def test_that_deposits_only_uses_positive_record_amounts(saving: SavingCategory):
    saving.records.append(Record(-10, Date(2025, 9, 11)))

    assert saving.deposits(9, 2025) == 0


def test_that_withdrawals_for_june_is_200(saving: SavingCategory):
    saving.records.append(Record(-200, Date(2025, 6, 7)))

    assert saving.withdrawals(6, 2025) == 200


def test_that_withdrawals_only_uses_negative_values(saving: SavingCategory):
    saving.records.append(Record(-100, Date(2025, 5, 1)))
    saving.records.append(Record(500, Date(2025, 5, 2)))

    assert saving.withdrawals(5, 2025) == 100
