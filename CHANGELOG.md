# Changelog

Every version merged into `prod`, newest first. The numbers follow
[Semantic Versioning](https://semver.org/): fixes raise the last number, new features the
middle one.

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
