# Idempotent WinRM HTTPS setup for Agentica target (run as Administrator)
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$Port = 5986
$CertSubject = "CN=$env:COMPUTERNAME"

Write-Host "=== Agentica WinRM HTTPS Setup ===" -ForegroundColor Cyan

# 1. Enable PowerShell Remoting
if (-not (Get-PSSessionConfiguration -Name "Microsoft.PowerShell" -ErrorAction SilentlyContinue)) {
    Enable-PSRemoting -Force -SkipNetworkProfileCheck
    Write-Host "PSRemoting enabled"
}

# 2. Create self-signed cert if missing
$cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -eq $CertSubject } | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -DnsName $env:COMPUTERNAME `
        -NotAfter (Get-Date).AddYears(5)
    Write-Host "Created self-signed certificate: $($cert.Thumbprint)"
} else {
    Write-Host "Using existing certificate: $($cert.Thumbprint)"
}

# 3. Create HTTPS listener (idempotent)
$listener = Get-WSManInstance -ResourceURI "winrm/config/Listener" -SelectorSet @{Transport="HTTPS"; Address="*"} -ErrorAction SilentlyContinue
if (-not $listener) {
    New-WSManInstance -ResourceURI "winrm/config/Listener" `
        -SelectorSet @{Transport="HTTPS"; Address="*"} `
        -ValueSet @{Hostname=$env:COMPUTERNAME; CertificateThumbprint=$cert.Thumbprint}
    Write-Host "HTTPS WinRM listener created on port $Port"
} else {
    Write-Host "HTTPS WinRM listener already exists"
}

# 4. Open firewall port 5986
$rule = Get-NetFirewallRule -DisplayName "WinRM HTTPS $Port" -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName "WinRM HTTPS $Port" `
        -Direction Inbound -Protocol TCP -LocalPort $Port `
        -Action Allow -Profile Any
    Write-Host "Firewall rule added for port $Port"
}

# 5. Set auth to NTLM/Negotiate
Set-WSManInstance -ResourceURI "winrm/config/service/auth" -ValueSet @{
    Basic    = $false
    Kerberos = $true
    Negotiate = $true
    NTLM     = $true
}

# 6. Export certificate
$certPath = "$env:TEMP\agentica-winrm.cer"
Export-Certificate -Cert $cert -FilePath $certPath | Out-Null
Write-Host "Certificate exported to: $certPath"

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Thumbprint: $($cert.Thumbprint)" -ForegroundColor Yellow
Write-Host "Add to targets.yaml: trusted_thumbprint: $($cert.Thumbprint)" -ForegroundColor Yellow
Write-Host "Endpoint: https://$($env:COMPUTERNAME):$Port/wsman"
