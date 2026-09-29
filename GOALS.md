# Budget Manager: Project Goals (draft for review)

> This is my reading of what the repository is trying to become. I based it on the
> `prod` branch and on two unmerged branches, `feat/data_classes` (Aug 28 – Sep 9, 2025)
> and `new-budget-manager` (Sep 11, 2025). `new-budget-manager` looks like a clean
> rewrite of the first branch. Anything marked **(assumption)** is a guess. Please
> correct or delete it.

---

## 1. Purpose

A personal budgeting tool, written in Python, that answers one main question:

> **"Given what I earn, what I have to pay, and what I'm saving for, how much money
> will I have in each month, past and future?"**

It is a forward-looking planner, not only an expense tracker. It mixes **actual
recorded transactions** for past months with **expected amounts from plans** for
future months. That lets it project balances and savings month by month.

## 2. Core concepts

### 2.1 Records
- A `Record` is one real transaction: `amount`, `timestamp` (date) and an optional `name`.
- A positive amount is money coming in or a deposit. A negative amount is a withdrawal (used in `SavingCategory`).

### 2.2 Income
- An **`IncomeCategory`** (for example "Salary") holds the actual income records and one or more **income plans**.
- **Income paid in month M funds the budget for month M+1.** For example, a salary paid in April is spent in May.
- Income plans (strategy pattern, `IncomePlan` ABC):
  - **`ScheduledIncomePlan`**: a fixed amount on a schedule (`repetition`, `start_date`, `end_date`). It can also be a one-off.
  - **`HistoricalIncomePlan`**: expects next month's income to equal last month's actual income.
- For completed months and the current month, the category reports actual income. For future months it reports expected income.

### 2.3 Expenses and allocation plans (envelope / sinking-fund budgeting)
- An **`ExpenseCategory`** (for example "Rent" or "Car insurance") holds actual expense records and one or more **`AllocationPlan`s**.
- An `AllocationPlan` describes a known cost: `target_amount` due on `target_date`, optionally repeating (`repetition`, such as every 12 months) until `end_date`, with an optional `start_amount` already set aside.
  - **Allocation:** the target is spread evenly over the months between `start_date` and the first `target_date`. After that it is spread over each repetition cycle. For example, a 1200/year insurance bill becomes 100/month.
  - **Expected expense:** the full `target_amount` falls in the month(s) it is due.
- A category has a **running balance**: its starting amount, plus monthly allocations, minus expenses, carried over from month to month. This shows whether each "envelope" has enough money in it when the bill arrives.
- Past and current months use actual expenses. Future months use expected expenses.
  - ⚠️ The two branches disagree about the **current month**. `feat/data_classes` used `max(actual, expected)`, while `new-budget-manager` uses only the actual expense. Which do you want?

### 2.4 Savings
- A **`SavingCategory`** (for example "Emergency fund" or "Holiday") has a `start_amount` and deposit/withdrawal records. It reports monthly deposits, monthly withdrawals and a running balance. `balance` is not implemented yet.

### 2.5 Budget (the aggregate)
- A **`Budget`** has a name, a `start_date` and a `start_saving`. It contains income categories and expense categories (and saving categories, per the rewrite **(assumption)**).
- `Budget.saving(month, year)` = income − expenses + the previous month's saving. It is computed recursively back to `start_date`.
- Category names must be unique within a budget (`DuplicateCategoryName`).
- **Accounts:** an expense category can be linked to an account, such as the bank account it is paid from. The budget can then report expenses per account, for example "how much must I transfer to the bills account each month". `DuplicatedAccountName` suggests accounts will become named, first-class objects **(assumption)**.

### 2.6 Ideas from the earlier branch that may be dropped (please confirm)
- **`Amount`**: money stored as integer cents to avoid float rounding. The rewrite went back to `float`.
- **`Category` hierarchy**: nested categories with spending limits, where children cannot go over the parent's limit.
- **`Account`** with deposit and withdraw on a balance.

## 3. Time handling
- The unit of planning is the **calendar month** (`month: 1–12`, `year`).
- Dates use `pendulum`. Tests freeze "today" with `freezegun`.
- Helpers: `next_first`, `month_shifter`, `is_completed_month`, `is_current_month` and `is_date_in_month`.

## 4. Engineering goals (from repo setup)
- Python ≥ 3.12, managed with **uv** (`uv_build` backend) and packaged as `budget-manager`, with a console script `budget-manager = budget_manager:main`.
- Code style: **ruff**, line length 100. Tests: **pytest** under `tests/unit`, written test-first and using frozen dates.
- **Conventional commits** with **commitizen** (`cz_conventional_commits`, tags `v$version`).
- Git flow: feature branches → `dev` → `prod`, both protected. CI runs lint and tests on pushes and PRs to `dev` and `prod`.
- Automated version bump and changelog on merge to `prod` was tried (a `cd.yml` using a deploy key) but was removed. It could be brought back later.

## 5. Not yet decided (the repo gives no answer; please fill in)
1. **Interface**: CLI, TUI, web app, or only a library for now? `main()` just prints "Hello".
2. **Persistence**: how is a budget saved and loaded (JSON/YAML file, SQLite, …)?
3. **Data entry**: are records entered by hand, or imported from bank CSV exports?
4. **Currency**: one currency only? Floats, or integer cents (`Amount`)?
5. **Which branch to build on**: I propose `new-budget-manager` as the base and porting `Budget` and accounts from `feat/data_classes` into it.
6. **Reporting**: which views matter most? For example a month overview, a per-category balance timeline, a per-account transfer plan, or a savings projection.
7. **Multi-user or shared budgets**: needed or not?

## 6. Proposed first milestone (for discussion)
1. Settle the domain model on the `new-budget-manager` base: `Record`, `IncomeCategory` with plans, `ExpenseCategory` with `AllocationPlan`, `SavingCategory` (finish `balance`), and `Budget` with accounts.
2. Save and load a budget to and from a file.
3. A minimal CLI to add categories and plans, record transactions, and print a month overview and a 12-month projection.
4. Keep CI green: ruff plus pytest with good unit coverage.
