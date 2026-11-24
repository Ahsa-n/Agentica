# Agentica startup script — starts PostgreSQL, then backend, then UI
#
# Usage: .\start.ps1
# Prerequisites:
#   - Docker Desktop running (for PostgreSQL)
#   - D:\Temp\venv virtualenv with packages installed
#   - Ollama running (ollama serve)

$root = $PSScriptRoot
$venv = "D:\Temp\venv\Scripts"

Write-Host "=== Agentica Startup ===" -ForegroundColor Cyan

# 1. Start PostgreSQL
Write-Host "Starting PostgreSQL..." -ForegroundColor Yellow
docker compose -f "$root\infra\docker-compose.dev.yml" up -d postgres
Start-Sleep -Seconds 3

# 2. Run migrations
Write-Host "Running migrations..." -ForegroundColor Yellow
$env:TEMP = "D:\Temp\tmp"; $env:TMP = "D:\Temp\tmp"
& "$venv\python.exe" -m alembic -c "$root\backend\alembic.ini" upgrade head

# 3. Start backend (background)
Write-Host "Starting backend..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "$venv\python.exe" `
    -ArgumentList "$root\backend\run.py", "--host", "127.0.0.1", "--port", "8765" `
    -WorkingDirectory "$root\backend" `
    -PassThru -WindowStyle Minimized
Write-Host "Backend PID: $($backend.Id)"

# 4. Start UI dev server
Write-Host "Starting UI..." -ForegroundColor Yellow
$ui = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "$root\ui" `
    -PassThru -WindowStyle Minimized
Write-Host "UI PID: $($ui.Id)"

Write-Host ""
Write-Host "=== Agentica is starting ===" -ForegroundColor Green
Write-Host "Backend: http://127.0.0.1:8765"
Write-Host "UI:      http://localhost:5173"
Write-Host ""
Write-Host "Press Ctrl+C to stop all processes"

# Wait and cleanup
try {
    Wait-Process -Id $backend.Id
} finally {
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $ui.Id -ErrorAction SilentlyContinue
}
