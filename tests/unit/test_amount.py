import pytest

from budget_manager.models.amount import Amount


def test_amount_is_integer():
    amount = Amount(100)
    assert isinstance(amount.value, int), "Amount value should be an integer"


def test_that_amount_from_float_returns_amount_instance():
    amt = Amount.from_float(1)
    assert isinstance(amt, Amount)


@pytest.mark.parametrize("value", [100.0, 0.0, -50.5, 42.42])
def test_that_amount_from_float_converts_float_to_integer(value: float):
    amt = Amount.from_float(value)
    assert isinstance(amt.value, int)
    assert amt.value == (int(100 * value))


@pytest.mark.parametrize(
    "value, expected", [(100, 1.0), (0, 0.0), (-50, -0.5), (4242, 42.42)]
)
def test_that_amount_to_float_returns_correct_float(value: int, expected: float):
    amt = Amount(value)
    float_value = amt.to_float()
    assert isinstance(float_value, float)
    assert float_value == expected, f"Expected {expected}, got {float_value}"


@pytest.mark.parametrize(
    "first, second, expected", [(100, 200, 3.0), (1, 2, 0.03), (200, -200, 0.0)]
)
def test_amount_addition(first: int, second: int, expected: float):
    amt1 = Amount(first)
    amt2 = Amount(second)
    result = (amt1 + amt2).to_float()
    assert isinstance(result, float)
    assert result == expected, f"Expected {expected}, got {result}"


def test_amount_subtraction():
    amt1 = Amount(100)
    amt2 = Amount(50)
    result = (amt1 - amt2).to_float()
    assert isinstance(result, float)
    assert result == 0.5, f"Expected 0.5, got {result}"


@pytest.mark.parametrize(
    "value, expected",
    [(1000, "10.00"), (12345, "123.45"), (-555555, "-5555.55"), (0, "0.00")],
)
def test_amount_str_representation(value: int, expected: str):
    amt = Amount(value)
    assert str(amt) == expected, f"Expected '{expected}', got '{str(amt)}'"


def test_amount_equality_requires_other_to_be_amount():
    with pytest.raises(TypeError):
        assert Amount(100) == 100


def test_amount_equality():
    amt1 = Amount(100)
    amt2 = Amount.from_float(1.00)
    amt3 = Amount(200)

    assert amt1 == amt2, "Amounts should be equal"
    assert amt1 != amt3, "Amounts should not be equal"


def test_that_amount_can_compare_with_other_amounts():
    amt1 = Amount(100)
    amt2 = Amount(200)

    assert amt1 < amt2, "Amount 100 should be less than 200"
    assert amt2 > amt1, "Amount 200 should be greater than 100"
    assert amt1 <= amt2, "Amount 100 should be less than or equal to 200"
    assert amt2 >= amt1, "Amount 200 should be greater than or equal to 100"


def test_that_sum_operator_works_with_amounts():
    amt1 = Amount(100)
    amt2 = Amount(200)
    result = sum([amt1, amt2])
    assert isinstance(result, Amount), "Sum should return an Amount instance"
    assert result.value == 300, "Sum of 100 and 200 should be 300"


def test_that_sum_with_float_raises_type_error():
    amt = Amount(100)
    with pytest.raises(TypeError):
        sum([50.0, amt])  # Should raise TypeError since 50.0 is not an Amount instance


def test_that_amount_can_be_divided_with_int():
    amt = Amount(100)
    assert amt / 10 == Amount(10)


def test_that_amount_can_be_devided_with_float():
    amt = Amount(100)
    assert amt / 0.5 == Amount(200)


def test_that_division_result_is_rounded_up():
    amt = Amount(100)
    res = amt / 3
    assert res == Amount(34)


def test_that_division_with_amount_are_allowed():
    assert Amount(100) / Amount(2) == Amount(50)
