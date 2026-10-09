<#
.SYNOPSIS
    Update Budget Manager to the newest version of a branch and run it.

.DESCRIPTION
    1. Stops a server started earlier by this script.
    2. Backs up the database (keeps the newest -KeepBackups copies).
    3. Updates the code to the newest commit on -Branch (local changes in this clone are
       discarded, so use a clone that is only for running the app).
    4. Installs the matching dependencies with uv and starts the server.
    5. If the new version does not start, goes back to the version that ran before.

    The server keeps running until this window is closed or the scheduled task is stopped.
    Your data lives in -DataDir, outside the code, so updates never touch it.

.EXAMPLE
    .\run-budget.ps1
.EXAMPLE
    .\run-budget.ps1 -Branch dev -Port 8080
.EXAMPLE
    .\run-budget.ps1 -NoUpdate
#>
[CmdletBinding()]
param(
    [string]$Branch = "prod",
    [int]$Port = 8000,
    [string]$DataDir = (Join-Path $env:USERPROFILE "BudgetManagerData"),
    [int]$KeepBackups = 30,
    [int]$StartTimeoutSeconds = 120,
    [switch]$NoUpdate,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $DataDir "logs"
$BackupDir = Join-Path $DataDir "backups"
$PidFile = Join-Path $DataDir "server.pid"
$Database = Join-Path $DataDir "budget.sqlite3"
New-Item -ItemType Directory -Force -Path $DataDir, $LogDir, $BackupDir | Out-Null
$LauncherLog = Join-Path $LogDir "launcher.log"

function Write-Log([string]$Message) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $Message
    Write-Host $line
    Add-Content -Path $LauncherLog -Value $line
}

function Invoke-Native([string]$File, [string[]]$Arguments) {
    # Runs a program and throws if it fails (PowerShell does not do that for programs).
    # Programs like uv write normal progress to stderr. With "Stop", Windows PowerShell 5.1
    # turns each such line into a terminating error, so only the exit code decides here.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $File @Arguments 2>&1 | ForEach-Object {
            # Lines from stderr arrive as ErrorRecord objects; "$_" is their plain text.
            Add-Content -Path $LauncherLog -Value "    $("$_")"
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "$File $($Arguments -join ' ') failed with exit code $exitCode"
    }
}

function Find-Program([string]$Name, [string[]]$Fallbacks) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in $Fallbacks) { if (Test-Path $path) { return $path } }
    throw "$Name was not found. Install it first (see README.md)."
}

function Stop-Server {
    if (Test-Path $PidFile) {
        $oldPid = (Get-Content $PidFile -Raw).Trim()
        if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
            Write-Log "Stopping the running server (process $oldPid)."
            & taskkill.exe /PID $oldPid /T /F | Out-Null
            Start-Sleep -Seconds 2
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Test-Port {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-Server {
    $serverLog = Join-Path $LogDir "server.log"
    if ((Test-Path $serverLog) -and (Get-Item $serverLog).Length -gt 5MB) {
        Move-Item $serverLog (Join-Path $LogDir "server.previous.log") -Force
    }
    $env:BUDGET_DATA_DIR = $DataDir
    $command = "`"$Uv`" run --no-dev budget-manager serve --host 0.0.0.0 --port $Port >> `"$serverLog`" 2>&1"
    # cmd.exe /c strips the first and the last quote of the command line, so the whole
    # command gets one extra pair of quotes around it.
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$command`"" `
        -WorkingDirectory $RepoDir -NoNewWindow -PassThru
    Set-Content -Path $PidFile -Value $process.Id
    $deadline = (Get-Date).AddSeconds($StartTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) { return $null }
        if (Test-Port) { return $process }
        Start-Sleep -Seconds 2
    }
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    return $null
}

function Update-Code([string]$Target) {
    Invoke-Native $Git @("-C", $RepoDir, "checkout", "--quiet", "--force", "-B", $Branch, $Target)
    Invoke-Native $Git @("-C", $RepoDir, "reset", "--quiet", "--hard", $Target)
    Invoke-Native $Uv @("sync", "--locked", "--no-dev", "--directory", $RepoDir)
}

$Uv = Find-Program "uv" @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")
$Git = Find-Program "git" @("$env:ProgramFiles\Git\cmd\git.exe")

Stop-Server
if (Test-Port) {
    throw "Port $Port is already in use by another program. Choose another with -Port."
}
if ($Stop) {
    Write-Log "Stopped."
    return
}

if (Test-Path $Database) {
    $backup = Join-Path $BackupDir ("budget-{0:yyyy-MM-dd-HHmm}.sqlite3" -f (Get-Date))
    Copy-Item $Database $backup -Force
    Write-Log "Backed up the database to $backup"
    Get-ChildItem $BackupDir -Filter "budget-*.sqlite3" | Sort-Object Name -Descending |
        Select-Object -Skip $KeepBackups | Remove-Item -Force
}

$previous = (& $Git -C $RepoDir rev-parse HEAD).Trim()
$updated = $false
if (-not $NoUpdate) {
    try {
        Write-Log "Fetching the newest version of '$Branch'."
        Invoke-Native $Git @("-C", $RepoDir, "fetch", "--quiet", "origin", $Branch)
        Update-Code "origin/$Branch"
        $current = (& $Git -C $RepoDir rev-parse HEAD).Trim()
        $updated = $current -ne $previous
        if ($updated) {
            Write-Log "Updated from $($previous.Substring(0, 7)) to $($current.Substring(0, 7))."
        } else {
            Write-Log "Already up to date ($($current.Substring(0, 7)))."
        }
    } catch {
        Write-Log "Could not update ($($_.Exception.Message)). Starting the current version."
        try { Update-Code $previous } catch { Write-Log "Restoring the previous version failed too." }
        $updated = $false
    }
} else {
    Invoke-Native $Uv @("sync", "--locked", "--no-dev", "--directory", $RepoDir)
}

Write-Log "Starting Budget Manager on port $Port (data in $DataDir)."
$server = Start-Server
if (-not $server -and $updated) {
    Write-Log "The new version did not start. Going back to $($previous.Substring(0, 7))."
    Write-Log "If the database was changed by the new version, restore it from $BackupDir."
    Update-Code $previous
    $server = Start-Server
}
if (-not $server) {
    Write-Log "Budget Manager did not start. See $(Join-Path $LogDir 'server.log')."
    exit 1
}

$addresses = @("http://localhost:$Port")
try {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        ForEach-Object { "http://$($_.IPAddress):$Port" }
} catch { }
Write-Log "Running. Open $($addresses -join ' or ') from a browser on your network."
Write-Host "Keep this window open. Closing it stops Budget Manager."
Wait-Process -Id $server.Id -ErrorAction SilentlyContinue
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Log "Budget Manager stopped."
