# Budget Manager – Requirements

Build a self-hosted **budget manager** web application.

## Technical requirements

- Runs on a local server on the home network and is accessed through a web browser.
- Python is strongly preferred (e.g. Flask, FastAPI or Django) so the code is easy to read and maintain. It is not a hard requirement.
- Any storage works, but all data must be stored locally on the machine running the app.
- Do not display any currency symbol or code. Amounts are shown as plain numbers.
- Multiple users can log in, but the app must only be reachable from the local network (not exposed to the internet). Reaching it from your own devices over Tailscale is allowed.
- Several budgets (for example private and a company), each shared with chosen users. A budget can be copied or started from scratch under its own name.
- A login is only asked for where it protects something: when the app only serves the computer it runs on, there is nothing to log in to. On the home network each device stays logged in for a long time (a year).
- Works on a phone, an iPad and a desktop, also in a split-screen window: no page may need sideways scrolling, and columns follow the room the page actually has.

### Running and updating

- **One file:** someone else must be able to run the app on their own Windows computer by downloading one file from GitHub and double-clicking it, without administrator rights. That copy only serves its own computer.
- **Home server:** on the computer that runs the household's copy, a new version merged into `prod` is picked up within minutes, without anyone doing anything. An **Update now** button (usable from any device, e.g. an iPad) and a script on the computer update right away.
- A version that fails to start is rolled back automatically; reverting the change on GitHub must be enough to recover.
- The database is backed up before every update.
- Versions are numbered with [Semantic Versioning](https://semver.org/) and described in `CHANGELOG.md`. The app shows its version. The one-file copy asks before installing a major (breaking) version.

## Core concepts

### Accounts

Money is spread across several bank accounts, such as Budget, Food and Savings. The app must show the current balance of every account so it is easy to compare with the bank and verify everything is aligned.

Two accounts are special:

- **NemKonto** – where income arrives. After the monthly transfers, its balance should end up between a configurable minimum (X) and maximum (Y).
- **General Savings** – receives surplus and covers shortfalls:
  - If income minus expenses leaves more than Y on the NemKonto, the excess is transferred to General Savings.
  - If it leaves less than X, the difference is taken from General Savings.
  - If General Savings cannot cover it, show a warning and allow the NemKonto to go below X.
  - If the NemKonto would go below 0, ask the user which expense or savings goal to take the money from.

### Monthly cycle

- All transfers happen on the **last day of the month**.
- Expenses can still be due on any day, e.g. a monthly payment on the 15th or a yearly payment on a specific date.

### Expenses

An expense is a planned cost that money is set aside for. Each expense has:

- A name, a **category** (e.g. Insurance, Entertainment, Children, House) and a **linked account**.
- An amount and a schedule, for example:
  - **Monthly**, e.g. a mortgage payment of a fixed amount per month.
  - **Yearly on a fixed date**, e.g. insurance of 500 due on a specific day. Money is saved monthly so the expense's balance equals the full amount on the due date.
  - **One-off savings goal**, e.g. a boarding-school stay in 2030. The app calculates the required monthly contribution.
  - **Recurring savings goal**, e.g. a summer holiday needing 30,000 by March 1st every year.
- An optional **starting balance**, meaning money already in the linked account for this expense.
- An optional **different first payment**, for when the payment on the first due date is not the usual amount. Example: a subscription of 1,000 a month whose first payment covers two months (2,000). Later payments are the usual amount. When the budget is started, the extra part is set aside from General Savings, so the monthly contribution stays 1,000.
- An optional **end date**. Ending an expense (e.g. cancelling Disney+) stops contributions from then on, and the money left on it returns to General Savings.
- An **expense type**: fixed, variable or running (see below).

**Changes over time:** if an expense's amount changes, the monthly contribution is recalculated so the shortfall is covered by the due date. Example: a yearly payment of 500 has 250 saved after 6 months, then it turns out to be 600. The contribution for the remaining 6 months must rise so the balance reaches 600 on the due date.

### Fixed, variable and running expenses

- **Fixed expenses** have a relatively stable amount, paid on a due date (e.g. insurance). If the balance goes negative, the missing amount is taken from General Savings and the expense's expected amount is updated to match the real cost.
- **Variable expenses** are bills paid on a due date whose amount varies (e.g. power, heating).
- **Running expenses** are spent bit by bit through the month (e.g. food, fuel, parking: 100 set aside per month, sometimes less is spent, sometimes more). They are monthly and have no due date.
- **Everyday spending from the NemKonto** is not an expense: what the NemKonto keeps after a month-end (between X and Y) is the money for it. At each month-end the actual spending from the NemKonto is entered, and the month-end refills the NemKonto to between X and Y. The forecast expects the average of the last six month-ends. Until three month-ends have recorded it, the rough monthly amount from the settings fills in for the missing ones.
- For variable and running expenses the balance may go negative or build up, and it is the user's responsibility to adjust the amount.

### Actual spending

Expenses are based on expected costs. Each month the user enters the actual amount spent on each expense, if any. This gives each expense a current balance (contributions minus actual spending). Balances are allowed to go negative.

### Income

- Income sources (e.g. salary, child benefit, interest) have both an **expected** and an **actual** amount, since income varies.
- Salary, benefits etc. arrive on the NemKonto.
- **Interest income and interest expenses** land directly on the account they belong to, not the NemKonto. They are treated as if they had arrived on the NemKonto: if 30 in interest lands on the Budget account, the next transfer to the Budget account is 30 smaller (and correspondingly larger for interest expenses).

## Features

1. **Monthly transfer overview:** how much to transfer from the NemKonto to each account at the end of the month, based on all active expenses, interest adjustments, and the resulting transfer to or from General Savings.
2. **Account balances:** current balance of every account, easy to match against the bank.
3. **Management:** create, edit and end expenses, categories, accounts and income sources.
4. **Monthly entry** of actual spending per expense and actual income per income source, as a step-by-step checklist:
   - fixed payments that were due are filled in with their amount (they can be changed);
   - each expense and the NemKonto can be entered as what was spent or as the balance after (typing one fills in the other);
   - expenses that were not due are folded away;
   - a finished step can be undone, and the latest month-end can be reopened.
5. **History:** actual spending per year and average per month, broken down by expense, category and account.
6. **Forecast:** navigate to future months and see the expected balance of every account and expense.
7. **Warnings** when General Savings can't cover a shortfall, and a prompt to choose where to take money from if the NemKonto would go below 0.
8. **Balancing any day:** moves between General Savings and the expenses (filling a new expense, top-ups, returning money no longer needed) and refunds (e.g. a surplus paid back by the insurance company) can be made outside the month-end. The app lists the bank transfers needed; once they are made, the balances update.
9. **Coming up:** the next payments with how ready each one is: *ready* (the money is there), *on track* (the planned month-end transfers bring it in time) or *short* (even the planned transfers do not cover it).
10. **Expenses board:** per category or account, each expense shows its monthly amount, its next payment and how much of it is there.
11. **Step-by-step setup** of a budget: today's account balances (and adding accounts), all expenses with their next due date, a summary per category with the monthly total, the expected income, then the transfers that start the budget. Once started, the setup is the ground truth: no money should have to be moved afterwards to match it.

## Future extension (not needed now)

- Pasting or importing bank statements. For now all data is entered manually, but the data model must allow an import feature to be added later.
