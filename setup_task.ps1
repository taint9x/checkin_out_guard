<#
setup_task.ps1
--------------
Registers a Task Scheduler task to run the guard every time you log into
Windows. Does NOT require Admin rights (only creates a task for the current
user, "Run only when user is logged on").

Auto-detects which build is present in this folder, in priority order:
  1. checkin_guard.exe (flat file)          -> onefile build (Option 1 / Option 3), single portable exe
  2. checkin_guard\checkin_guard.exe        -> onedir build, only if you built it that way yourself
  3. checkin_guard.pyw                      -> runs it via pythonw.exe found in PATH (Option 2 in README)

Tries two ways to register the task:
  1. Register-ScheduledTask (PowerShell cmdlet, goes through WMI/CIM)
  2. schtasks.exe with a generated Task XML (goes through the classic Task
     Scheduler COM API, not WMI)
On some machines - especially corporate/managed ones - the WMI path used by
Register-ScheduledTask is locked down (by IT hardening or security
software) and fails with "Access is denied" even though the Task Scheduler
service itself works fine and the classic API is unrestricted. If method 1
fails, this script automatically retries with method 2.

HOW TO RUN:
  1. Open a REGULAR PowerShell (no need for "Run as Administrator")
  2. cd into the folder containing this file
  3. If script execution is blocked, run this once:
       Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  4. Run:  .\setup_task.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuardExeFlat = Join-Path $ScriptDir "checkin_guard.exe"
$GuardExeOnedir = Join-Path $ScriptDir "checkin_guard\checkin_guard.exe"
$GuardPyw = Join-Path $ScriptDir "checkin_guard.pyw"

if (Test-Path $GuardExeFlat) {
    $TargetExecute = $GuardExeFlat
    $TargetArguments = ""
}
elseif (Test-Path $GuardExeOnedir) {
    $TargetExecute = $GuardExeOnedir
    $TargetArguments = ""
}
elseif (Test-Path $GuardPyw) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        Write-Error "pythonw.exe not found in PATH. Install Python (python.org) and make sure to check 'Add to PATH' during setup."
        exit 1
    }
    $TargetExecute = $pythonw
    $TargetArguments = "`"$GuardPyw`""
}
else {
    Write-Error "No checkin_guard build found in $ScriptDir (looked for checkin_guard\checkin_guard.exe, checkin_guard.exe, checkin_guard.pyw)."
    exit 1
}

$TaskName = "CheckinCheckoutGuard"
$RunDescription = if ($TargetArguments) { "$TargetExecute $TargetArguments" } else { $TargetExecute }

# ---------- Method 1: Register-ScheduledTask (WMI/CIM) ----------
$Method1Failed = $false
try {
    if ($TargetArguments) {
        $Action = New-ScheduledTaskAction -Execute $TargetExecute -Argument $TargetArguments
    }
    else {
        $Action = New-ScheduledTaskAction -Execute $TargetExecute
    }
    $Trigger = New-ScheduledTaskTrigger -AtLogOn
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Settings $Settings -Description "Reminds check-in/check-out on login/shutdown/wake" `
        -Force -ErrorAction Stop | Out-Null
}
catch {
    $Method1Failed = $true
    Write-Host "Register-ScheduledTask failed ($($_.Exception.Message)) - trying schtasks.exe instead..." -ForegroundColor Yellow
}

# ---------- Method 2: schtasks.exe + Task XML (classic COM API, bypasses WMI) ----------
if ($Method1Failed) {
    $EscExecute = [System.Security.SecurityElement]::Escape($TargetExecute)
    $EscArguments = [System.Security.SecurityElement]::Escape($TargetArguments)

    $TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Reminds check-in/check-out on login/shutdown/wake</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$EscExecute</Command>
      <Arguments>$EscArguments</Arguments>
    </Exec>
  </Actions>
</Task>
"@

    $XmlPath = Join-Path $env:TEMP "CheckinCheckoutGuard.xml"
    # schtasks.exe /XML requires UTF-16 LE encoding
    [System.IO.File]::WriteAllText($XmlPath, $TaskXml, [System.Text.Encoding]::Unicode)

    try {
        $schtasksOutput = & schtasks.exe /Create /TN $TaskName /XML $XmlPath /F 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "schtasks.exe also failed (exit $LASTEXITCODE): $schtasksOutput`nThis machine's Task Scheduler is likely locked down by IT policy. See the 'Không đăng ký được Task Scheduler' section in README.md for the Startup-folder workaround."
            exit 1
        }
    }
    finally {
        Remove-Item $XmlPath -ErrorAction SilentlyContinue
    }
}

Write-Host "Task '$TaskName' created successfully." -ForegroundColor Green
Write-Host "Task will run: $RunDescription"
Write-Host ""
Write-Host "To test now (no need to logoff/login again), run:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "To remove the task, run:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host "  (or: schtasks.exe /Delete /TN $TaskName /F)"
