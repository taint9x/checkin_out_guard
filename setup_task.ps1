<#
setup_task.ps1
--------------
Registers a Task Scheduler task to run the guard every time you log into
Windows. Does NOT require Admin rights (only creates a task for the current
user, "Run only when user is logged on").

Auto-detects which file is present in this folder:
  - checkin_guard.exe  -> runs the exe directly (Option 1 / Option 3 in README)
  - checkin_guard.pyw  -> runs it via pythonw.exe found in PATH (Option 2 in README)
If both exist, checkin_guard.exe takes priority.

HOW TO RUN:
  1. Open a REGULAR PowerShell (no need for "Run as Administrator")
  2. cd into the folder containing this file
  3. If script execution is blocked, run this once:
       Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  4. Run:  .\setup_task.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuardExe = Join-Path $ScriptDir "checkin_guard.exe"
$GuardPyw = Join-Path $ScriptDir "checkin_guard.pyw"

if (Test-Path $GuardExe) {
    $Action = New-ScheduledTaskAction -Execute $GuardExe
    $RunDescription = $GuardExe
}
elseif (Test-Path $GuardPyw) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        Write-Error "pythonw.exe not found in PATH. Install Python (python.org) and make sure to check 'Add to PATH' during setup."
        exit 1
    }
    $Action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$GuardPyw`""
    $RunDescription = "$pythonw `"$GuardPyw`""
}
else {
    Write-Error "Neither checkin_guard.exe nor checkin_guard.pyw found in $ScriptDir."
    exit 1
}

$TaskName = "CheckinCheckoutGuard"

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

# No -RunLevel Highest, no SYSTEM -> no Admin required
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Reminds check-in/check-out on login/shutdown/wake" `
    -Force | Out-Null

Write-Host "Task '$TaskName' created successfully." -ForegroundColor Green
Write-Host "Task will run: $RunDescription"
Write-Host ""
Write-Host "To test now (no need to logoff/login again), run:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "To remove the task, run:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
