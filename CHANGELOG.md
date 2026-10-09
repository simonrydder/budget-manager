# Changelog

Every version merged into `prod`, newest first. The numbers follow
[Semantic Versioning](https://semver.org/): fixes raise the last number, new features the
middle one.

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
