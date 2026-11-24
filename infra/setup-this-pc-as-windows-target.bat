@echo off
:: Make THIS PC an Agentica Windows (WinRM HTTPS) target, local-only (testing / demo).
:: Runs infra\windows-target-setup.ps1 as Administrator (you approve the UAC prompt):
::   - WinRM HTTPS listener on 127.0.0.1:5986 only (not reachable from the network, no firewall port)
::   - self-signed certificate "Agentica WinRM"
::   - visible local admin account "agentica" with a random password, handed to Agentica's
::     keyring via a file only your account can read (Agentica deletes it after reading)
::   - LocalAccountTokenFilterPolicy=1 (Windows requires it for a local admin over WinRM)
:: Undo everything:  setup-this-pc-as-windows-target.bat /uninstall
setlocal
set "HANDOFF=%LOCALAPPDATA%\ATCO\agentica\winrm-handoff"

net session >nul 2>&1
if errorlevel 1 (
    if "%~1"=="" (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    ) else (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1' -Verb RunAs"
    )
    exit /b
)

if not exist "%HANDOFF%" mkdir "%HANDOFF%"
if /i "%~1"=="/uninstall" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-target-setup.ps1" -Uninstall -CreateUser agentica -LogFile "%HANDOFF%\uninstall.log"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-target-setup.ps1" -LocalOnly -CreateUser agentica -PasswordFile "%HANDOFF%\password.txt" -ResultFile "%HANDOFF%\result.json" -LogFile "%HANDOFF%\setup.log"
)
echo.
echo You can close this window.
pause
