<#
sign_exe.ps1
------------
Signs checkin_guard.exe with a self-signed code-signing certificate so the
file has a verifiable publisher on THIS machine (and on any machine where
you import the same certificate).

What this does and does not solve:
  [x] "Unknown publisher" warnings from SmartScreen / UAC-style prompts
  [x] Lets corporate IT create a Publisher rule (WDAC/AppLocker) trusting
      this certificate, instead of re-whitelisting every new build by hash
  [ ] Smart App Control (SAC): NOT satisfied - SAC only trusts certificates
      issued by real Certificate Authorities or apps with established
      reputation. If SAC is blocking files, the options are: turn SAC off
      (Windows Security > App & browser control > Smart App Control - this
      is one-way, it cannot be re-enabled without reinstalling Windows), or
      buy a CA-issued code-signing certificate, or have IT deploy a WDAC
      policy instead.

NOTE: importing the certificate into the "Trusted Root" store pops up a
security confirmation dialog - read it and click Yes. That prompt is
Windows working as intended.

HOW TO RUN (regular PowerShell, no Admin needed):
  .\sign_exe.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ScriptDir "checkin_guard.exe"

if (-not (Test-Path $ExePath)) {
    Write-Error "checkin_guard.exe not found in $ScriptDir"
    exit 1
}

$Subject = "CN=CheckinGuard Self-Signed"

# Reuse the cert if it already exists (so every rebuild is signed by the
# same publisher), otherwise create it.
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $Subject } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $cert) {
    Write-Host "Creating self-signed code-signing certificate '$Subject'..."
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
        -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5)
}
else {
    Write-Host "Reusing existing certificate '$Subject' (expires $($cert.NotAfter))."
}

# Trust the cert on this machine (CurrentUser scope, no Admin needed).
# Without this, the signature exists but shows as "not trusted".
$cerPath = Join-Path $env:TEMP "checkin_guard_publisher.cer"
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null
try {
    $alreadyTrusted = Get-ChildItem Cert:\CurrentUser\Root |
        Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if (-not $alreadyTrusted) {
        Write-Host "Importing certificate into CurrentUser Trusted Root (a confirmation dialog will appear - click Yes)..." -ForegroundColor Yellow
        Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    }
    $alreadyPublisher = Get-ChildItem Cert:\CurrentUser\TrustedPublisher |
        Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if (-not $alreadyPublisher) {
        Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
    }
}
finally {
    Remove-Item $cerPath -ErrorAction SilentlyContinue
}

Write-Host "Signing $ExePath ..."
$sig = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert `
    -TimestampServer "http://timestamp.digicert.com" -HashAlgorithm SHA256

Write-Host ""
Write-Host "Signature status: $($sig.Status) - $($sig.StatusMessage)" -ForegroundColor $(if ($sig.Status -eq "Valid") { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "The exported certificate for IT / other machines can be re-exported with:" -ForegroundColor Yellow
Write-Host "  Export-Certificate -Cert (Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object Subject -eq '$Subject') -FilePath checkin_guard_publisher.cer"
