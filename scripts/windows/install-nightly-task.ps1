<#
.SYNOPSIS
    Run Budget Manager in the background: start it when Windows starts. While it runs it checks
    for a new version every -CheckMinutes minutes and restarts with it. Run this once from a
    PowerShell window opened with "Run as administrator".

.EXAMPLE
    .\install-nightly-task.ps1
.EXAMPLE
    .\install-nightly-task.ps1 -Branch prod -Port 8000 -CheckMinutes 10
.EXAMPLE
    .\install-nightly-task.ps1 -At 03:30     # also restart every night at 03:30
.EXAMPLE
    .\install-nightly-task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$At = "",
    [string]$Branch = "prod",
    [int]$CheckMinutes = 5,
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
    "-Branch $Branch -Port $Port -CheckMinutes $CheckMinutes -DataDir `"$DataDir`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments `
    -WorkingDirectory $PSScriptRoot
$triggers = @(New-ScheduledTaskTrigger -AtStartup)
if ($At) {
    $triggers += New-ScheduledTaskTrigger -Daily -At $At
}
# S4U: runs whether or not you are logged in, without storing your password.
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
# Starting the task again stops the running launcher and starts a new one ("Stop existing").
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
$schedule = if ($At) { " and restarts every day at $At" } else { "" }
Write-Host ("Installed. Budget Manager starts with Windows$schedule, and checks '$Branch' for a " +
    "new version every $CheckMinutes minutes.")
Write-Host "It is starting now; logs are in $(Join-Path $DataDir 'logs')."
Write-Host "Port $Port is open for private (home) networks and Tailscale (100.64.0.0/10) only."
