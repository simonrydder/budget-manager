import random
from dataclasses import replace
from datetime import date

import pytest

from budget_manager.engine import CloseError, Kind, Line, YearMonth, apply_close, plan_close

from .helpers import BUDGET, FOOD, MAY, NEM, SAVINGS, expense, kr, state

APRIL = YearMonth(2025, 4)


def household(**kwargs):
    """Rent on Budget, groceries on Food and a holiday goal on Savings."""
    return state(
        [
            expense(1, 10000, date(2025, 5, 1), name="Rent"),
            expense(2, 4000, date(2025, 5, 1), account=FOOD, kind=Kind.VARIABLE, name="Groceries"),
            expense(3, 30000, date(2026, 3, 1), 12, account=SAVINGS, name="Holiday"),
        ],
        **kwargs,
    )


def amounts(plan):
    return {account_id: transfer.amount for account_id, transfer in plan.transfers.items()}


def assert_consistent(budget, plan):
    """Money is only moved around: nothing appears or disappears in a close."""
    balances_before = sum(line.balance_before for line in plan.lines.values())
    balances_after = sum(line.balance_after for line in plan.lines.values())
    before = balances_before + budget.nemkonto + budget.general_savings
    after = balances_after + plan.nemkonto_end + plan.general_savings_after
    assert after == before + plan.income + plan.interest_total
    sent = sum(amounts(plan).values())
    nem_interest = plan.interest.get(NEM, 0)
    assert plan.nemkonto_end == budget.nemkonto + plan.income + nem_interest - sent


def test_surplus_above_maximum_goes_to_general_savings():
    budget = household()
    plan = plan_close(budget, income=kr(25000))
    # Holiday: 30.000 over 11 transfers (May–March) = 2.727,27, rounded up.
    assert plan.lines[3].contribution == kr(2728)
    assert plan.nemkonto_after_transfers == kr(3000 + 25000 - 16728)
    assert plan.surplus == kr(6272)
    assert plan.nemkonto_end == kr(5000)
    assert plan.general_savings_after == kr(16272)
    assert amounts(plan) == {BUDGET: kr(10000), FOOD: kr(4000), SAVINGS: kr(2728 + 6272)}
    assert plan.notices == []
    assert plan.transfer_date == date(2025, 4, 30)
    assert_consistent(budget, plan)


def test_nothing_moves_when_the_nemkonto_ends_between_its_limits():
    budget = household()
    plan = plan_close(budget, income=kr(18500))
    assert plan.nemkonto_end == kr(3000 + 18500 - 16728)
    assert plan.surplus == plan.taken == 0
    assert amounts(plan)[SAVINGS] == kr(2728)
    assert_consistent(budget, plan)


def test_shortfall_below_minimum_is_taken_from_general_savings():
    budget = household()
    plan = plan_close(budget, income=kr(15000))
    assert plan.nemkonto_after_transfers == kr(1272)
    assert plan.taken == kr(728)
    assert plan.nemkonto_end == kr(2000)
    assert plan.general_savings_after == kr(10000 - 728)
    assert amounts(plan)[SAVINGS] == kr(2728 - 728)
    assert plan.notices == []
    assert_consistent(budget, plan)


def test_warning_when_general_savings_cannot_cover_the_minimum():
    budget = household(general_savings=500)
    plan = plan_close(budget, income=kr(15000))
    assert plan.taken == kr(500)
    assert plan.nemkonto_end == kr(1772)
    assert plan.general_savings_after == 0
    assert [n.code for n in plan.notices] == ["savings_cannot_cover_nemkonto"]
    assert plan.shortfall == 0
    assert_consistent(budget, plan)


