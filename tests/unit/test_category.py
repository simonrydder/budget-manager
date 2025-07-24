import pytest

from budget_manager.models.amount import Amount
from budget_manager.models.category import Category, CategoryLimitExceededException


@pytest.fixture(scope="function")
def house() -> Category:
    return Category(name="House")


@pytest.fixture(scope="function")
def wifi() -> Category:
    return Category(name="WiFi")


@pytest.fixture(scope="function")
def other() -> Category:
    return Category(name="Other")


def test_that_category_has_name_house(house: Category):
    assert house.name == "House"


def test_that_category_can_be_renamed(house: Category):
    house.name = "New House"
    assert house.name == "New House"


def test_that_category_has_no_children_by_default(house: Category):
    assert house.children is None


def test_that_category_can_add_child(house: Category, wifi: Category):
    house.add_child(wifi)
    assert house.children is not None
    assert house.children[0] == wifi


def test_that_category_can_search_for_child(house: Category, wifi: Category):
    house.add_child(wifi)
    assert wifi in house


def test_that_category_can_search_for_child_when_no_children(house: Category, wifi: Category):
    assert wifi not in house


def test_that_category_can_search_for_non_existent_child(
    house: Category, other: Category, wifi: Category
):
    house.add_child(other)
    assert wifi not in house


def test_that_category_can_add_two_children(house: Category, wifi: Category, other: Category):
    house.add_child(wifi)
    house.add_child(other)
    assert house.children is not None
    assert len(house.children) == 2
    assert wifi in house
    assert other in house


def test_that_category_can_remove_child(house: Category, wifi: Category):
    house.add_child(wifi)
    assert house.children is not None
    house.remove_child(wifi)
    assert wifi not in house


def test_that_category_can_remove_single_child(house: Category, wifi: Category, other: Category):
    house.add_child(wifi)
    house.add_child(other)
    assert house.children is not None
    house.remove_child(wifi)
    assert wifi not in house
    assert other in house


def test_that_category_can_not_remove_child_that_does_not_exsist(
    house: Category, wifi: Category, other: Category
):
    house.add_child(other)
    with pytest.raises(ValueError):
        house.remove_child(wifi)


def test_that_categoty_can_not_remove_child_when_no_children(house: Category, wifi: Category):
    with pytest.raises(ValueError):
        house.remove_child(wifi)


def test_that_adding_child_exceeding_limit_raises_exception(house: Category, wifi: Category):
    house.limit = Amount(1000)
    wifi.limit = Amount(2000)
    with pytest.raises(CategoryLimitExceededException):
        house.add_child(wifi)


def test_that_category_limit_is_larger_than_sum_of_children_limits(
    house: Category, wifi: Category, other: Category
):
    house.limit = Amount(5000)
    wifi.limit = Amount(2000)
    other.limit = Amount(3500)

    house.add_child(wifi)
    with pytest.raises(CategoryLimitExceededException):
        house.add_child(other)
