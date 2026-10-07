from dataclasses import replace
from datetime import date

from budget_manager.engine import Kind, Line, YearMonth, apply_close, plan_close

from .helpers import MAY, expense, kr, state


def run_months(budget, count, *, spend_expected=True):
    """Close ``count`` months with no income checks, spending exactly what was expected."""
    plans = []
    for _ in range(count):
        if spend_expected:
            previous = budget.month - 1
            for ledger in budget.ledgers:
                line = ledger.lines.get(previous)
                if line and line.expected_spend and previous not in ledger.spending:
                    ledger.spending[previous] = line.expected_spend
        plan = plan_close(budget, income=kr(100000))
        apply_close(budget, plan)
        plans.append(plan)
    return plans


def test_monthly_expense_contributes_its_amount_every_month():
    rent = expense(1, 10692.55, date(2025, 5, 1))
    budget = state([rent])
    plans = run_months(budget, 3)
    assert [p.lines[1].contribution for p in plans] == [kr(10692.55)] * 3
    assert rent.balance_after_close(YearMonth(2025, 7)) == kr(10692.55)


def test_yearly_expense_uses_the_same_amount_every_month():
    insurance = expense(1, 500, date(2025, 12, 1), 12)
    budget = state([insurance])
    plans = run_months(budget, 20)
    contributions = [p.lines[1].contribution for p in plans]
    # May–December: 8 transfers of 500/8 = 62,50 rounded up, so 4 over.
    assert contributions[:8] == [kr(63)] * 8
    assert insurance.balance_after_close(YearMonth(2025, 12)) == kr(504)
    # The next year starts from the 4 left over: 496/12 rounded up.
    assert contributions[8:20] == [kr(42)] * 12


def test_small_yearly_payment_overshoots_rather_than_varying():
    fee = expense(1, 66, date(2026, 4, 1), 12, start=YearMonth(2025, 5))
    budget = state([fee])
    plans = run_months(budget, 24)
    contributions = [p.lines[1].contribution for p in plans]
    assert contributions[:12] == [kr(6)] * 12  # 72 saved for 66
    assert contributions[12:24] == [kr(5)] * 12  # starts with 6 left: 60/12


def test_changed_amount_is_caught_up_by_the_due_date():
    # The example from the requirements: 500 a year, then it turns out to be 600.
    insurance = expense(1, 500, date(2025, 12, 1), 12, start=YearMonth(2025, 1))
    budget = state([insurance], month=YearMonth(2025, 1))
    run_months(budget, 6)
    saved = insurance.balance_after_close(YearMonth(2025, 6))
    assert saved == kr(252)  # 6 × 42

    insurance.expense = replace(insurance.expense, amount=kr(600))
    plans = run_months(budget, 6)
    remaining = [p.lines[1].contribution for p in plans]
    assert remaining == [kr(58)] * 5 + [kr(58)]
    assert insurance.balance_after_close(YearMonth(2025, 12)) == kr(600)


def test_starting_balance_counts_towards_the_next_payment():
    goal = expense(1, 30000, date(2026, 3, 1), 12, account=4, starting_balance=8000)
    budget = state([goal])
    plan = plan_close(budget, income=kr(50000))
    # May 2025 to March 2026 is 11 transfers for the missing 22.000.
    assert plan.lines[1].contribution == kr(2000)


def test_one_off_savings_goal_needs_a_monthly_contribution():
    school = expense(1, 60000, date(2030, 5, 1), 0, account=4)
    budget = state([school])
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].contribution == kr(984)  # 60.000 over 61 transfers, rounded up


def test_ended_and_future_expenses_get_nothing():
    ended = expense(1, 89, date(2025, 1, 5), end=date(2025, 4, 30))
    later = expense(2, 100, date(2025, 8, 1), start=YearMonth(2025, 7))
    budget = state([ended, later])
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].contribution == 0
    assert plan.lines[2].contribution == 0
    assert plan.lines[2].expected_spend == 0