def test_below_zero_needs_covers_before_closing():
    budget = household(general_savings=0)
    plan = plan_close(budget, income=kr(10000))
    assert plan.nemkonto_end == kr(-3728)
    assert plan.shortfall == kr(3728)
    codes = [n.code for n in plan.notices]
    assert codes == ["savings_cannot_cover_nemkonto", "nemkonto_below_zero"]

    covered = plan_close(budget, income=kr(10000), covers={3: kr(2728), 2: kr(1000)})
    assert covered.shortfall == 0
    assert covered.nemkonto_end == 0
    assert amounts(covered) == {BUDGET: kr(10000), FOOD: kr(3000), SAVINGS: 0}
    assert covered.lines[3].balance_after == 0
    assert_consistent(budget, covered)


def test_cover_cannot_take_more_than_the_expense_has():
    budget = household(general_savings=0)
    with pytest.raises(CloseError):
        plan_close(budget, income=kr(10000), covers={3: kr(3000)})
    with pytest.raises(CloseError):
        plan_close(budget, income=kr(10000), covers={99: kr(10)})
    with pytest.raises(CloseError):
        plan_close(budget, income=kr(10000), interest={99: kr(10)})


def test_covered_expense_is_rebuilt_by_later_contributions():
    budget = household(general_savings=0)
    apply_close(budget, plan_close(budget, income=kr(10000), covers={3: kr(2728), 2: kr(1000)}))
    budget.ledger(2).spending[MAY] = kr(3000)
    plan = plan_close(budget, income=kr(40000))
    # The holiday goal lost May's 2.728 and now has 10 transfers left to reach 30.000.
    assert plan.lines[3].contribution == kr(3000)


def test_interest_reduces_the_transfer_to_that_account():
    budget = household()
    plan = plan_close(budget, income=kr(25000), interest={BUDGET: kr(30), FOOD: kr(-15)})
    assert amounts(plan)[BUDGET] == kr(9970)
    assert amounts(plan)[FOOD] == kr(4015)
    assert plan.surplus == kr(6272 + 30 - 15)
    assert plan.nemkonto_end == kr(5000)
    assert_consistent(budget, plan)


def test_interest_on_the_nemkonto_counts_as_income():
    budget = household()
    plan = plan_close(budget, income=kr(18500), interest={NEM: kr(12.5)})
    assert plan.nemkonto_end == kr(3000 + 18500 + 12.5 - 16728)
    assert_consistent(budget, plan)


def rent_paid_more_than_expected(general_savings=10000):
    budget = household(month=MAY, general_savings=general_savings)
    rent = budget.ledger(1)
    rent.expense = replace(rent.expense, start_month=APRIL)
    rent.lines[APRIL] = Line(contribution=kr(10000), expected_spend=kr(10000))
    rent.spending[APRIL] = kr(10500)
    return budget


def test_fixed_expense_below_zero_is_topped_up_and_its_amount_raised():
    budget = rent_paid_more_than_expected()
    plan = plan_close(budget, income=kr(25000))
    line = plan.lines[1]
    assert line.balance_before == kr(-500)
    assert line.topup == kr(500)
    assert line.amount_after == kr(10500)
    assert line.contribution == kr(10500)
    assert line.balance_after == kr(10500)
    assert plan.surplus == kr(3000 + 25000 - (10500 + 4000 + 2728) - 5000)
    assert plan.general_savings_after == kr(10000) + plan.surplus - kr(500)
    assert amounts(plan)[BUDGET] == kr(11000)
    assert [n.code for n in plan.notices] == ["fixed_topped_up"]
    assert "raised from 10.000,00 to 10.500,00" in plan.notices[0].message
    assert_consistent(budget, plan)

    apply_close(budget, plan)
    assert budget.ledger(1).expense.amount == kr(10500)


def test_fixed_top_up_limited_by_general_savings():
    budget = rent_paid_more_than_expected(general_savings=200)
    plan = plan_close(budget, income=kr(18500))  # no surplus this month
    assert plan.surplus == 0
    assert plan.lines[1].topup == kr(200)
    assert plan.general_savings_after == 0
    codes = [n.code for n in plan.notices]
    assert codes == ["fixed_topped_up", "savings_cannot_cover_fixed"]
    assert_consistent(budget, plan)


