# Budget Manager

A self-hosted budget manager for the home. Once a month it works out how much to transfer from
the NemKonto (where your income arrives) to each of your accounts, so every expense has its money
when it is due. It keeps the NemKonto between a minimum and a maximum using General Savings,
warns you before money runs short, and forecasts every account and expense into the future.

- **Private:** runs on a computer at home. Only your home network (and, if you want, your own
  devices over Tailscale) can reach it; everything is stored in one SQLite file on that computer.
- **Several budgets and people:** for example one budget for the household and one for a
  company, each shared with the people you choose.
- **Step by step:** a five-step setup to start a budget and a five-step checklist for every
  month-end, with undo.
- **Works on a phone, an iPad or a desktop,** also in a split-screen window.
- **Updates itself** on the computer that runs it.
- Amounts are plain numbers written like `1.234,56`, without a currency.

| Document | For |
|---|---|
| [docs/user-guide.md](docs/user-guide.md) | Using the app, page by page. |
| [docs/requirements.md](docs/requirements.md) | What the app must do. |
| [docs/design.md](docs/design.md) | How it does it: the rules, the data and the updates. |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each version. |

## Three ways to run it

| | For | Login | Other devices | Updates |
|---|---|---|---|---|
| [One file on a Windows PC](#1-one-file-on-a-windows-pc) | Trying it, or one person on one computer | None | No | At every start; asks before a major update |
| [Home server on Windows](#2-home-server-on-windows) | The household's budget, used from phones, tablets and PCs | Yes | Home network and Tailscale | Every 5 minutes, or **Update now** |
| [By hand with uv](#3-by-hand-with-uv-linux-macos-windows) | Linux, macOS, development | Yes | Home network and Tailscale | When you pull |

### 1. One file on a Windows PC

1. Open [BudgetManager.cmd](BudgetManager.cmd) on GitHub and click **Download raw file** (the
   download icon above the file).
2. Double-click the downloaded file. If Windows warns that it comes from the internet, choose
   **Run** (or **More info → Run anyway**).

The first time, it installs [uv](https://docs.astral.sh/uv/), which downloads Python and Budget
Manager into your user folder; no administrator rights are needed. Every start checks GitHub for
a newer version: ordinary updates install by themselves, but a **major update** (a new first
number, like 2.0.0) shows what is new and asks first. Without internet it starts the version it
already has. Then it opens the app in the browser.

The app only answers this computer: other devices cannot connect, and there is no login. Your
data is in `%USERPROFILE%\BudgetManager`. Keep the window open while you use the app; closing it
stops the app. Double-clicking the file again while it runs just opens it in the browser.

### 2. Home server on Windows

`scripts/windows` runs the app from the newest commit of the `prod` branch on a Windows computer
that stays on, and restarts it with every new version.

1. Install [Git](https://git-scm.com/download/win) and [uv](https://docs.astral.sh/uv/):
   `winget install Git.Git astral-sh.uv`.
2. Clone a copy that is only for running the app (the launcher throws away local changes in it):

   ```bat
   git clone https://github.com/simonrydder/budget-manager.git %USERPROFILE%\budget-manager
   ```

3. Open PowerShell with **Run as administrator** and install the background task:

   ```powershell
   cd $env:USERPROFILE\budget-manager\scripts\windows
   powershell -ExecutionPolicy Bypass -File .\install-nightly-task.ps1
   ```

   This adds a scheduled task called *Budget Manager* that starts the app when Windows starts,
   even before anyone logs in, and starts it now. It opens port 8000 in the firewall for private
   networks and, through the rule *Budget Manager (Tailscale)*, for Tailscale's addresses
   (`100.64.0.0/10`) only. Options: `-Port 8080`, `-CheckMinutes 10`, `-Branch <name>`,
   `-DataDir <folder>`, `-At 03:30` to also restart every night. `-Uninstall` removes the task
   and the firewall rules.

   Instead of the task you can double-click `scripts\windows\start-budget.cmd`, which does the
   same in a window that has to stay open.

4. Open `http://<the computer's address>:8000` from a phone or another PC on the home network.
   The first visit creates your login and starts the setup of your first budget.

**Updates.** While it runs, the launcher checks `prod` for a new commit every 5 minutes. When
there is one it backs up the database, updates, installs the dependencies and restarts the app;
that takes a minute or two. **Update now** under **Settings → App version** (from any device) or
`scripts\windows\update-now.cmd` (on the computer) does it right away. If the new version does
not start, the launcher goes back to the version that ran before and skips that commit until a
newer one arrives, so reverting a merge on GitHub is enough to recover. When an update changes the
launcher itself, the new launcher takes over at once.

**Files.** Everything lives in `%USERPROFILE%\BudgetManagerData`, outside the code, so updates
never touch it:

| Path | What |
|---|---|
| `budget.sqlite3` | The database: every budget, person and month-end. |
| `secret_key` | Signs the logins. Keep it with the database. |
| `backups\budget-<date>-<time>.sqlite3` | A copy of the database before every start and update (the 30 newest). |
| `logs\launcher.log` | What the launcher did: updates, versions, restarts. |
| `logs\server.log` | The app's own log. |
| `server.pid`, `update.request`, `update.failed` | Used by the launcher while it runs. |

**Troubleshooting.**

- *No Update now button, or no automatic updates:* the app was started by something other than
  the launcher, or by a launcher from before version 1.4, which keeps running its old code until
  it is restarted. Run `install-nightly-task.ps1` again as administrator (or restart the
  computer) once; from then on the launcher replaces itself when it changes.
- *The app does not start:* look at the end of `logs\launcher.log` and `logs\server.log`.
- *Port 8000 is in use:* choose another with `-Port`.

### 3. By hand with uv (Linux, macOS, Windows)

You need [uv](https://docs.astral.sh/uv/); it brings Python 3.12 if needed.

```sh
git clone https://github.com/simonrydder/budget-manager.git
cd budget-manager
uv sync
uv run budget-manager serve
```

Then open `http://<the computer's address>:8000` from a browser on your network. `serve` applies
database migrations before it starts. To update, `git pull`, `uv sync` and start it again.

To start it with the computer on Linux, create `/etc/systemd/system/budget-manager.service`:

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

## Using it from other devices

On the home network, open `http://<the computer's address>:8000` (for example
`http://192.168.1.10:8000`) on any phone, tablet or PC. Each device logs in once and stays logged
in for a year.

**Away from home, with Tailscale:**

1. Install [Tailscale](https://tailscale.com/download) on the computer that runs the app and on
   your phone, and sign in to both with the same account.
2. On the phone, with Tailscale connected, open `http://<computer name>:8000`, for example
   `http://living-room-pc:8000`. The computer name is the one shown in the Tailscale app.

**Never forward the port on your router.** The app checks every connection itself and answers
`403` to any address outside the allowed networks, but it is not built to face the internet.

## Configuration

`budget-manager serve` reads these options and environment variables:

| Option / variable | Default | Meaning |
|---|---|---|
| `--host` / `BUDGET_HOST` | `0.0.0.0` | Interface to listen on (`127.0.0.1` for this computer only). |
| `--port` / `BUDGET_PORT` | `8000` | Port. |
| `BUDGET_DATA_DIR` | `./data` | Folder for the database and the secret key. |
| `BUDGET_ALLOWED_NETWORKS` | loopback, private ranges and Tailscale (`100.64.0.0/10`; its IPv6 range is in `fc00::/7`) | Comma-separated networks allowed to connect, e.g. `192.168.1.0/24`. Setting it replaces the whole default. |
| `BUDGET_ALLOWED_HOSTS` | `*` | Host names Django accepts; the network check is what keeps the app private. |
| `BUDGET_SECRET_KEY` | a random key saved in the data folder | Signs logins and forms. |
| `BUDGET_LOCAL_ONLY` | off | `1`: no login; requests from this computer are signed in as its person (set by `BudgetManager.cmd`, which also listens on `127.0.0.1` only). |
| `BUDGET_UPDATER` | off | `1`: show **Update now**, which leaves `update.request` in the data folder for the launcher (set by the Windows launcher). |
| `BUDGET_CHECK_MINUTES` | `0` | How often the launcher checks for a new version; shown in Settings (set by the launcher). |
| `BUDGET_COMMIT` | empty | The commit shown next to the version (set by the launcher). |
| `BUDGET_UPDATE_SOURCE` | the `prod` branch on GitHub | Where `budget-manager check-update` looks for the newest version. |
| `BUDGET_DEBUG` | off | `1` during development. |

Other commands: `budget-manager --version`, `budget-manager check-update` (exit code 0: up to
date, 3: an update, 4: a major update, 1: could not check) and `budget-manager manage <command>`
for any Django management command.

## Backups

The whole app is one SQLite file, `budget.sqlite3` in the data folder. The Windows launcher copies
it to `backups` before every start and update. To make a copy by hand while the app runs:

```sh
sqlite3 budget.sqlite3 ".backup 'budget-backup.sqlite3'"
```

To restore, stop the app, put the copy in place of `budget.sqlite3` and start it again. Keep
`secret_key` with it; without it everyone has to log in again.

## Try it with example data

```sh
BUDGET_DATA_DIR=./demo-data uv run budget-manager manage migrate
BUDGET_DATA_DIR=./demo-data uv run budget-manager manage demo
BUDGET_DATA_DIR=./demo-data uv run budget-manager serve
```

This creates a budget called *Demo* with a made-up household and three closed month-ends. Log in
as `demo` / `demo`. `manage demo --name Other` adds a second budget.

## Using the app

The [user guide](docs/user-guide.md) walks through every page. In short:

1. **Once per budget**, follow **Set up**: today's account balances, your expenses, a summary of
   what they cost, your income, and the transfers that start the budget.
2. **At every month-end** (the last day of the month) follow **Month-end**: what was spent
   (fixed payments are filled in), interest, next month's income, the transfers to make, then
   check and close.
3. **Any day**, use **Balance** to move money between General Savings and your expenses, and the
   **Overview**, **Expenses**, **Forecast** and **History** to see where you stand.

## Develop

```sh
uv sync
uv run pytest            # engine unit tests and web tests
uv run ruff check        # lint
uv run ruff format       # format
BUDGET_DEBUG=1 uv run python manage.py runserver
```

The code is in `src/budget_manager`:

| Folder | What |
|---|---|
| `engine/` | The budget rules as plain Python (no Django): schedules, contributions, the month-end close and the forecast. Start here to understand or change a rule. |
| `ledger/` | The Django app: models, services (from the database to the engine and back), views, forms, templates, one CSS and one JavaScript file. |
| `web/` | Settings, URLs and the middleware: the local-network check and the sign-in for this-computer-only mode. |
| `cli.py` | `budget-manager serve`, `check-update` and `manage`. |

`tests/unit` tests the engine and the command line, `tests/integration` the pages. Windows
scripts are in `scripts/windows`; `BudgetManager.cmd` is kept with Windows line endings
(`.gitattributes`).

**Conventions.** Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:`, …). Every change goes through a pull request into `prod`, which is
what the home server and `BudgetManager.cmd` run.

**Versions** follow [Semantic Versioning](https://semver.org/). Every change merged into `prod`
raises the version in `pyproject.toml` (then run `uv lock`) and adds an entry to `CHANGELOG.md`:
the last number for fixes (1.0.0 → 1.0.1), the middle one for new features (1.0.1 → 1.1.0), and
the first one for changes that need something done by hand when updating. `BudgetManager.cmd`
asks before installing such a major update and shows its `CHANGELOG.md` entries, so write them
for the people who will read them there.

**Layout.** Pages are checked at 390, 640, 768, 820, 1024, 1180 and 1440 pixels wide. Columns
follow the width of the page content (CSS container queries), so the same page also works next to
the menu on an iPad and in a split-screen window.
