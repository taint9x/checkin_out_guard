<#
create_shutdown_shortcut.ps1
-----------------------------
Creates a "Shutdown (with check-in)" shortcut on your Desktop that runs
`checkin_guard.exe --shutdown`.

Clicking that shortcut does NOTHING except show the check-in/check-out
popup. Only pressing "Confirmed" actually shuts the machine down;
"Not yet..." opens the check-in website and the popup stays.

This is the recommended way to shut down, because Windows does not allow
any app to fully intercept the native Start-menu Shutdown button: that
path always shows Windows' own fullscreen "app is preventing shutdown"
screen (with an unremovable "Shut down anyway" button) before the popup
can be seen.

HOW TO RUN (regular PowerShell, no Admin needed):
  .\create_shutdown_shortcut.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuardExe = Join-Path $ScriptDir "checkin_guard.exe"

if (-not (Test-Path $GuardExe)) {
    Write-Error "checkin_guard.exe not found in $ScriptDir"
    exit 1
}

$DesktopFolder = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopFolder "Shutdown (with check-in).lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $GuardExe
$Shortcut.Arguments = "--shutdown"
$Shortcut.WorkingDirectory = $ScriptDir
# Standard Windows shutdown icon
$Shortcut.IconLocation = "%SystemRoot%\System32\SHELL32.dll,27"
$Shortcut.Description = "Shows the check-in/check-out popup first; shuts down only after you confirm"
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host ""
Write-Host "Use this shortcut instead of Start > Power > Shut down." -ForegroundColor Yellow
Write-Host "Clicking it shows the popup; 'Confirmed' really shuts down, 'Not yet' opens the check-in website."