def test_early_payment_is_topped_up_without_changing_the_amount():
    budget = household()
    insurance = expense(5, 1200, date(2025, 12, 1), 12, name="Insurance")
    budget.ledgers.append(insurance)
    for _ in range(6):
        apply_close(budget, plan_close(budget, income=kr(25000)))
    insurance.spending[YearMonth(2025, 10)] = kr(1200)  # charged in October, due December
    plan = plan_close(budget, income=kr(25000))
    assert plan.lines[5].topup == plan.lines[5].topup_needed > 0
    assert plan.lines[5].amount_after is None


def test_release_moves_money_to_general_savings_without_a_new_transfer():
    budget = household()
    disney = expense(9, 89, date(2025, 1, 5), end=date(2025, 4, 30), starting_balance=150)
    budget.ledgers.append(disney)
    plan = plan_close(budget, income=kr(18500), releases={9: kr(150)})
    assert plan.lines[9].balance_after == 0
    assert plan.general_savings_after == kr(10150)
    assert amounts(plan)[BUDGET] == kr(10000 - 150)
    assert amounts(plan)[SAVINGS] == kr(2728 + 150)
    assert_consistent(budget, plan)


def test_apply_close_moves_to_the_next_month():
    budget = household()
    plan = plan_close(budget, income=kr(25000))
    apply_close(budget, plan)
    assert budget.month == YearMonth(2025, 6)
    assert budget.nemkonto == plan.nemkonto_end
    assert budget.general_savings == plan.general_savings_after
    assert budget.ledger(1).lines[MAY].contribution == kr(10000)
    with pytest.raises(CloseError):
        apply_close(budget, plan)


def test_random_months_never_create_or_lose_money():
    rng = random.Random(7)
    for _ in range(40):
        budget = household(nemkonto=rng.randint(-2000, 8000), general_savings=rng.randint(0, 20000))
        budget.ledgers.append(expense(4, rng.randint(100, 3000), date(2025, 7, 15), 3))
        budget.ledgers.append(
            expense(5, rng.randint(100, 900), date(2025, 5, 3), kind=Kind.VARIABLE)
        )
        for _ in range(8):
            previous = budget.month - 1
            for ledger in budget.ledgers:
                line = ledger.lines.get(previous)
                if line:
                    ledger.spending[previous] = (
                        rng.choice([0, line.expected_spend]) + rng.randint(0, 800) * 100
                    )
            interest = {rng.choice([NEM, BUDGET, FOOD, SAVINGS]): rng.randint(-50, 80) * 100}
            plan = plan_close(budget, income=kr(rng.randint(12000, 30000)), interest=interest)
            assert_consistent(budget, plan)
            assert plan.general_savings_after >= min(0, budget.general_savings)
            apply_close(budget, plan)


def test_chosen_top_up_restores_a_variable_expense_from_general_savings():
    budget = household()
    apply_close(budget, plan_close(budget, income=kr(25000)))
    budget.ledger(2).spending[MAY] = kr(4500)  # groceries 500 over
    plan = plan_close(budget, income=kr(18500), topups={2: kr(500)})
    line = plan.lines[2]
    assert line.balance_before == kr(-500)
    assert line.topup == kr(500)
    assert line.contribution == kr(4000)  # the plan is unchanged
    assert line.balance_after == kr(4000)
    assert amounts(plan)[FOOD] == kr(4500)
    assert [n.code for n in plan.notices] == ["topped_up"]
    assert_consistent(budget, plan)


def test_chosen_top_up_is_limited_by_general_savings():
    budget = household(general_savings=100)
    plan = plan_close(budget, income=kr(18500), topups={2: kr(300)})
    assert plan.lines[2].topup == kr(100)
    assert plan.general_savings_after == 0
    assert "savings_cannot_cover_fixed" in [n.code for n in plan.notices]
    assert_consistent(budget, plan)
