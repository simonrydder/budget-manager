import pytest
from freezegun import freeze_time
from pendulum import Date, Duration

from budget_manager.models.allocation_plan import AllocationPlan


@pytest.fixture(scope="module", autouse=True)
def freeze_time_for_tests():
    with freeze_time("2025-03-26"):
        yield


@pytest.fixture
def rent() -> AllocationPlan:
    return AllocationPlan(
        target_amount=10000,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=1),
        end_date=Date(2025, 12, 1),
    )


@pytest.fixture
def car() -> AllocationPlan:
    return AllocationPlan(
        target_amount=2800,
        target_date=Date(2025, 5, 1),
        repetition=Duration(months=1),
        start_amount=0,
    )


@pytest.fixture
def wifi() -> AllocationPlan:
    return AllocationPlan(
        target_amount=600,
        target_date=Date(2025, 4, 1),
        repetition=Duration(months=3),
        start_amount=300,
        end_date=Date(2025, 12, 1),
    )


@pytest.fixture
def phone() -> AllocationPlan:
    return AllocationPlan(
        target_amount=100,
        target_date=Date(2025, 8, 1),
        repetition=None,
    )


def test_that_april_allocation_for_rent_is_10000(rent: AllocationPlan):
    assert rent.monthly_allocation(4, 2025) == 10000


def test_that_juni_allocation_for_car_is_2800(car: AllocationPlan):
    assert car.monthly_allocation(6, 2025) == 2800


def test_that_may_allocation_for_Car_is_1400(car: AllocationPlan):
    assert car.monthly_allocation(5, 2025) == 1400


def test_that_april_allocation_for_wifi_is_200(wifi: AllocationPlan):
    assert wifi.monthly_allocation(4, 2025) == 300


def test_that_january_2026_allocation_for_rent_is_0(rent: AllocationPlan):
    assert rent.monthly_allocation(1, 2026) == 0


def test_that_may_allocation_for_wifi_is_200(wifi: AllocationPlan):
    assert wifi.monthly_allocation(5, 2025) == 200


def test_that_july_allocation_for_rent_is_10000(rent: AllocationPlan):
    assert rent.monthly_allocation(7, 2025) == 10000


def test_that_june_allocation_for_wifi_is_200(wifi: AllocationPlan):
    assert wifi.monthly_allocation(6, 2025) == 200


def test_that_september_allocation_for_phone_is_0(phone: AllocationPlan):
    assert phone.monthly_allocation(9, 2025) == 0


def test_that_november_allocation_for_wifi_is_0(wifi: AllocationPlan):
    assert wifi.monthly_allocation(11, 2025) == 0


def test_that_june_allocation_for_rent_is_0_after_changed_end_date(rent: AllocationPlan):
    assert rent.monthly_allocation(6, 2025) == 10000
    rent.end_date = Date(2025, 5, 1)
    assert rent.monthly_allocation(6, 2025) == 0


def test_that_january_allocation_for_rent_is_0(rent: AllocationPlan):
    assert rent.monthly_allocation(1, 2025) == 0
