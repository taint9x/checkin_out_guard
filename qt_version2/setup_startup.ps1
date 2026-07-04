# =========================================================================
# setup_startup.ps1 - Phuong an du phong: tu dong chay khi login bang
# STARTUP FOLDER (khong dung Task Scheduler, khong can quyen Admin).
#
# Dung khi setup_task.ps1 bi chan boi Group Policy. Startup folder la
# co che loi cua Windows, gan nhu khong GPO nao chan.
#
# Cach dung:
#   .\setup_startup.ps1            -> tao shortcut trong Startup folder
#   .\setup_startup.ps1 -Remove    -> xoa shortcut (go bo)
# =========================================================================

param([switch]$Remove)

$ErrorActionPreference = "Stop"

$ShortcutName = "Checkin Reminder.lnk"
$StartupDir   = [Environment]::GetFolderPath("Startup")  # shell:startup cua user
$ShortcutPath = Join-Path $StartupDir $ShortcutName

if ($Remove) {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force -Confirm:$false
        Write-Host "Da xoa $ShortcutPath" -ForegroundColor Green
    } else {
        Write-Host "Khong co shortcut nao de xoa."
    }
    exit 0
}

# ---- Chon target: uu tien ban build .exe, khong co thi dung pythonw ------
$ExeCandidates = @(
    (Join-Path $PSScriptRoot "dist\checkin_reminder.exe"),
    (Join-Path $PSScriptRoot "checkin_reminder.exe"),
    (Join-Path $PSScriptRoot "dist\checkin_guard.exe"),
    (Join-Path $PSScriptRoot "checkin_guard.exe")
)
$ExePath = $ExeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($ExePath) {
    $Target    = $ExePath
    $Arguments = ""
    Write-Host "Dung ban exe : $ExePath"
} else {
    $ScriptPath = Join-Path $PSScriptRoot "checkin_guard_qt.pyw"
    if (-not (Test-Path $ScriptPath)) {
        Write-Host "LOI: Khong tim thay exe lan $ScriptPath" -ForegroundColor Red
        exit 1
    }
    $PythonW = $null
    try {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
        $Candidate = Join-Path (Split-Path $PythonExe) "pythonw.exe"
        if (Test-Path $Candidate) { $PythonW = $Candidate }
    } catch {}
    if (-not $PythonW) {
        try { $PythonW = (Get-Command pythonw -ErrorAction Stop).Source } catch {}
    }
    if (-not $PythonW) {
        Write-Host "LOI: Khong tim thay pythonw.exe. Hay cai Python (tick 'Add python.exe to PATH')." -ForegroundColor Red
        exit 1
    }
    $Target    = $PythonW
    $Arguments = "`"$ScriptPath`""
    Write-Host "Dung Python : $PythonW"
    Write-Host "Script      : $ScriptPath"
}

# ---- Tao shortcut .lnk trong Startup folder ------------------------------
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
if ($Arguments) { $Shortcut.Arguments = $Arguments }
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.Description = "Check-in / Check-out Reminder"
$Shortcut.Save()

Write-Host ""
Write-Host "==> Da tao shortcut: $ShortcutPath" -ForegroundColor Green
Write-Host "Tool se tu chay o lan dang nhap Windows tiep theo."
Write-Host "Go bo: .\setup_startup.ps1 -Remove"
