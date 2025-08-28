import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.saving_goal import SavingGoal


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-03-26"):
        yield


@pytest.fixture
def rent() -> SavingGoal:
    return SavingGoal(
        target_amount=10000,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=1),
        end_date=Date(2025, 12, 1),
    )


@pytest.fixture
def car() -> SavingGoal:
    return SavingGoal(
        target_amount=2800,
        target_date=Date(2025, 5, 1),
        repetition=Duration(months=1),
        start_amount=0,
    )


@pytest.fixture
def wifi() -> SavingGoal:
    return SavingGoal(
        target_amount=600,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=3),
        start_amount=300,
        end_date=Date(2025, 12, 1),
    )


@pytest.fixture
def phone() -> SavingGoal:
    return SavingGoal(
        target_amount=100,
        target_date=Date(2025, 8, 1),
        repetition=None,
    )


def test_that_april_saving_for_rent_is_10000(rent: SavingGoal):
    assert rent.get_saving_amount(4, 2025) == 10000


def test_that_juni_saving_for_car_is_2800(car: SavingGoal):
    assert car.get_saving_amount(6, 2025) == 2800


def test_that_may_saving_for_Car_is_1400(car: SavingGoal):
    assert car.get_saving_amount(5, 2025) == 1400


def test_that_april_saving_for_wifi_is_200(wifi: SavingGoal):
    assert wifi.get_saving_amount(4, 2025) == 300


def test_that_january_2026_saving_for_rent_is_0(rent: SavingGoal):
    assert rent.get_saving_amount(1, 2026) == 0


def test_that_may_saving_for_wifi_is_200(wifi: SavingGoal):
    assert wifi.get_saving_amount(5, 2025) == 200


def test_that_july_saving_for_rent_is_10000(rent: SavingGoal):
    assert rent.get_saving_amount(7, 2025) == 10000


def test_that_june_saving_for_wifi_is_200(wifi: SavingGoal):
    assert wifi.get_saving_amount(6, 2025) == 200


def test_that_september_saving_for_phone_is_0(phone: SavingGoal):
    assert phone.get_saving_amount(9, 2025) == 0


def test_that_november_saving_for_wifi_is_0(wifi: SavingGoal):
    assert wifi.get_saving_amount(11, 2025) == 0


def test_that_june_saving_for_rent_is_0_after_changed_end_date(rent: SavingGoal):
    assert rent.get_saving_amount(6, 2025) == 10000
    rent.end_date = Date(2025, 5, 1)
    assert rent.get_saving_amount(6, 2025) == 0
