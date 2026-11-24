@echo off
title Agentica Stop
color 0C

:: The backend usually runs as Administrator (see start.bat), so stopping it needs elevation.
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  Stopping Agentica servers...
echo.

:: Kill backend (python run.py on port 8765)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765.*LISTENING" 2^>nul') do (
    echo  Stopping backend (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

:: Kill Vite (port 5173)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173.*LISTENING" 2^>nul') do (
    echo  Stopping UI dev server (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

:: Close the titled windows (an elevated window is titled "Administrator: Agentica Backend")
powershell -NoProfile -Command "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*Agentica Backend*' -or $_.MainWindowTitle -like '*Agentica UI*' } | Stop-Process -Force" >nul 2>&1

echo  Done. All servers stopped.
echo.
pause
