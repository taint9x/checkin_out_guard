# =========================================================================
# setup_task.ps1 - Dang ky Checkin Guard (ban Qt) chay tu dong khi login
# qua Task Scheduler, o scope USER hien tai - KHONG can quyen Admin.
#
# Neu lan dau chay bi chan boi ExecutionPolicy:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# =========================================================================

$ErrorActionPreference = "Stop"

$TaskName   = "CheckinGuardQt"
$ScriptPath = Join-Path $PSScriptRoot "checkin_guard_qt.pyw"

# ---- Uu tien ban build .exe neu co (khong can Python tren may) -----------
$ExeCandidates = @(
    (Join-Path $PSScriptRoot "dist\checkin_reminder.exe"),
    (Join-Path $PSScriptRoot "checkin_reminder.exe"),
    (Join-Path $PSScriptRoot "dist\checkin_guard.exe"),
    (Join-Path $PSScriptRoot "checkin_guard.exe")
)
$ExePath = $ExeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($ExePath) {
    Write-Host "Dung ban exe : $ExePath"
    $Action = New-ScheduledTaskAction -Execute $ExePath
} else {
    if (-not (Test-Path $ScriptPath)) {
        Write-Host "LOI: Khong tim thay $ScriptPath (va cung khong co file .exe)" -ForegroundColor Red
        exit 1
    }
    # ---- Tim pythonw.exe (ban khong hien console) ------------------------
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
        Write-Host "LOI: Khong tim thay pythonw.exe. Hay cai Python va tick 'Add python.exe to PATH'." -ForegroundColor Red
        exit 1
    }
    Write-Host "Dung Python : $PythonW"
    Write-Host "Script      : $ScriptPath"
    $Action = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$ScriptPath`""
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Da xoa task cu '$TaskName' de dang ky lai."
}

# UserId phai o dang "MAY\user" hoac "DOMAIN\user".
$UserId  = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Nhac nho check-in / check-out (ban Qt) khi login va sau khi may thuc day" `
    -ErrorAction Stop | Out-Null

Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null

Write-Host ""
Write-Host "==> Dang ky thanh cong task '$TaskName'!" -ForegroundColor Green
Write-Host ""
Write-Host "Cac lenh huu ich:" -ForegroundColor Cyan
Write-Host "  Test ngay khong can login lai : Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Go bo task                    : Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "LUU Y: Neu ban tkinter (task 'CheckinGuard') cung dang bat, nen go bot 1 trong 2." -ForegroundColor Yellow
