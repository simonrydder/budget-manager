# Changelog

Every version merged into `prod`, newest first. The numbers follow
[Semantic Versioning](https://semver.org/): fixes raise the last number, new features the
middle one.

## 1.4.0 (2026-10-09)

- Layouts follow the room the page has, not the window: on an iPad or in a split-screen window
  the overview and other pages switch to one column instead of squeezing two.
- Expenses: each category (or account) is a full-width section with its cards in rows, can be
  folded, and shows what it costs a month. Drag and drop works as before.
- Accounts: an account's expenses fold into one line with their total when there are many.
- Overview: Coming up shows the first 10 payments, the rest behind "Show more".
- Month-end step 1 shows the expenses due that month; the rest fold into "N more, not due".
- Names in lists and tables are plain text that opens the expense, instead of blue links.
- The menu is grouped: Overview, Month-end, Balance · Expenses, Income, Accounts · Forecast,
  History · Settings, Budgets, People.
- Windows launcher: when an update changes the launcher itself, it hands over to the new one
  right away, so new launcher features (like Update now) do not wait for the next restart.

## 1.3.2 (2026-10-09)

- Coming up on the overview no longer calls payments after the next month-end "short" when
  the month-end transfers before them bring the money: they are *on track*. *Ready* means the
  money is there now, and *short* only shows when even the planned transfers do not cover it.

## 1.3.1 (2026-10-09)

- Fix: starting a budget again reused a bill's payment from the first start even after its due
  date had been moved to next month, so the bill was set aside nothing but still counted as
  paid and showed a negative balance. Bills now always follow their current due date; only what
  was typed for running budgets is kept.

## 1.3.0 (2026-10-09)

- `BudgetManager.cmd` needs no login: the app only serves that computer, so it signs in by
  itself (and hides Log out and People). Any other device would still have to log in.
- `BudgetManager.cmd` checks for a newer version before downloading it: ordinary updates install
  by themselves, a major update (a new first number) shows what is new and asks first. It also
  starts faster when nothing changed.
- On the home network each device stays logged in for a year instead of 30 days.
- `budget-manager --version` and `budget-manager check-update`.

## 1.2.0 (2026-10-09)

- `BudgetManager.cmd`: one file to download from GitHub and double-click to run the app on
  your own Windows computer. It installs uv (which brings Python and the app) without
  administrator rights, gets the newest version on every start, opens the browser and only
  accepts that computer.

## 1.1.0 (2026-10-09)

- The Windows launcher checks `prod` for a new commit every 5 minutes (`-CheckMinutes`) and
  restarts the app with it, instead of updating only at night. A version that does not start is
  rolled back and skipped until a newer commit arrives (for example a revert).
- The scheduled task now only starts the app with Windows; `-At` adds a nightly restart if
  wanted. Re-run `install-nightly-task.ps1` to drop the old nightly trigger.

## 1.0.0 (2026-10-09)

The first numbered version. It contains everything built so far:

- Several budgets per person, each set up in five steps: accounts and today's balances,
  expenses (fixed, variable and running; a different first payment where needed), a summary
  per category, income, and the transfers that start the budget. Starting sets aside exactly
  what keeps every monthly transfer the same and is the ground truth from then on.
- The month-end checklist: spending (including everyday spending from the NemKonto), interest,
  income, the transfers and closing. The NemKonto ends between its minimum and maximum, with
  General Savings taking the rest or covering a shortfall.
- Balance: moves between General Savings and the expenses on any day.
- Overview, expenses board with the monthly cost, the next payment and how much of it is there,
  forecast (everyday spending learned from the last six month-ends) and history.
- Runs on the home network and over Tailscale only.
- Windows launcher that updates every night, and an **Update now** button in Settings that
  updates to the newest version from any device.
