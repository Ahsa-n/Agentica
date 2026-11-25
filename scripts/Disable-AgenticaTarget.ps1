<#
.SYNOPSIS
  Undoes Enable-AgenticaTarget.ps1. Run in an elevated PowerShell.

.DESCRIPTION
  Removes the firewall rule, turns WinRM remoting off, restores the remote-admin
  restriction, and deletes the Agentica account. Only an account created by
  Enable-AgenticaTarget.ps1 is ever deleted (recognised by its description).

.EXAMPLE
  .\Disable-AgenticaTarget.ps1                    # also deletes the 'agentica' account
  .\Disable-AgenticaTarget.ps1 -UserName opsbot   # if you created it under another name
  .\Disable-AgenticaTarget.ps1 -KeepUser          # leave the account in place
#>
[CmdletBinding()]
param(
    [string]$UserName = 'agentica',
    [switch]$KeepUser
)

$ErrorActionPreference = 'Continue'
$Marker = 'Used by Agentica to manage this machine over WinRM'

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Run this script in an elevated PowerShell (right-click > Run as administrator).' -ForegroundColor Red
    exit 1
}

Write-Host "`nRemoving Agentica access from $env:COMPUTERNAME`n" -ForegroundColor Yellow
Get-NetFirewallRule -DisplayName 'Agentica WinRM (HTTP-In)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' `
    -Name LocalAccountTokenFilterPolicy -ErrorAction SilentlyContinue
Disable-PSRemoting -Force -WarningAction SilentlyContinue
Stop-Service -Name WinRM -ErrorAction SilentlyContinue
Set-Service -Name WinRM -StartupType Manual

if (-not $KeepUser) {
    $user = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
    if (-not $user) {
        Write-Host "  No local account named '$UserName'; nothing to delete."
    } elseif ($user.Description -ne $Marker) {
        Write-Host "  '$UserName' was not created by Enable-AgenticaTarget.ps1, so it was left untouched." -ForegroundColor Yellow
    } else {
        Remove-LocalUser -Name $UserName
        Write-Host "  Deleted the account '$UserName'."
    }
}
Write-Host 'Done. WinRM is stopped and the firewall rule is removed.' -ForegroundColor Green
