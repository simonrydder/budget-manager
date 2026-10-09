<#
.SYNOPSIS
    Run Budget Manager in the background: start it when Windows starts and update and restart
    it every night. Run this once from a PowerShell window opened with "Run as administrator".

.EXAMPLE
    .\install-nightly-task.ps1
.EXAMPLE
    .\install-nightly-task.ps1 -At 04:00 -Branch prod -Port 8000
.EXAMPLE
    .\install-nightly-task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$At = "03:30",
    [string]$Branch = "prod",
    [int]$Port = 8000,
    [string]$DataDir = (Join-Path $env:USERPROFILE "BudgetManagerData"),
    [string]$TaskName = "Budget Manager",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TailscaleRule = "$TaskName (Tailscale)"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Open PowerShell with 'Run as administrator' and run this script again."
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName $TaskName -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName $TailscaleRule -ErrorAction SilentlyContinue
    & (Join-Path $PSScriptRoot "run-budget.ps1") -Stop -Port $Port -DataDir $DataDir
    Write-Host "Removed the '$TaskName' task and firewall rules."
    return
}

$script = Join-Path $PSScriptRoot "run-budget.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" " +
    "-Branch $Branch -Port $Port -DataDir `"$DataDir`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments `
    -WorkingDirectory $PSScriptRoot
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At $At),
    (New-ScheduledTaskTrigger -AtStartup)
)
# S4U: runs whether or not you are logged in, without storing your password.
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
# The nightly run stops the running server and starts the updated one ("Stop existing").
$settings.CimInstanceProperties.Item("MultipleInstances").Value = 3

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Principal $principal -Settings $settings -Force | Out-Null

if (-not (Get-NetFirewallRule -DisplayName $TaskName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $TaskName -Direction Inbound -Protocol TCP `
        -LocalPort $Port -Profile Private -Action Allow | Out-Null
}
# Tailscale's network adapter is often classed as public, so this rule covers every profile
# but only Tailscale's addresses (100.64.0.0/10), never the internet.
if (-not (Get-NetFirewallRule -DisplayName $TailscaleRule -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $TailscaleRule -Direction Inbound -Protocol TCP `
        -LocalPort $Port -RemoteAddress "100.64.0.0/10" -Profile Any -Action Allow | Out-Null
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed. Budget Manager starts with Windows and updates from '$Branch' every day at $At."
Write-Host "It is starting now; logs are in $(Join-Path $DataDir 'logs')."
Write-Host "Port $Port is open for private (home) networks and Tailscale (100.64.0.0/10) only."
