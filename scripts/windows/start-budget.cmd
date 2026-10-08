@echo off
rem Double-click to update Budget Manager to the newest version and start it.
rem Extra options are passed on, e.g.:  start-budget.cmd -Branch dev -Port 8080
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-budget.ps1" %*
pause
