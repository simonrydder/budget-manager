@echo off
rem Double-click to update Budget Manager to the newest version right away. It does the same as
rem the "Update now" button in the app's Settings: the running launcher (the scheduled task or
rem start-budget.cmd) notices the request within seconds, updates and restarts the app.
rem Another data folder can be given:  update-now.cmd D:\BudgetData
setlocal
set "DATA=%~1"
if "%DATA%"=="" set "DATA=%USERPROFILE%\BudgetManagerData"
if exist "%DATA%\server.pid" (
    echo %DATE% %TIME% update-now.cmd> "%DATA%\update.request"
    echo Update requested. Budget Manager restarts with the newest version in a minute or two.
) else (
    echo Budget Manager is not running, so it is started with the newest version instead.
    call "%~dp0start-budget.cmd" -DataDir "%DATA%"
)
pause
