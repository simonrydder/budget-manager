from datetime import date

from budget_manager.engine import (
    Account,
    BudgetState,
    Expense,
    ExpenseLedger,
    Income,
    Kind,
    MonthSchedule,
    Role,
    Schedule,
    YearMonth,
)

NEM, BUDGET, FOOD, SAVINGS = 1, 2, 3, 4
MAY = YearMonth(2025, 5)


def kr(amount: float) -> int:
    """Hundredths from a readable amount."""
    return round(amount * 100)


def accounts(min_balance: float = 2000, max_balance: float = 5000) -> list[Account]:
    return [
        Account(NEM, "NemKonto", Role.NEMKONTO, kr(min_balance), kr(max_balance)),
        Account(BUDGET, "Budget", Role.NORMAL),
        Account(FOOD, "Food", Role.NORMAL),
        Account(SAVINGS, "Savings", Role.SAVINGS),
    ]


def expense(
    expense_id: int,
    amount: float,
    first_due: date,
    interval: int = 1,
    *,
    account: int = BUDGET,
    kind: Kind = Kind.FIXED,
    start: YearMonth = MAY,
    starting_balance: float = 0,
    end: date | None = None,
    name: str | None = None,
) -> ExpenseLedger:
    return ExpenseLedger(
        Expense(
            id=expense_id,
            name=name or f"Expense {expense_id}",
            account_id=account,
            kind=kind,
            amount=kr(amount),
            schedule=Schedule(first_due, interval, end),
            start_month=start,
            starting_balance=kr(starting_balance),
        )
    )


def salary(amount: float, income_id: int = 1, first: YearMonth = MAY) -> Income:
    return Income(income_id, f"Salary {income_id}", kr(amount), MonthSchedule(first, 1))


def state(
    ledgers: list[ExpenseLedger],
    *,
    month: YearMonth = MAY,
    nemkonto: float = 3000,
    general_savings: float = 10000,
    incomes: list[Income] | None = None,
    min_balance: float = 2000,
    max_balance: float = 5000,
) -> BudgetState:
    return BudgetState(
        accounts=accounts(min_balance, max_balance),
        ledgers=ledgers,
        incomes=incomes or [],
        month=month,
        nemkonto=kr(nemkonto),
        general_savings=kr(general_savings),
    )
