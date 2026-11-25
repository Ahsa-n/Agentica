<#
.SYNOPSIS
  Prepares a Windows machine so Agentica can manage it over WinRM (HTTP 5985, NTLM).

.DESCRIPTION
  Run ONCE on each Windows machine you want Agentica to manage, in an elevated
  PowerShell ("Run as administrator"). Nothing is installed: Agentica is agentless and
  connects in with WinRM, which is built into Windows.

  What it does:
    1. Creates a local administrator account for Agentica (default name: agentica).
       You choose its password (asked twice). Skip with -NoCreateUser to use an existing admin account.
    2. Enables PowerShell remoting (WinRM service + HTTP listener on 5985).
    3. Lets local administrator accounts sign in remotely with full rights
       (LocalAccountTokenFilterPolicy = 1). Needed on machines that are not in a domain.
    4. Opens TCP 5985 in Windows Firewall on every network profile
       (only from the Agentica PC's IP with -AgenticaIP).
    5. Prints exactly what to type into Agentica (Machines > +).

  Undo everything with Disable-AgenticaTarget.ps1.

.EXAMPLE
  .\Enable-AgenticaTarget.ps1                         # creates local admin 'agentica', asks for a password
  .\Enable-AgenticaTarget.ps1 -AgenticaIP 192.168.1.10
  .\Enable-AgenticaTarget.ps1 -UserName opsbot        # different account name
  .\Enable-AgenticaTarget.ps1 -NoCreateUser           # use an existing administrator account instead
#>
[CmdletBinding()]
param(
    [string]$AgenticaIP = 'Any',
    [string]$UserName = 'agentica',
    [switch]$NoCreateUser
)

$ErrorActionPreference = 'Stop'
# Accounts created by this script carry this description; the scripts never touch accounts without it.
$Marker = 'Used by Agentica to manage this machine over WinRM'

function Step($text) { Write-Host "  > $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`n  $text`n" -ForegroundColor Red; exit 1 }

function Test-AgUserName([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return 'The username is empty.' }
    if ($Name.Length -gt 20) { return 'The username can be at most 20 characters.' }
    if ($Name -match '["/\\\[\]:;|=,+*?<>@]') {
        return 'The username contains a character Windows does not allow:  " / \ [ ] : ; | = , + * ? < > @'
    }
    if ($Name.Trim('. ').Length -eq 0) { return 'The username cannot be only dots or spaces.' }
    if ($Name -ieq $env:COMPUTERNAME) { return 'The username cannot be the same as the computer name.' }
    return $null
}

function ConvertFrom-AgSecure([Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Read-AgPassword([string]$Name) {
    for ($try = 1; $try -le 3; $try++) {
        $first  = Read-Host -AsSecureString "  Choose a password for '$Name'"
        $second = Read-Host -AsSecureString '  Type it again to confirm'
        $a = ConvertFrom-AgSecure $first
        $b = ConvertFrom-AgSecure $second
        if ($a.Length -eq 0) {
            Write-Host '  The password cannot be empty (Windows blocks remote sign-in with a blank password).' -ForegroundColor Red
        } elseif ($a -cne $b) {
            Write-Host "  The passwords don't match. Try again." -ForegroundColor Red
        } else {
            return $first
        }
    }
    Fail 'No password was set. Nothing on this machine was changed.'
}

# ---------------------------------------------------------------- checks (nothing changed yet)

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'Run this script in an elevated PowerShell (right-click > Run as administrator).'
}

Write-Host "`nAgentica target setup on $env:COMPUTERNAME`n" -ForegroundColor Yellow

$account = "$env:COMPUTERNAME\<an administrator account>"
$password = $null
$existing = $null
if (-not $NoCreateUser) {
    $problem = Test-AgUserName $UserName
    if ($problem) { Fail "$problem Nothing on this machine was changed." }
    $existing = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
    if ($existing -and $existing.Description -ne $Marker) {
        Fail ("A local account named '$UserName' already exists and was not created by this script, so it " +
              "will not be modified. Pick another name with -UserName, or use it as-is with -NoCreateUser.")
    }
    $password = Read-AgPassword $UserName
}

# ---------------------------------------------------------------- changes

if (-not $NoCreateUser) {
    if ($existing) {
        Step "Updating the password of the existing Agentica account '$UserName'"
        Set-LocalUser -Name $UserName -Password $password
        Enable-LocalUser -Name $UserName
    } else {
        Step "Creating local administrator account '$UserName' for Agentica"
        try {
            New-LocalUser -Name $UserName -Password $password -PasswordNeverExpires -Description $Marker | Out-Null
        } catch {
            Fail "Windows refused to create the account: $($_.Exception.Message) Nothing else was changed."
        }
    }
    $admins = (New-Object Security.Principal.SecurityIdentifier 'S-1-5-32-544').Translate([Security.Principal.NTAccount]).Value.Split('\')[-1]
    Add-LocalGroupMember -Group $admins -Member $UserName -ErrorAction SilentlyContinue
    $account = "$env:COMPUTERNAME\$UserName"
}

Step 'Enabling PowerShell remoting (WinRM, HTTP listener on 5985)'
Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
Set-Service -Name WinRM -StartupType Automatic
Start-Service -Name WinRM

Step 'Allowing local administrator accounts to sign in remotely'
New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' `
    -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null

Step "Opening TCP 5985 in Windows Firewall (from: $AgenticaIP)"
Get-NetFirewallRule -DisplayName 'Agentica WinRM (HTTP-In)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'Agentica WinRM (HTTP-In)' -Direction Inbound -Protocol TCP -LocalPort 5985 `
    -RemoteAddress $AgenticaIP -Profile Any -Action Allow | Out-Null

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress

Write-Host "`nDone. In Agentica: Machines > + and enter:" -ForegroundColor Green
Write-Host "  Machine     : $env:COMPUTERNAME   (or $($ips -join ' / '))"
Write-Host "  OS          : Windows"
Write-Host "  Connection  : WinRM over HTTP / 5985"
Write-Host "  Username    : $account"
if ($NoCreateUser) { Write-Host "  Password    : that account's password`n" }
else { Write-Host "  Password    : the password you just chose`n" }
