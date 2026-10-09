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

    While it runs, the script checks every -CheckMinutes minutes whether -Branch has a new
    commit, and watches for an update request: the "Update now" button in the app's Settings,
    or update-now.cmd, leaves the file update.request in -DataDir. Either way it then does all
    of the above again, so the newest version runs within a minute or two. A version that did
    not start is skipped by the checks until a newer commit (for example a revert) arrives.

.EXAMPLE
    .\run-budget.ps1
.EXAMPLE
    .\run-budget.ps1 -Branch dev -Port 8080
.EXAMPLE
    .\run-budget.ps1 -NoUpdate
.EXAMPLE
    .\run-budget.ps1 -CheckMinutes 0     # only update when started or asked to
#>
[CmdletBinding()]
param(
    [string]$Branch = "prod",
    [int]$Port = 8000,
    [string]$DataDir = (Join-Path $env:USERPROFILE "BudgetManagerData"),
    [int]$KeepBackups = 30,
    [int]$StartTimeoutSeconds = 120,
    [int]$CheckMinutes = 5,
    [switch]$NoUpdate,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $DataDir "logs"
$BackupDir = Join-Path $DataDir "backups"
$PidFile = Join-Path $DataDir "server.pid"
$RequestFile = Join-Path $DataDir "update.request"
$FailedFile = Join-Path $DataDir "update.failed"  # a commit that did not start
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
        $process = $null
        if ($oldPid -match '^\d+$') {
            $process = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        }
        # After a reboot the stored number can belong to another program. Only the cmd.exe
        # this script started is stopped: it was running before server.pid was written.
        $written = (Get-Item $PidFile).LastWriteTime
        $started = $null
        if ($process) {
            try { $started = $process.StartTime } catch { }  # access can be denied
        }
        $ours = $process -and $process.ProcessName -eq "cmd" -and
            $started -and $started -le $written
        if ($ours) {
            Write-Log "Stopping the running server (process $oldPid)."
            & taskkill.exe /PID $oldPid /T /F | Out-Null
            Start-Sleep -Seconds 2
        } elseif ($process) {
            Write-Log "Process $oldPid is not the server started earlier, so it is left running."
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
    # Tells the app to offer "Update now" (this script watches for the request) and which
    # commit runs; the app knows its own version number.
    $env:BUDGET_UPDATER = "1"
    $env:BUDGET_CHECK_MINUTES = if ($NoUpdate) { "0" } else { "$CheckMinutes" }
    $env:BUDGET_COMMIT = ""
    try {
        $env:BUDGET_COMMIT = (& $Git -C $RepoDir log -1 "--format=%h, %cd" --date=short).Trim()
    } catch { }
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

function Get-Version {
    # The version number in pyproject.toml, with the commit: "1.2.0 (a1b2c3d)".
    $commit = (& $Git -C $RepoDir rev-parse --short HEAD).Trim()
    $line = Select-String -Path (Join-Path $RepoDir "pyproject.toml") -Pattern '^version = "(.+)"' |
        Select-Object -First 1
    if ($line) { return "$($line.Matches[0].Groups[1].Value) ($commit)" }
    return $commit
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
# This start updates anyway (unless -NoUpdate), so an earlier request is done with.
Remove-Item $RequestFile -Force -ErrorAction SilentlyContinue

if (Test-Path $Database) {
    $backup = Join-Path $BackupDir ("budget-{0:yyyy-MM-dd-HHmmss}.sqlite3" -f (Get-Date))
    Copy-Item $Database $backup -Force
    Write-Log "Backed up the database to $backup"
    Get-ChildItem $BackupDir -Filter "budget-*.sqlite3" | Sort-Object Name -Descending |
        Select-Object -Skip $KeepBackups | Remove-Item -Force
}

$previous = (& $Git -C $RepoDir rev-parse HEAD).Trim()
$previousVersion = Get-Version
$updated = $false
$target = $null
if (-not $NoUpdate) {
    try {
        Write-Log "Fetching the newest version of '$Branch'."
        Invoke-Native $Git @("-C", $RepoDir, "fetch", "--quiet", "origin", $Branch)
        $target = (& $Git -C $RepoDir rev-parse "origin/$Branch").Trim()
        Update-Code "origin/$Branch"
        $current = (& $Git -C $RepoDir rev-parse HEAD).Trim()
        $updated = $current -ne $previous
        if ($updated) {
            Write-Log "Updated from $previousVersion to $(Get-Version)."
        } else {
            Write-Log "Already up to date: $(Get-Version)."
        }
    } catch {
        Write-Log "Could not update ($($_.Exception.Message)). Starting the current version."
        if ($target -and $target -ne $previous) {
            Set-Content -Path $FailedFile -Value $target  # do not try it again every few minutes
        }
        try { Update-Code $previous } catch { Write-Log "Restoring the previous version failed too." }
        $updated = $false
    }
} else {
    Invoke-Native $Uv @("sync", "--locked", "--no-dev", "--directory", $RepoDir)
}

Write-Log "Starting Budget Manager $(Get-Version) on port $Port (data in $DataDir)."
$server = Start-Server
if (-not $server -and $updated) {
    Write-Log "The new version did not start. Going back to $previousVersion."
    Write-Log "If the database was changed by the new version, restore it from $BackupDir."
    Write-Log "It is skipped until a newer commit arrives on '$Branch' (for example a revert)."
    Set-Content -Path $FailedFile -Value (& $Git -C $RepoDir rev-parse HEAD).Trim()
    Update-Code $previous
    $updated = $false  # the previous version runs again, so the marker above stays
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
if ($updated) {
    Remove-Item $FailedFile -Force -ErrorAction SilentlyContinue  # a newer version runs fine
}
Write-Host "Keep this window open. Closing it stops Budget Manager."

function Find-NewVersion {
    # The newest commit on the branch if it is not the one running and did not fail before.
    Invoke-Native $Git @("-C", $RepoDir, "fetch", "--quiet", "origin", $Branch)
    $remote = (& $Git -C $RepoDir rev-parse "origin/$Branch").Trim()
    $running = (& $Git -C $RepoDir rev-parse HEAD).Trim()
    $failed = if (Test-Path $FailedFile) { "$(Get-Content $FailedFile -Raw)".Trim() } else { "" }
    if ($remote -ne $running -and $remote -ne $failed) { return $remote }
    return $null
}

$checking = -not $NoUpdate -and $CheckMinutes -gt 0
$nextCheck = (Get-Date).AddMinutes($CheckMinutes)
$checkFailed = $false
$reason = $null
while (-not $server.HasExited) {
    if (Test-Path $RequestFile) {
        $request = "$(Get-Content $RequestFile -Raw -ErrorAction SilentlyContinue)".Trim()
        Remove-Item $RequestFile -Force -ErrorAction SilentlyContinue
        $reason = "Update requested ($request)"
        break
    }
    if ($checking -and (Get-Date) -ge $nextCheck) {
        $nextCheck = (Get-Date).AddMinutes($CheckMinutes)
        try {
            $newer = Find-NewVersion
            if ($checkFailed) { Write-Log "Checking for new versions works again." }
            $checkFailed = $false
            if ($newer) {
                $reason = "A new version is on '$Branch' ($($newer.Substring(0, 7)))"
                break
            }
        } catch {
            if (-not $checkFailed) {
                Write-Log "Could not check for a new version ($($_.Exception.Message)). Trying again every $CheckMinutes minutes."
            }
            $checkFailed = $true
        }
    }
    Start-Sleep -Seconds 5
}
if ($reason) {
    Write-Log "$reason. Updating to the newest '$Branch' and restarting."
    # Run this script again: it stops the server, backs up, updates and starts the new one.
    & $PSCommandPath -Branch $Branch -Port $Port -DataDir $DataDir -KeepBackups $KeepBackups `
        -StartTimeoutSeconds $StartTimeoutSeconds -CheckMinutes $CheckMinutes
    exit $LASTEXITCODE
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Log "Budget Manager stopped."
