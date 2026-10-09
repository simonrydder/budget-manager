# Budget Manager – User guide

This guide follows the app page by page, in the order you meet them. It describes version 1.6
(the version is shown under **Settings → App version** and at the bottom of the menu). How to
install and run the app is in the [README](../README.md); the rules behind the numbers are in
[design.md](design.md).

- [The idea in one minute](#the-idea-in-one-minute)
- [Words used in the app](#words-used-in-the-app)
- [Setting up a budget](#setting-up-a-budget)
- [The overview](#the-overview)
- [The month-end](#the-month-end)
- [Balance: moving money between month-ends](#balance-moving-money-between-month-ends)
- [Expenses](#expenses)
- [Income](#income)
- [Accounts](#accounts)
- [Forecast and History](#forecast-and-history)
- [Settings, Budgets and People](#settings-budgets-and-people)
- [Updates](#updates)
- [Questions](#questions)

## The idea in one minute

Your income arrives on one account, the **NemKonto**. Once a month, on the last day of the month,
you move money from the NemKonto to the accounts that pay your expenses: rent from the Budget
account, groceries from the Food account, savings goals on the Savings account, and so on. Every
expense saves a little each month, so the money is there when the payment is due: a yearly
insurance of 6.000 saves 500 a month.

After those transfers the NemKonto should keep between a **minimum** and a **maximum**, for
example 2.000–5.000. That is the money for everyday spending with its card until the next
month-end. Anything above the maximum goes to **General Savings**; anything missing below the
minimum comes from it.

The app works out every transfer, keeps track of what each expense has, warns you before money
runs short, and shows where every account will be in the months ahead.

## Words used in the app

| Word | Meaning |
|---|---|
| **NemKonto** | The account your income arrives on and the transfers go out from. It is also your everyday account: what it keeps after a month-end is the money for everyday spending. Expenses cannot use it. |
| **General Savings** | Not a separate bank account: the part of your savings account that is not set aside for an expense or savings goal. It takes what is left over each month and covers what is missing. |
| **Expense** | Something money is set aside for: a bill, a subscription, a running budget like food, or a savings goal. Each expense belongs to one account and, if you like, one category. |
| **Fixed** | An expense that costs the same each time it is due (rent, insurance, subscriptions). If one costs more, General Savings covers the difference and the expected amount is raised. |
| **Variable** | A bill paid on its due date whose amount varies (power, heating, water). |
| **Running** | Money spent bit by bit through the month (food, fuel, parking). It is monthly, available from the 1st, and has no due date. |
| **One-off goal** | An expense paid once, on a date in the future, for example a new car or a stay abroad. The app spreads it over the months until then. |
| **Month-end** | The last day of the month, when the transfers are made. The month-end on 31 October pays for November: the income that arrives at the end of October funds November's payments. |
| **Contribution** | What an expense gets at a month-end. It stays the same every month, so the transfers can be standing orders in the bank. |

Amounts are written like `1.234,56`, without a currency. You can type `1234,56`, `1.234,56` or
`1234`.

## Setting up a budget

A new budget starts with **Set up** in the menu: five steps, each opening once the one before it
is done. Until the first month-end you can go back and change any step and start again.

### Step 1 – Accounts

Type today's balance of every account, exactly as the bank shows it. The budget starts with four
accounts: NemKonto, Budget, Food and Savings. Rename them, remove the ones you do not use, or add
your own (for example a separate account for the car).

Below the accounts you choose how much the NemKonto should **keep at least** and **keep at most**
after each month-end, and roughly what you **spend from it in a month** with its card. That last
amount is only used for the forecast until three month-ends have recorded what was really spent.

### Step 2 – Expenses

Add every expense, one at a time:

- **Name**, **type** (fixed, variable or running), **amount**, **account** and **category**.
- **Frequency** and **next due date**: monthly, quarterly, yearly, every few years, or *One-off*
  for a savings goal (then the due date is when the money must be ready). A running budget needs
  neither: it is monthly.
- **The next payment is a different amount**: open this when the next payment is not the usual
  amount, for example a monthly subscription whose first payment covers two months. Later
  payments are the usual amount again.

The next expense starts with the same account, category and frequency, so a series of similar
expenses goes quickly. On the same page you can add, rename and remove **categories**. The list
below groups the expenses per category with what each costs a month; every group can be folded
away (the app remembers this in your browser).

Everyday spending from the NemKonto is *not* an expense: it comes out of what the NemKonto keeps
(step 1).

### Step 3 – Summary

What the expenses cost a month, per category and per account, and in total. A yearly payment
counts as a twelfth, a one-off goal as its amount spread over the months until it is due.

### Step 4 – Income

Add what you expect to arrive on the NemKonto: salaries, child benefit and so on, with the first
month each one is for and how often it comes. The page compares the income with the expenses and
everyday spending, so you see straight away whether the budget holds.

### Step 5 – Transfers

This is where the budget starts. The page shows:

1. **October so far** (the current month): bills follow their due dates. A bill due before today
   counts as paid; one due later this month is still on the account. For a running budget like
   food, type what has been spent so far this month, or what is left of it, then press
   **Recalculate**.
2. **Even out the accounts today**: every expense gets exactly what keeps its monthly amount the
   same from the first month-end on. A yearly 1.200 due in two months needs 1.000 now, a payment
   due this month all of it, and a savings goal what is already saved for it. The table compares
   that with what is in the bank and lists the bank transfers to or from Savings that make the
   accounts match. Whatever is left over is your General Savings.
3. **Your first month-end**: what will be sent to each account at the end of this month, next to
   what it usually needs a month.

Press **Start the budget**, then make the listed bank transfers. The overview keeps showing them
until you press **Done**. From then on the setup is the ground truth: nothing else should need
moving to match it.

## The overview

The **Overview** is the first page of a running budget:

- **Next month-end**: the date, how many days are left, and an estimate of the income, the total
  transfers, what goes to (or comes from) General Savings and where the NemKonto ends. Press
  **Start** (or **Continue**) to do the month-end.
- **Balances**: the NemKonto after the last month-end, General Savings, what is set aside for
  expenses, and the last month-end.
- **Accounts**: every account with its balance and the expenses with the most money on it.
- **Next 12 months**: a small chart per account and for General Savings, with the lowest point.
  A red dashed line marks zero; it only appears when the balance goes below it.
- **Needs attention**: warnings, for example when the expenses need more than the income, when
  General Savings cannot cover a shortfall, or when a variable expense keeps going below zero.
- **Coming up**: the payments in the next 60 days (the first ten, the rest behind *Show more*),
  each marked:
  - **ready**: the money is on the expense now;
  - **on track**: the month-end transfers before the due date bring the rest;
  - **short X**: even the planned transfers leave X missing, for example after money was taken
    from that expense. A payment before the next month-end only counts what is there now.

## The month-end

On the last day of the month open **Month-end** in the menu and follow the five steps. You can
start earlier, enter what you know and come back; nothing is final until you close it.

1. **Spending** (for example *October spending*): what each expense actually cost this month.
   - **Fixed payments** that were due are filled in with their amount. Change one if it cost
     something else.
   - **Variable bills** and **running budgets** are empty: type the real amount. For a running
     budget you can instead type **what is left**, and the app works out what was spent.
   - **Spent from the NemKonto**: what you spent with the NemKonto's card. Or type its balance
     before the income arrived, and the app works it out.
   - Expenses that were not due this month are folded away under *N more, not due*. Open it if
     one of them had a payment anyway.
2. **Interest**: interest each account received (or paid, as a negative amount). It counts as if
   it arrived on the NemKonto, so the next transfer to that account is smaller.
3. **Income** (for example *November income*): what arrived on the NemKonto for next month.
4. **Transfers**: one transfer per account, from the NemKonto (or back to it). Each has a
   **Copy** button for the amount; tick it off when you have made it in the bank. The side panel
   shows how the NemKonto ends up between its minimum and maximum and what that does to General
   Savings. If the NemKonto would end below zero, the page asks which expenses or savings goals to
   take the missing money from.
5. **Check & close**: optionally type what the bank shows for each account to compare, then
   **Close the month-end**.

**Going back.** Every step has a **Back** button, and the step bar at the top lets you jump to any
step you have reached. **Undo step N** (at the top) marks the last finished step as not done and
takes you back to it; what you entered is kept. Right after closing, the next month-end offers
**Reopen the month-end on …**, which undoes the close. Older month-ends are under
**Earlier month-ends**; only the latest one can be reopened.

## Balance: moving money between month-ends

Sometimes money has to move between General Savings and an expense before the next month-end:

| Move | Where you start it |
|---|---|
| **Fill** a new expense with what it would already have saved | *Fill from General Savings* when adding the expense (once the budget is running). |
| **Top up** an expense, for example one below zero | *Top up from General Savings* on the expense's edit page. |
| **Return** money an expense no longer needs | *Move money to General Savings* on the expense's page. An ended expense returns what is left by itself. |
| **Refund**, for example a surplus paid back by the insurance company | *Add a refund* on the Balance page. |

Each move waits on the **Balance** page, which nets them into the bank transfers to make (to or
from the account that holds General Savings). Make them in the bank, then press **Transfers
made**; the balances update at once. A move can be cancelled while it waits and undone until the
next month-end. A month-end cannot be closed while moves are waiting.

## Expenses

The **Expenses** page shows every active expense as a card, grouped **by category** or **by
account**. Each group is a section with its monthly cost and can be folded away (*Collapse all*
folds them all). Drag a card to another group to move it, or within a group to change the order.

Each card shows:

- what the expense takes **a month**;
- the **next payment** and when (*in 23 days*), or for a running budget *spent through October,
  refilled 31 Oct*, or for a goal *Goal 60.000 by Aug 2029*;
- a **bar** for how much of the next payment is there, and **on track**, **short X** or
  **below zero** compared with the plan.

Click a card to open the expense: its balance, next contribution and due dates, the plan for the
next 12 month-ends, its history, and the buttons to **Edit**, **End** (no payments after a date;
what is left goes back to General Savings) or move money to General Savings. An expense without
history can be deleted from there too.

**Categories** (button on the Expenses page) lists, renames, orders and removes categories.
Removing a category keeps its expenses; they become uncategorised.

## Income

**Income** lists the expected income: amount, how often it comes, the first month it is for and,
optionally, the last month. The month-end asks for the actual amount each time; the plan and the
forecast use the expected amount until then.

## Accounts

**Accounts** shows every account's balance after the last month-end and the spending entered
since, with its expenses folded into one line when there are many. Type what the bank shows in
**In the bank** to see the difference at once. If the NemKonto or General Savings differ for a
reason the app cannot know (a bank fee, a forgotten purchase), use **Correct the NemKonto
balance** or **Correct General Savings**. Accounts can be added, renamed or removed (an account
with expenses or history cannot be removed); exactly one account holds General Savings.

## Forecast and History

**Forecast** runs the month-ends forward (24 months by default, see Settings) with the expected
amounts. The slider picks a month; the page shows every account and expense at the end of it, the
NemKonto and General Savings flow, and the warnings ahead. Everyday spending from the NemKonto
counts as the average of the last six month-ends (or the amount from the settings until there are
three).

**History** shows what was actually spent, per month and year, by category, expense or account,
with the average per month and what the plan expected in the same months.

## Settings, Budgets and People

**Settings** belong to the budget you are in: its name, the people who can use it, the NemKonto
minimum and maximum, the rough everyday spending, the forecast length, the starting point, and
copying or deleting the budget. **App version** shows the running version and, when the app runs
through the Windows launcher, the **Update now** button.

**Budgets** lists your budgets. A new budget starts with the usual accounts and categories and
the setup. **Copy** makes either a fresh copy (accounts, categories, current expenses and income,
then set it up from scratch) or a full copy with all month-ends and history, for example to try a
change without touching the real budget. Each budget has its own address (`/b/<number>/…`), so
two tabs can show two budgets side by side.

**People** lists everyone who can log in. Add a person with a password and the budgets they can
use; change passwords or remove people here. Everyone sees and changes the same data in the
budgets they share. On the home network each device stays logged in for a year.

With the one-file start (`BudgetManager.cmd`) the app only serves the computer it runs on, so
there is no login, and Log out and People are hidden.

## Updates

- **Home server (Windows launcher):** the app checks for a new version every 5 minutes and
  restarts with it by itself; a backup of the database is made first. **Update now** under
  Settings → App version does it right away, from any device. If a new version does not start,
  the previous one keeps running.
- **One-file start:** every start checks for a new version. Ordinary updates install by
  themselves; a **major update** (a new first number, like 2.0.0) shows what is new and asks
  first.

What changed in each version is in [CHANGELOG.md](../CHANGELOG.md).

## Questions

**An expense is below zero. What do I do?**
A fixed expense is topped up from General Savings at the next month-end by itself. A variable or
running expense is not: if it keeps happening, raise its amount, or top it up now on its edit
page.

**The NemKonto would end below its minimum.**
General Savings covers it. If General Savings cannot, the month-end warns you and the NemKonto ends
below the minimum; if it would end below zero, you choose which expenses to take the money from.

**Can I change an expense's amount?**
Yes, any time. The contributions until the next payment change so the money is there by the due
date (a yearly 500 that turns out to be 600 saves more for the remaining months). Past month-ends
keep their numbers.

**I made a mistake in a month-end.**
Use **Undo step** or **Back** while it is open. Once closed, open the next month-end and press
**Reopen the month-end on …** (or open it under History / Earlier month-ends), fix it and close it
again.

**There is no Update now button.**
The app was not started by the Windows launcher, or by a launcher from before version 1.1. On the
computer that runs it, start it again with `start-budget.cmd`, or run `install-nightly-task.ps1`
again as administrator.
