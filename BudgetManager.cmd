@echo off
rem Budget Manager on this computer. Download this one file and double-click it: the first time
rem it installs what it needs (uv, which brings Python and the app), and every time it checks for
rem a newer version and starts the app. Updates install by themselves, except a major update
rem (a new first number, like 2.0.0), which may change how things work: that one asks first.
rem Only this computer can open the app, so there is no login; other devices cannot connect.
rem Your data stays in %USERPROFILE%\BudgetManager. Close the window to stop the app.
setlocal
title Budget Manager
set "SOURCE=https://github.com/simonrydder/budget-manager/archive/refs/heads/prod.zip"
if not defined BUDGET_DATA_DIR set "BUDGET_DATA_DIR=%USERPROFILE%\BudgetManager"
if not defined BUDGET_PORT set "BUDGET_PORT=8000"
set "BUDGET_ALLOWED_NETWORKS=127.0.0.0/8,::1/128"
set "BUDGET_LOCAL_ONLY=1"
set "URL=http://127.0.0.1:%BUDGET_PORT%/"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

rem Started twice? Then open the one that is running.
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %BUDGET_PORT%)).Close(); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
    echo Budget Manager is already running. Opening %URL%
    start "" "%URL%"
    exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
    echo Installing uv, which downloads Python and Budget Manager. This is only needed once.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    where uv >nul 2>nul
    if errorlevel 1 (
        echo Could not install uv. Check the internet connection and try again.
        pause
        exit /b 1
    )
)

where budget-manager >nul 2>nul
if errorlevel 1 goto install
rem Exit code 0: up to date, 3: an update, 4: a major update. Anything else (no internet, or a
rem version too old to check) tries to install the newest.
budget-manager check-update
if errorlevel 5 goto install
if errorlevel 4 goto ask
if errorlevel 1 goto install
goto run

:ask
choice /C YN /M "Install this major update now"
if errorlevel 2 goto run

:install
echo Getting the newest version of Budget Manager...
uv tool install --quiet --reinstall --refresh-package budget-manager "budget-manager @ %SOURCE%"
if not errorlevel 1 goto run
where budget-manager >nul 2>nul
if errorlevel 1 (
    echo Could not download Budget Manager. Check the internet connection and try again.
    pause
    exit /b 1
)
echo Could not get the newest version, so the version installed earlier is started.

:run
rem Open the browser as soon as the app answers.
start "" powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 120; $i++) { try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %BUDGET_PORT%)).Close(); Start-Process '%URL%'; break } catch { Start-Sleep -Seconds 1 } }"

echo.
echo Budget Manager runs on %URL% for this computer only.
echo Keep this window open while you use it. Closing it stops Budget Manager.
echo.
budget-manager serve --host 127.0.0.1 --port %BUDGET_PORT%
echo Budget Manager stopped.
pause
