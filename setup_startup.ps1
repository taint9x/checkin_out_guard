<#
setup_startup.ps1
------------------
Alternative to setup_task.ps1 for machines where Task Scheduler is locked
down (Register-ScheduledTask and/or schtasks.exe both fail with "Access is
denied" - common on hardened/managed corporate PCs).

Instead of a Task Scheduler task, this creates a shortcut in your personal
Startup folder (%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup).
Windows runs everything in that folder automatically at login - no special
permission is needed, any standard user account can write to it.

This covers the "run at login" part. The shutdown-block and resume-popup
behavior is handled entirely by the program itself once it's running, so
it works exactly the same as with Task Scheduler - the only difference is
how the program gets started at login.

Auto-detects which build is present in this folder, same priority order as
setup_task.ps1:
  1. checkin_guard.exe (flat file)
  2. checkin_guard\checkin_guard.exe
  3. checkin_guard.pyw (via pythonw.exe)

HOW TO RUN:
  1. Open a REGULAR PowerShell (no need for "Run as Administrator")
  2. cd into the folder containing this file
  3. Run:  .\setup_startup.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuardExeFlat = Join-Path $ScriptDir "checkin_guard.exe"
$GuardExeOnedir = Join-Path $ScriptDir "checkin_guard\checkin_guard.exe"
$GuardPyw = Join-Path $ScriptDir "checkin_guard.pyw"

if (Test-Path $GuardExeFlat) {
    $TargetPath = $GuardExeFlat
    $Arguments = ""
}
elseif (Test-Path $GuardExeOnedir) {
    $TargetPath = $GuardExeOnedir
    $Arguments = ""
}
elseif (Test-Path $GuardPyw) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        Write-Error "pythonw.exe not found in PATH. Install Python (python.org) and make sure to check 'Add to PATH' during setup."
        exit 1
    }
    $TargetPath = $pythonw
    $Arguments = "`"$GuardPyw`""
}
else {
    Write-Error "No checkin_guard build found in $ScriptDir (looked for checkin_guard\checkin_guard.exe, checkin_guard.exe, checkin_guard.pyw)."
    exit 1
}

$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "CheckinCheckoutGuard.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.Arguments = $Arguments
$Shortcut.WorkingDirectory = Split-Path -Parent $TargetPath
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "Will run at every login: $TargetPath $Arguments"
Write-Host ""
Write-Host "To test now (without logging off), run:" -ForegroundColor Yellow
Write-Host "  & `"$ShortcutPath`""
Write-Host ""
Write-Host "To remove, delete the shortcut:" -ForegroundColor Yellow
Write-Host "  Remove-Item `"$ShortcutPath`""
