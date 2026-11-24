<#
.SYNOPSIS
    Prepare a Windows machine as an Agentica target: WinRM over HTTPS (port 5986)
    with a self-signed certificate. Idempotent. Run as Administrator.

.DESCRIPTION
    - Starts WinRM and sets it to start automatically.
    - Creates (or reuses) a self-signed certificate "Agentica WinRM" in LocalMachine\My.
    - Creates one HTTPS listener on 5986 and REMOVES any plain-HTTP (5985) listener:
      Agentica only ever uses HTTPS.
    - Disables Basic auth and unencrypted traffic; Negotiate/NTLM stays enabled.
    - Opens TCP 5986 in the firewall for the Domain and Private profiles only
      (never Public unless you pass it explicitly). Not done with -LocalOnly.
    - Exports the certificate and prints its SHA-1 thumbprint. Compare it with the
      thumbprint shown by "Fetch from server" on the Agentica Machines page, then Trust.

.PARAMETER LocalOnly
    Bind the listener to 127.0.0.1 and open no firewall port. Use this when Agentica
    manages the same PC it runs on (testing / demo): nothing is reachable from the network.

.PARAMETER FirewallProfile
    Firewall profiles for the inbound 5986 rule (ignored with -LocalOnly). Default Domain,Private.

.PARAMETER CreateUser
    Create or update a dedicated, visible local administrator account for Agentica with a
    random 32-character password (never expires). This also sets
    LocalAccountTokenFilterPolicy=1, which Windows requires for a LOCAL admin account to
    administer the machine over WinRM (UAC remote restrictions; `winrm quickconfig` sets the
    same value). Domain accounts don't need it. -Uninstall reverts both.

.PARAMETER PasswordFile
    With -CreateUser: write the generated password to this file (ACL: current user only)
    instead of printing it, so it can be handed to Agentica's keyring and deleted.

.PARAMETER ResultFile
    Write a JSON summary (thumbprint, endpoint, user) for automation.

.PARAMETER LogFile
    Write a transcript (useful when the script is launched elevated in a new window).

.PARAMETER Uninstall
    Undo: remove the HTTPS listener, firewall rule and certificate, stop WinRM and set it
    back to Manual. With -CreateUser also deletes that account and the token-policy setting.

.EXAMPLE
    # A server Agentica will manage over the network:
    .\windows-target-setup.ps1 -CreateUser agentica
.EXAMPLE
    # The same PC Agentica runs on (local-only, password handed to a file):
    .\windows-target-setup.ps1 -LocalOnly -CreateUser agentica -PasswordFile C:\path\pw.txt
.EXAMPLE
    .\windows-target-setup.ps1 -Uninstall -CreateUser agentica
#>
[CmdletBinding()]
param(
    [switch]$LocalOnly,
    [string[]]$FirewallProfile = @("Domain", "Private"),
    [string]$CreateUser,
    [string]$PasswordFile,
    [string]$ResultFile,
    [string]$LogFile,
    [switch]$Uninstall
)
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$Port = 5986
$FriendlyName = "Agentica WinRM"
$RuleName = "Agentica WinRM HTTPS $Port"
$LegacyRuleName = "WinRM HTTPS $Port"   # created by an older version of this script
$TokenPolicyKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"

function Remove-Listeners([string]$Transport) {
    Get-ChildItem WSMan:\localhost\Listener |
        Where-Object { $_.Keys -contains "Transport=$Transport" } |
        ForEach-Object { Remove-Item -Path $_.PSPath -Recurse -Force }
}

function New-RandomPassword {
    $alphabet = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#%^*-_=+'
    $bytes = New-Object byte[] 28
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $core = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
    return $core + 'Aa7!'   # guarantees every character class for complexity policies
}

