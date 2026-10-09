from datetime import date

from budget_manager.engine import (
    Income,
    Kind,
    MonthSchedule,
    YearMonth,
    apply_close,
    plan_close,
    run_forecast,
)

from .helpers import BUDGET, FOOD, MAY, NEM, SAVINGS, expense, kr, salary, state


def household():
    return state(
        [
            expense(1, 10000, date(2025, 5, 1), name="Rent"),
            expense(2, 4000, date(2025, 5, 1), account=FOOD, kind=Kind.VARIABLE),
            expense(3, 30000, date(2026, 3, 1), 12, account=SAVINGS, name="Holiday"),
        ],
        incomes=[salary(25000)],
    )


def test_forecast_uses_expected_amounts_and_keeps_the_nemkonto_at_its_maximum():
    budget = household()
    points = run_forecast(budget, 12)
    assert [p.month for p in points][:2] == [YearMonth(2025, 4), YearMonth(2025, 5)]
    assert points[0].budget_month == MAY
    assert all(p.nemkonto == kr(5000) for p in points)
    # The holiday goal is full right after the transfer at the end of February 2026...
    february = next(p for p in points if p.month == YearMonth(2026, 2))
    assert february.expense_balances[3] == kr(11 * 2728)  # rounded up, a little over 30.000
    # ...and the expected payment in March empties it again.
    march = next(p for p in points if p.month == YearMonth(2026, 3))
    assert march.expense_balances[3] < kr(30000)
    # General Savings grows every month.
    savings = [p.general_savings for p in points]
    assert savings == sorted(savings)
    # The original state is untouched.
    assert budget.month == MAY
    assert budget.ledger(1).lines == {}


def test_account_balances_add_up_expenses_nemkonto_and_general_savings():
    budget = household()
    point = run_forecast(budget, 1)[0]
    assert point.account_balances[NEM] == point.nemkonto
    assert point.account_balances[BUDGET] == point.expense_balances[1]
    assert point.account_balances[FOOD] == point.expense_balances[2]
    assert point.account_balances[SAVINGS] == point.expense_balances[3] + point.general_savings


def test_forecast_uses_entered_spending_and_actual_income():
    budget = household()
    apply_close(budget, plan_close(budget, income=kr(25000)))
    budget.ledger(2).spending[MAY] = kr(4500)  # entered: 500 more than expected
    points = run_forecast(budget, 2, income={YearMonth(2025, 6): kr(20000)})
    assert points[0].expense_balances[2] == kr(-500 + 4000)
    assert points[0].close.income == kr(20000)
    assert points[1].close.income == kr(25000)


def test_forecast_warns_when_income_stops():
    budget = household()
    budget.incomes = [Income(1, "Salary", kr(25000), MonthSchedule(MAY, 1, YearMonth(2025, 8)))]
    points = run_forecast(budget, 8)
    codes = {n.code for p in points for n in p.close.notices}
    assert "nemkonto_below_zero" in codes
    assert points[-1].nemkonto < 0


def test_forecast_expects_the_everyday_spending_from_the_nemkonto():
    budget = household()
    budget.everyday_spending = kr(3000)
    points = run_forecast(budget, 3, nemkonto_spent={MAY: kr(1000)})
    assert [p.close.nemkonto_spent for p in points] == [kr(1000), kr(3000), kr(3000)]
    without = run_forecast(household(), 3)
    # Spending from the NemKonto leaves less to move to General Savings.
    saved = points[-1].general_savings - without[-1].general_savings
    assert saved == -kr(1000 + 3000 + 3000)
