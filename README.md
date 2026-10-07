# Budget Manager

A self-hosted budget manager for the home network. It works out how much to transfer from the
NemKonto to each account at the end of every month, keeps the NemKonto between a minimum and a
maximum using General Savings, and forecasts every account and expense into the future.

- Runs on one machine at home; you use it from any browser on the same network.
- Refuses connections from outside the local network.
- Everything is stored in a single SQLite file on that machine.
- Several people can log in; everyone sees and edits the same budget.
- Amounts are plain numbers written like `1.234,56`.

The rules it follows are described in [docs/requirements.md](docs/requirements.md) and
[docs/design.md](docs/design.md).

## Run it

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer.

```sh
git clone https://github.com/simonrydder/budget-manager.git
cd budget-manager
uv sync
uv run budget-manager serve
```

Then open `http://<the machine's address>:8000` from a browser on your network, for example
`http://192.168.1.10:8000`. The first visit asks you to create a login; add more people under
**People** afterwards.

`serve` applies database migrations before it starts. Options:

| Option / variable | Default | Meaning |
|---|---|---|
| `--host` / `BUDGET_HOST` | `0.0.0.0` | Interface to listen on. |
| `--port` / `BUDGET_PORT` | `8000` | Port. |
| `BUDGET_DATA_DIR` | `./data` | Where the database (`budget.sqlite3`) and the secret key live. |
| `BUDGET_ALLOWED_NETWORKS` | loopback and private ranges | Comma-separated networks allowed to connect, e.g. `192.168.1.0/24`. |
| `BUDGET_ALLOWED_HOSTS` | `*` | Host names Django accepts. |

Do not forward the port on your router. The app also checks every connection itself and answers
`403` to any address outside the allowed networks.

### Start it automatically (Linux)

Create `/etc/systemd/system/budget-manager.service`:

```ini
[Unit]
Description=Budget Manager
After=network-online.target

[Service]
User=budget
WorkingDirectory=/home/budget/budget-manager
Environment=BUDGET_DATA_DIR=/home/budget/budget-data
ExecStart=/home/budget/.local/bin/uv run budget-manager serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then `sudo systemctl enable --now budget-manager`.

### Run it on Windows (updated every night)

`scripts/windows` starts the app on Windows from the newest commit of the `prod` branch.

1. Install [Git](https://git-scm.com/download/win) and [uv](https://docs.astral.sh/uv/)
   (`winget install Git.Git astral-sh.uv`).
2. Clone a copy that is only for running the app. The script throws away local changes in it.

   ```bat
   git clone https://github.com/simonrydder/budget-manager.git %USERPROFILE%\budget-manager
   ```

3. Double-click `scripts\windows\start-budget.cmd`. It stops a running copy, backs up the
   database, updates to the newest `prod`, installs the dependencies and starts the server on
   port 8000. Keep the window open. If the new version does not start, it goes back to the
   version that ran before.
4. To run it in the background instead, open PowerShell with **Run as administrator** and run:

   ```powershell
   cd $env:USERPROFILE\budget-manager\scripts\windows
   powershell -ExecutionPolicy Bypass -File .\install-nightly-task.ps1
   ```

   This adds a scheduled task called *Budget Manager* that starts the app when Windows starts and
   updates and restarts it every night at 03:30, and opens the port in the firewall for private
   networks. Options: `-At 04:00`, `-Port 8080`, `-Branch <name>`. Remove it again with
   `-Uninstall`.

The data lives in `%USERPROFILE%\BudgetManagerData` (`-DataDir` to change it), outside the
code, so updates never touch it. Every start keeps a copy of the database in `backups` (the 30
newest) and the server log in `logs\server.log`.

### Back up

The whole budget is one file. Copy it safely while the app runs with:

```sh
sqlite3 data/budget.sqlite3 ".backup 'budget-backup.sqlite3'"
```

## Try it with example data

```sh
BUDGET_DATA_DIR=./demo-data uv run budget-manager manage migrate
BUDGET_DATA_DIR=./demo-data uv run budget-manager manage demo
BUDGET_DATA_DIR=./demo-data uv run budget-manager serve
```

This creates a made-up household with three closed month-ends. Log in as `demo` / `demo`.

## How you use it

1. **Once:** check the accounts (NemKonto, Budget, Food and Savings to begin with), set the
   NemKonto minimum and maximum and the starting balances under **Settings**, then add your
   expenses and income.
2. **Every month-end** (the last day of the month) follow the checklist under **Month-end**:
   1. enter what was actually spent on each expense during the month,
   2. enter the interest each account received,
   3. enter the income that arrived for next month,
   4. make the transfers it lists and tick them off,
   5. optionally compare the balances with the bank, then close the month-end.

The **Overview** shows balances, warnings, upcoming payments and the next 12 months. **Forecast**
goes further ahead, **History** shows actual spending per year.

## Develop

```sh
uv sync
uv run pytest            # engine unit tests and web tests
uv run ruff check        # lint
uv run ruff format       # format
BUDGET_DEBUG=1 uv run python manage.py runserver
```

The code is in `src/budget_manager`:

- `engine/`: the budget rules as plain Python (no Django): schedules, contributions, the
  month-end close and the forecast. Start here to understand or change a rule.
- `ledger/`: the Django app: models, views, templates, static files.
- `web/`: Django settings, URLs and the local-network check.

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, …).
