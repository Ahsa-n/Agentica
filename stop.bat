@echo off
title Agentica Stop
color 0C

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

:: Close the titled windows
taskkill /FI "WINDOWTITLE eq Agentica Backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Agentica UI" /F >nul 2>&1

echo  Done. All servers stopped.
echo.
pause
