# =========================================================================
# setup_task.ps1 - Dang ky Checkin Guard chay tu dong khi login Windows
# qua Task Scheduler, o scope USER hien tai - KHONG can quyen Admin.
#
# Neu lan dau chay bi chan boi ExecutionPolicy, mo PowerShell va chay:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# roi chay lai script nay.
# =========================================================================

$ErrorActionPreference = "Stop"

$TaskName   = "CheckinGuard"
$ScriptPath = Join-Path $PSScriptRoot "checkin_guard.pyw"

# ---- Kiem tra file script chinh ton tai ---------------------------------
if (-not (Test-Path $ScriptPath)) {
    Write-Host "LOI: Khong tim thay $ScriptPath" -ForegroundColor Red
    Write-Host "Hay dat setup_task.ps1 cung thu muc voi checkin_guard.pyw"
    exit 1
}

# ---- Tim pythonw.exe (ban khong hien console) ----------------------------
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
    Write-Host "LOI: Khong tim thay pythonw.exe." -ForegroundColor Red
    Write-Host "Hay cai Python tu https://www.python.org/downloads/ va nho tick 'Add python.exe to PATH'."
    exit 1
}

Write-Host "Dung Python : $PythonW"
Write-Host "Script      : $ScriptPath"

# ---- Xoa task cu neu da ton tai (de chay lai script nay an toan) ---------
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Da xoa task cu '$TaskName' de dang ky lai."
}

# ---- Tao task: trigger AtLogOn, chay o quyen user hien tai ---------------
# KHONG dung -RunLevel Highest, KHONG chay duoi SYSTEM -> khong can Admin.
# UserId phai o dang "MAY\user" hoac "DOMAIN\user" - ten user tran se bi
# Task Scheduler bao "The parameter is incorrect".
$UserId  = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action  = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$ScriptPath`""
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
    -Description "Nhac nho check-in / check-out khi login va sau khi may thuc day" `
    -ErrorAction Stop | Out-Null

# Xac nhan task da thuc su ton tai truoc khi bao thanh cong.
Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null

Write-Host ""
Write-Host "==> Dang ky thanh cong task '$TaskName'!" -ForegroundColor Green
Write-Host ""
Write-Host "Cac lenh huu ich:" -ForegroundColor Cyan
Write-Host "  Test ngay khong can login lai : Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Xem trang thai                : Get-ScheduledTask -TaskName $TaskName"
Write-Host "  Go bo task                    : Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "Chay thu ngay bay gio? Go lenh sau:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
