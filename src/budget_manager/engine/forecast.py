"""Run the month-end close forward in time using expected amounts."""

from __future__ import annotations

from dataclasses import dataclass

from budget_manager.engine.close import ClosePlan, apply_close, plan_close
from budget_manager.engine.model import BudgetState
from budget_manager.engine.months import YearMonth


@dataclass
class ForecastMonth:
    """The expected state at the end of ``month``, right after its month-end transfers."""

    month: YearMonth
    close: ClosePlan  # the close made on the last day of ``month``
    expense_balances: dict[int, int]
    account_balances: dict[int, int]
    nemkonto: int
    general_savings: int

    @property
    def budget_month(self) -> YearMonth:
        return self.close.month


def run_forecast(
    state: BudgetState,
    months: int,
    *,
    income: dict[YearMonth, int] | None = None,
    interest: dict[YearMonth, dict[int, int]] | None = None,
    covers: dict[YearMonth, dict[int, int]] | None = None,
    releases: dict[YearMonth, dict[int, int]] | None = None,
    topups: dict[YearMonth, dict[int, int]] | None = None,
) -> list[ForecastMonth]:
    """Forecast ``months`` month-ends, starting with the next close.

    Spending that has not been entered is assumed to equal the expected amount. Income uses
    the expected amounts unless ``income`` holds an actual total for a budget month; the same
    goes for ``interest`` (keyed by the budget month whose transfer it adjusts). ``covers`` and
    ``releases`` hold decisions already made for a close.
    """
    state = state.copy()
    income = income or {}
    interest = interest or {}
    covers = covers or {}
    releases = releases or {}
    topups = topups or {}
    result: list[ForecastMonth] = []
    for _ in range(months):
        month = state.month
        previous = month - 1
        for ledger in state.ledgers:
            if previous not in ledger.spending:
                line = ledger.lines.get(previous)
                if line and line.expected_spend:
                    ledger.spending[previous] = line.expected_spend
        plan = plan_close(
            state,
            income=income.get(month, state.expected_income(month)),
            interest=interest.get(month),
            covers=covers.get(month),
            releases=releases.get(month),
            topups=topups.get(month),
        )
        apply_close(state, plan)
        result.append(
            ForecastMonth(
                month=previous,
                close=plan,
                expense_balances={
                    ledger.expense.id: ledger.balance_after_close(month) for ledger in state.ledgers
                },
                account_balances=state.account_balances_after_close(month),
                nemkonto=state.nemkonto,
                general_savings=state.general_savings,
            )
        )
    return result
