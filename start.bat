@echo off
title Agentica Launcher
color 0A
setlocal

set "ROOT=D:\Temp\Agentica"
set "PY=D:\Temp\venv\Scripts\python.exe"
set "COMPOSE=%ROOT%\infra\docker-compose.dev.yml"
set "DOCKER_DESKTOP=D:\Docker\Docker Desktop.exe"
set "OLLAMA_APP=%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"

echo.
echo  =========================================
echo   Agentica - IT Operations Agent
echo  =========================================
echo.

:: -- 1. Docker + PostgreSQL ------------------------------------------
echo [1/5] Checking Docker...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo       Docker is not running - starting Docker Desktop...
start "" "%DOCKER_DESKTOP%"
set /a tries=0
:wait_docker
timeout /t 3 /nobreak >nul
set /a tries+=1
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
if %tries% GEQ 60 (
    echo       ERROR: Docker did not start within 3 minutes. Start Docker Desktop and re-run.
    pause
    exit /b 1
)
goto wait_docker
:docker_ok
echo       Docker is running.

echo [2/5] Starting PostgreSQL (agentica-postgres)...
docker compose -f "%COMPOSE%" up -d postgres >nul 2>&1
set /a tries=0
:wait_pg
docker exec agentica-postgres pg_isready -U agentica -d agentica >nul 2>&1
if not errorlevel 1 goto pg_ok
set /a tries+=1
if %tries% GEQ 40 (
    echo       ERROR: PostgreSQL did not become ready. Check: docker logs agentica-postgres
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_pg
:pg_ok
echo       PostgreSQL is ready. Applying migrations...
pushd "%ROOT%\backend"
%PY% -m alembic -c alembic.ini upgrade head >nul 2>&1
if errorlevel 1 echo       WARNING: migrations failed - run start.bat from a console to see why.
popd

:: -- 2. Ollama -------------------------------------------------------
echo [3/5] Checking Ollama...
curl -s -o nul http://127.0.0.1:11434/api/tags
if not errorlevel 1 goto ollama_ok
echo       Starting Ollama...
start "" "%OLLAMA_APP%"
set /a tries=0
:wait_ollama
timeout /t 2 /nobreak >nul
set /a tries+=1
curl -s -o nul http://127.0.0.1:11434/api/tags
if not errorlevel 1 goto ollama_ok
if %tries% GEQ 30 (
    echo       WARNING: Ollama is not answering on port 11434 - chat will fail until it runs.
    goto ollama_done
)
goto wait_ollama
:ollama_ok
echo       Ollama is running.
:ollama_done

:: -- 3. Backend ------------------------------------------------------
echo [4/5] Starting Backend (port 8765)...
curl -s http://127.0.0.1:8765/api/health | find "ok" >nul 2>&1
if not errorlevel 1 (
    echo       Backend already running.
    goto backend_up
)
:: Administrator rights let the agent start/stop/restart Windows services (UAC prompt).
:: If the prompt is declined, the backend still starts, without service control.
echo       Approve the Windows UAC prompt so Windows services can be started/stopped...
powershell -NoProfile -Command "try { Start-Process -FilePath '%ROOT%\run_backend.bat' -Verb RunAs -ErrorAction Stop } catch { Write-Host '      UAC declined - starting without Administrator rights.'; Start-Process -FilePath '%ROOT%\run_backend.bat' }"
echo       Waiting for backend...
set /a tries=0
:wait_backend
timeout /t 2 /nobreak >nul
set /a tries+=1
curl -s http://127.0.0.1:8765/api/health | find "ok" >nul 2>&1
if not errorlevel 1 goto backend_up
if %tries% GEQ 60 (
    echo       ERROR: backend did not start - see the "Agentica Backend" window.
    pause
    exit /b 1
)
goto wait_backend
:backend_up
echo       Backend is up.

:: -- 4. UI -----------------------------------------------------------
echo [5/5] Starting UI (port 5173)...
netstat -ano | find ":5173" | find "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo       UI already running.
) else (
    start "Agentica UI" /D "%ROOT%\ui" cmd /k "node_modules\.bin\vite.cmd"
    timeout /t 4 /nobreak >nul
)

echo.
echo  =========================================
echo   Opening http://localhost:5173
echo  =========================================
echo.
start "" "http://localhost:5173"

echo  Backend and UI run in their own windows. Use stop.bat to stop them.
echo  You can close this window.
echo.
timeout /t 10 >nul
endlocal