if ($LogFile) { Start-Transcript -Path $LogFile -Force | Out-Null }
try {
    Write-Host "=== Agentica WinRM HTTPS setup ($(if ($Uninstall) { 'uninstall' } else { 'install' })) ===" -ForegroundColor Cyan

    # WinRM must be running for the WSMan: drive to work.
    if ((Get-Service WinRM).Status -ne "Running") { Start-Service WinRM }

    if ($Uninstall) {
        Remove-Listeners "HTTPS"
        Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.FriendlyName -eq $FriendlyName } | Remove-Item
        if ($CreateUser) {
            if (Get-LocalUser -Name $CreateUser -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $CreateUser }
            Remove-ItemProperty -Path $TokenPolicyKey -Name LocalAccountTokenFilterPolicy -ErrorAction SilentlyContinue
            Write-Host "Removed account '$CreateUser' and LocalAccountTokenFilterPolicy"
        }
        Stop-Service WinRM
        Set-Service WinRM -StartupType Manual
        Write-Host "=== Uninstalled: listener, firewall rule, certificate removed; WinRM stopped (Manual) ===" -ForegroundColor Green
        return
    }

    # 1. Service
    Set-Service WinRM -StartupType Automatic
    Write-Host "WinRM service running, startup = Automatic"

    # 2. Certificate (reuse while valid for 30+ more days)
    $cert = Get-ChildItem Cert:\LocalMachine\My |
        Where-Object { $_.FriendlyName -eq $FriendlyName -and $_.NotAfter -gt (Get-Date).AddDays(30) } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -CertStoreLocation "Cert:\LocalMachine\My" `
            -DnsName $env:COMPUTERNAME, "localhost" -FriendlyName $FriendlyName `
            -NotAfter (Get-Date).AddYears(3) -KeyExportPolicy NonExportable
        Write-Host "Created self-signed certificate $($cert.Thumbprint)"
    } else {
        Write-Host "Reusing certificate $($cert.Thumbprint) (valid until $($cert.NotAfter.ToString('yyyy-MM-dd')))"
    }

    # 3. Listeners: exactly one HTTPS listener; no plain HTTP at all
    Remove-Listeners "HTTP"
    Remove-Listeners "HTTPS"
    $address = if ($LocalOnly) { "IP:127.0.0.1" } else { "*" }
    New-WSManInstance -ResourceURI "winrm/config/Listener" `
        -SelectorSet @{ Transport = "HTTPS"; Address = $address } `
        -ValueSet @{ Hostname = $env:COMPUTERNAME; CertificateThumbprint = $cert.Thumbprint } | Out-Null
    Write-Host "HTTPS listener on $address port $Port (HTTP listeners removed)"

    # 4. Authentication: no Basic, no unencrypted traffic.
    # Read first and only write what differs, through Set-WSManInstance: the WSMan: drive's
    # Set-Item refuses ANY service change while a network is "Public" ("WinRM firewall
    # exception will not work..."), even though nothing here touches the firewall.
    $svcCfg = Get-WSManInstance -ResourceURI "winrm/config/service"
    $authCfg = Get-WSManInstance -ResourceURI "winrm/config/service/auth"
    if ($svcCfg.AllowUnencrypted -ne "false") {
        Set-WSManInstance -ResourceURI "winrm/config/service" -ValueSet @{ AllowUnencrypted = "false" } | Out-Null
    }
    if ($authCfg.Basic -ne "false" -or $authCfg.Negotiate -ne "true") {
        Set-WSManInstance -ResourceURI "winrm/config/service/auth" -ValueSet @{ Basic = "false"; Negotiate = "true" } | Out-Null
    }
    $svcCfg = Get-WSManInstance -ResourceURI "winrm/config/service"
    $authCfg = Get-WSManInstance -ResourceURI "winrm/config/service/auth"
    if ($svcCfg.AllowUnencrypted -ne "false" -or $authCfg.Basic -ne "false" -or $authCfg.Negotiate -ne "true") {
        throw "WinRM auth settings could not be enforced (AllowUnencrypted=$($svcCfg.AllowUnencrypted), Basic=$($authCfg.Basic), Negotiate=$($authCfg.Negotiate))"
    }
    Write-Host "Auth: Basic off, unencrypted off, Negotiate/NTLM on (verified)"

    # 5. Firewall
    Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallRule -DisplayName $LegacyRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($LocalOnly) {
        Write-Host "LocalOnly: no firewall port opened"
    } else {
        New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Protocol TCP -LocalPort $Port `
            -Action Allow -Profile $FirewallProfile | Out-Null
        Write-Host "Firewall: inbound TCP $Port allowed on profiles $($FirewallProfile -join ', ')"
    }

    # 6. Optional dedicated account
    $userOut = $null
    if ($CreateUser) {
        $plain = New-RandomPassword
        $secure = ConvertTo-SecureString $plain -AsPlainText -Force
        if (Get-LocalUser -Name $CreateUser -ErrorAction SilentlyContinue) {
            Set-LocalUser -Name $CreateUser -Password $secure -PasswordNeverExpires $true
            Enable-LocalUser -Name $CreateUser
            Write-Host "Updated account '$CreateUser' with a new random password"
        } else {
            New-LocalUser -Name $CreateUser -Password $secure -PasswordNeverExpires -AccountNeverExpires `
                -Description "Agentica remote management over WinRM" | Out-Null   # Windows limit: 48 chars
            Write-Host "Created account '$CreateUser'"
        }
        try {
            Add-LocalGroupMember -SID "S-1-5-32-544" -Member $CreateUser
        } catch {
            if ($_.FullyQualifiedErrorId -notlike "*MemberExists*") { throw }
        }
        New-ItemProperty -Path $TokenPolicyKey -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null
        Write-Host "'$CreateUser' is in Administrators; LocalAccountTokenFilterPolicy=1 (needed for a local admin over WinRM)"
        $userOut = "$env:COMPUTERNAME\$CreateUser"

        if ($PasswordFile) {
            Set-Content -Path $PasswordFile -Value $plain -NoNewline -Encoding ASCII
            $me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
            # Drop inherited permissions; only the current user (who launched Agentica) may read it.
            & icacls.exe $PasswordFile /inheritance:r /grant:r "${me}:(F)" | Out-Null
            if ($LASTEXITCODE -ne 0) { Remove-Item $PasswordFile -Force; throw "Could not restrict permissions on $PasswordFile" }
            Write-Host "Password written to $PasswordFile (readable only by $me) - hand it to Agentica, then delete the file"
        } else {
            Write-Host "Password for ${userOut}: $plain" -ForegroundColor Yellow
            Write-Host "Enter it on the Agentica Machines page now; it is not stored anywhere else." -ForegroundColor Yellow
        }
    }

    # 7. Export certificate + summary
    $certDir = Join-Path $env:ProgramData "Agentica"
    New-Item -ItemType Directory -Force -Path $certDir | Out-Null
    $certPath = Join-Path $certDir "agentica-winrm.cer"
    Export-Certificate -Cert $cert -FilePath $certPath -Force | Out-Null

    $endpointHost = if ($LocalOnly) { "127.0.0.1" } else { $env:COMPUTERNAME }
    $result = [ordered]@{
        thumbprint       = $cert.Thumbprint
        endpoint         = "https://${endpointHost}:$Port/wsman"
        computer         = $env:COMPUTERNAME
        user             = $userOut
        local_only       = [bool]$LocalOnly
        certificate_file = $certPath
    }
    if ($ResultFile) { $result | ConvertTo-Json | Set-Content -Path $ResultFile -Encoding UTF8 }

    Write-Host ""
    Write-Host "=== Setup complete ===" -ForegroundColor Green
    Write-Host "Endpoint:   $($result.endpoint)"
    Write-Host "Thumbprint: $($cert.Thumbprint)  (compare with 'Fetch from server' in Agentica, then Trust)" -ForegroundColor Yellow
    Write-Host "Certificate exported to $certPath"
} finally {
    if ($LogFile) { Stop-Transcript | Out-Null }
}
