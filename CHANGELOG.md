# Changelog

Every version merged into `prod`, newest first. The numbers follow
[Semantic Versioning](https://semver.org/): fixes raise the last number, new features the
middle one.

## 1.12.2 (2026-11-01)

- Moving a due date from the 1st to the last day of the month before gives that month two
  payments. The month-end took them for one payment at twice the price, so it planned to raise
  the expense's amount and set aside twice as much from then on. Exactly two (or more) times the
  amount now counts as several payments: the extra one comes from General Savings and the amount
  stays.
- The forecast and the expense pages count moves waiting under Balance as made with the next
  month-end's transfers, like the month-end itself, so a waiting top-up no longer shows a
  different plan there.

## 1.12.1 (2026-11-01)

- Tapping or clicking an amount field selects the whole number, so typing replaces it instead of
  having to delete it first. Leaving the field without typing keeps the number.

## 1.12.0 (2026-11-01)

- The month-end step bar showed step 1 while on step 3 (and step 3 on step 1). Every page now
  takes its number from the same list as the step bar.
- Interest is entered on the income page, below the income, and an empty field counts as 0. The
  month-end has four steps: income and interest, spending, transfers, check and close. A
  month-end in progress continues on the same page.
- A refund can belong on another account than the one it arrived on, for example an electricity
  refund paid to the NemKonto that belongs on Budget. It goes to that account's expense (choose
  which when it has several) instead of General Savings, with one transfer straight there.
- An overdraft the bank covered is recorded on the account that went below zero instead of an
  expense; the expense is only asked for when the account has several. The bank takes it from
  the NemKonto unless you change it, and it can also cover General Savings.
- Balance sends money straight from an account that sends to one that receives, instead of
  through the account holding General Savings.

## 1.11.1 (2026-11-01)

- An account's standing order is switched on with a tick box, and its amount starts as what the
  account's expenses get a month (their contributions at the next month-end). Keep it, or type
  the amount your bank sends instead.

## 1.11.0 (2026-11-01)

- The month-end reads the bank as it stood at the end of the last day, so money that came and
  went in between no longer needs working out by hand.
  - The checklist starts with income and interest, then spending. A month-end in progress that
    had passed step 1 starts again at income; what was entered is kept.
  - What was spent from the NemKonto: type its balance at the end of the last day and the app
    works out the spending from what it had after the last month-end, the income, its interest
    and the standing orders. *What it should hold* shows the sum. It no longer matters on which
    day each income arrived.
- Standing orders: an account can have a fixed amount the bank sends from the NemKonto on the
  last bank day (Danish bank closing days are known). The Transfers step shows only the rest to
  send, or to send back, and a transfer the standing order covers in full is done by itself.
- Overdrafts the bank covered by itself (an account went below zero and the bank took money from
  Savings or the NemKonto) can be recorded under Balance, or from step 3. They count as made at
  once, so both accounts match the bank, and one from the NemKonto is not counted as everyday
  spending.
- Check & close lists payments due on a weekend or holiday at the very end of the month, which
  the bank draws in the new month.

## 1.10.0 (2026-10-13)

- Moves still waiting under Balance at a month-end go with its transfers: their money is added
  to the month-end transfer of each account (and taken from, or added to, the one to the account
  holding General Savings), so there is one transfer per account instead of moving the money
  first and then again. Step 4 shows a *Moves under Balance* part on each transfer and lists the
  moves included; they count as made when the month-end is closed, and reopening the month-end
  puts them back on the waiting list. This replaces the separate **Transfers made** in step 4
  from 1.9.0. If General Savings is too small for the moves, step 4 says so and the month-end
  waits until some are cancelled.

## 1.9.0 (2026-10-13)

- Month-end step 4 (Transfers) includes the moves still waiting under Balance: it lists them and
  the bank transfers they need, above the month-end transfers, and **Transfers made** there makes
  them. The month-end transfers then take them into account, so you no longer have to leave the
  month-end for the Balance page before closing. Cancelling a move is still done under Balance.

## 1.8.1 (2026-10-13)

- Windows launcher: an update could leave the old version running for good. Before updating, the
  launcher sometimes took its own server for another program ("is not the server started
  earlier"), left it running and stopped, so the old version kept the port. It now stops the
  server it started itself, and stops any Budget Manager still running on the port, for example
  one whose launcher has stopped. If you are stuck on an older version, start the launcher once
  by hand (`start-budget.cmd`, or restart the computer); after that it updates as it should.

## 1.8.0 (2026-10-13)

- Every new version on `prod` becomes a
  [GitHub release](https://github.com/simonrydder/budget-manager/releases) with its changes as
  the notes, once the tests pass.
- Settings → App version says when a newer version is out, warns when **Update now** was not
  picked up (the launcher on the computer has stopped) or a newer version did not install or
  start, and shows the end of the launcher's log.

## 1.7.0 (2026-10-10)

- Month-end step 1: every row, the NemKonto's included, has two fields side by side, **Spent**
  and **Balance after**. Type either one and the other follows, so you can copy whichever number
  the bank shows. This replaces the separate "Or type what is left" field. Setup step 5 does
  the same for running budgets (**Spent so far** and **Left**).

## 1.6.1 (2026-10-09)

- People and the page of a closed month-end fit on a phone: their tables hide the less
  important columns on narrow screens.
- A user guide (`docs/user-guide.md`) that walks through every page, and an updated README,
  requirements and design for this version: the three ways to run the app, every setting,
  updates, backups and troubleshooting.

## 1.6.0 (2026-10-09)

- Running budgets (food, fuel, …) can be entered as what was spent or as what is left: in
  month-end step 1 and setup step 5, typing what is left works out the spending, and typing the
  spending shows what is left.

## 1.5.0 (2026-10-09)

- Month-end step 1 fills in the fixed payments that were due with their amount (change it if
  one cost something else). Variable and running expenses stay empty, since only you know what
  they cost; payments from before the budget was started were settled by the setup.
- A month-end step can be undone: "Undo step N" marks the last finished step as not done and
  goes back to it, keeping what was entered. Right after closing a month-end, the next one
  offers to reopen it.

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