def test_variable_expense_ignores_actual_spending():
    parking = expense(1, 100, date(2025, 5, 1), kind=Kind.VARIABLE)
    budget = state([parking])
    apply_close(budget, plan_close(budget, income=kr(50000)))
    parking.spending[MAY] = kr(260)  # spent far more than planned
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].contribution == kr(100)
    assert plan.lines[1].balance_before == kr(-160)
    assert plan.lines[1].topup == 0
    assert [n.code for n in plan.notices] == ["variable_below_zero"]


def test_leftover_on_fixed_expense_stays_in_the_pot():
    phone = expense(1, 150, date(2025, 5, 20))
    budget = state([phone])
    apply_close(budget, plan_close(budget, income=kr(50000)))
    phone.spending[MAY] = kr(120)
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].contribution == kr(150)
    assert plan.lines[1].balance_after == kr(180)


def test_late_payment_does_not_trigger_a_top_up():
    rent = expense(1, 1000, date(2025, 5, 1))
    budget = state([rent])
    apply_close(budget, plan_close(budget, income=kr(50000)))
    rent.spending[MAY] = 0  # May's rent was not charged yet
    apply_close(budget, plan_close(budget, income=kr(50000)))
    rent.spending[YearMonth(2025, 6)] = kr(2000)  # charged twice in June
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].balance_before == 0
    assert plan.lines[1].topup == 0
    assert plan.lines[1].amount_after is None


def test_planned_balance_uses_frozen_expected_spending():
    ledger = expense(1, 500, date(2025, 12, 1), 12)
    ledger.lines[MAY] = Line(contribution=kr(63))
    ledger.lines[YearMonth(2025, 6)] = Line(contribution=kr(63))
    assert ledger.planned_balance_before(YearMonth(2025, 7)) == kr(126)
    assert ledger.planned_balance_before(YearMonth(2025, 6)) == kr(63)


OCT, NOV = YearMonth(2026, 10), YearMonth(2026, 11)


def started_mid_month(amount, first_due, interval=12, **kwargs):
    ledger = expense(1, amount, first_due, interval, start=NOV, **kwargs)
    ledger.expense = replace(ledger.expense, opening_month=OCT)
    return ledger


def test_suggested_balance_keeps_the_monthly_amount_steady():
    # Insurance 1.200 due 1 December; starting on 7 October. Steady rate 100: two transfers
    # (end of October and November) are left, so 1.000 should already be there.
    insurance = started_mid_month(1200, date(2026, 12, 1))
    assert insurance.expense.suggested_starting_balance() == kr(1000)
    insurance.expense = replace(insurance.expense, starting_balance=kr(1000))
    budget = state([insurance], month=NOV)
    plans = run_months(budget, 14)
    assert {p.lines[1].contribution for p in plans} == {kr(100)}


def test_payment_due_later_this_month_must_be_there_in_full():
    phone = started_mid_month(199, date(2026, 10, 20), 1)
    assert phone.expense.suggested_starting_balance() == kr(199)
    yearly_this_month = started_mid_month(600, date(2026, 10, 25))
    assert yearly_this_month.expense.suggested_starting_balance() == kr(600)


def test_monthly_budget_already_running_counts_this_months_payment():
    groceries = started_mid_month(5500, date(2026, 10, 1), 1, kind=Kind.VARIABLE)
    assert groceries.expense.suggested_starting_balance() == kr(5500)
    groceries.expense = replace(groceries.expense, starting_balance=kr(5500))
    groceries.spending[OCT] = kr(3200)  # spent so far when starting
    budget = state([groceries], month=NOV)
    assert groceries.balance_end_of(OCT) == kr(2300)
    plan = plan_close(budget, income=kr(50000))
    assert plan.lines[1].contribution == kr(5500)  # October's payment came from the start


def test_one_off_goal_has_no_suggestion():
    school = started_mid_month(60000, date(2030, 8, 1), 0)
    assert school.expense.suggested_starting_balance() is None
