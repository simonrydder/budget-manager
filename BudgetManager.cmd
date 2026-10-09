@echo off
rem Budget Manager on this computer. Download this one file and double-click it: the first time
rem it installs what it needs (uv, which brings Python and the app), and every time it gets the
rem newest version and starts it. Only this computer can open the app; other devices cannot
rem connect. Your data stays in %USERPROFILE%\BudgetManager. Close the window to stop the app.
setlocal
title Budget Manager
set "SOURCE=https://github.com/simonrydder/budget-manager/archive/refs/heads/prod.zip"
if not defined BUDGET_DATA_DIR set "BUDGET_DATA_DIR=%USERPROFILE%\BudgetManager"
if not defined BUDGET_PORT set "BUDGET_PORT=8000"
set "BUDGET_ALLOWED_NETWORKS=127.0.0.0/8,::1/128"
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

echo Getting the newest version of Budget Manager...
uv tool install --quiet --reinstall --refresh-package budget-manager "budget-manager @ %SOURCE%"
if errorlevel 1 (
    where budget-manager >nul 2>nul
    if errorlevel 1 (
        echo Could not download Budget Manager. Check the internet connection and try again.
        pause
        exit /b 1
    )
    echo Could not get the newest version, so the version installed earlier is started.
)

rem Open the browser as soon as the app answers.
start "" powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 120; $i++) { try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %BUDGET_PORT%)).Close(); Start-Process '%URL%'; break } catch { Start-Sleep -Seconds 1 } }"

echo.
echo Budget Manager runs on %URL% for this computer only.
echo Keep this window open while you use it. Closing it stops Budget Manager.
echo.
budget-manager serve --host 127.0.0.1 --port %BUDGET_PORT%
echo Budget Manager stopped.
pause
