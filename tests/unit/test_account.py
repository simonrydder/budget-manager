import pytest

from budget_manager.models.account import Account
from budget_manager.models.amount import Amount


@pytest.fixture(scope="function")
def account() -> Account:
    return Account(name="Test Account", _balance=Amount.from_float(100))


def test_that_account_has_name(account: Account):
    assert account.name == "Test Account"


def test_that_account_has_balance(account: Account):
    assert account.balance == Amount(10000)


@pytest.mark.parametrize("amount", [Amount(5050), Amount(100), Amount(0)])
def test_that_account_can_deposit(account: Account, amount: Amount):
    initial_balance = account.balance
    account.deposit(amount)
    assert account.balance == initial_balance + amount


def test_that_account_can_only_deposit_positive_amounts(account: Account):
    with pytest.raises(ValueError):
        account.deposit(Amount(-50))


@pytest.mark.parametrize("amount", [Amount(50500), Amount(100), Amount(0)])
def test_that_account_can_withdraw(account: Account, amount: Amount):
    inital_balance = account.balance
    account.withdraw(amount)
    assert account.balance == inital_balance - amount  # Assuming initial balance was 10000


def test_that_account_can_only_withdraw_positive_amounts(account: Account):
    with pytest.raises(ValueError):
        account.withdraw(Amount(-50))
