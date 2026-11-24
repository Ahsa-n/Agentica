@echo off
:: Started by start.bat (normally elevated, so Windows services can be started/stopped).
title Agentica Backend
cd /d D:\Temp\Agentica\backend
set HF_HOME=D:\Temp\hf-cache
set SENTENCE_TRANSFORMERS_HOME=D:\Temp\hf-cache\sentence-transformers
set TRANSFORMERS_CACHE=D:\Temp\hf-cache\transformers
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

net session >nul 2>&1
if errorlevel 1 (
    echo  Running WITHOUT Administrator rights: starting/stopping Windows services will be refused.
) else (
    echo  Running as Administrator: Windows service start/stop/restart enabled.
)
echo.
D:\Temp\venv\Scripts\python.exe run.py
echo.
echo  Backend stopped. Press a key to close this window.
pause >nul
