@echo off
setlocal enabledelayedexpansion

REM Remote Demo Launcher for ZebraID / STRIPEFORGE
REM Exposes ONLY the Vite frontend (port 5173) via ngrok; FastAPI stays private on 127.0.0.1:8000.

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "BACKEND_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

echo ============================================================
echo   ZebraID / STRIPEFORGE Remote Demo Launcher (ngrok)
echo ============================================================
echo.

REM 1. Check ngrok installation
where ngrok >nul 2>nul
if errorlevel 1 (
    echo [ERROR] ngrok is not installed or not in PATH.
    echo Install ngrok:
    echo   winget install ngrok.ngrok
    echo Or download from https://ngrok.com/download
    echo Then configure your authtoken once:
    echo   ngrok config add-authtoken ^<YOUR_NGROK_TOKEN^>
    exit /b 1
)

REM 2. Check backend virtual environment
if not exist "%BACKEND_PY%" (
    echo [ERROR] Backend virtual environment not found at:
    echo   %BACKEND_PY%
    echo Create it and install dependencies before running this script.
    exit /b 1
)

if not exist "%BACKEND_DIR%\.env" (
    echo [ERROR] Missing %BACKEND_DIR%\.env
    echo Copy backend\.env.example to backend\.env and fill in credentials.
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [ERROR] Missing %FRONTEND_DIR%\node_modules
    echo Run "npm install" inside %FRONTEND_DIR% first.
    exit /b 1
)

REM 3. Start private FastAPI backend on 127.0.0.1:8000
echo [1/3] Starting private FastAPI backend on 127.0.0.1:8000...
start "ZebraID Backend (127.0.0.1:8000)" cmd /k "cd /d "%BACKEND_DIR%" && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"

REM 4. Start Vite frontend on 0.0.0.0:5173 (proxies /api -> 127.0.0.1:8000)
echo [2/3] Starting Vite frontend on 0.0.0.0:5173...
start "ZebraID Frontend (0.0.0.0:5173)" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev -- --host 0.0.0.0 --port 5173"

echo Waiting 4 seconds for servers to initialize...
timeout /t 4 /nobreak >nul

REM 5. Start ngrok tunnel for port 5173
echo [3/3] Starting ngrok HTTPS tunnel for port 5173...
start "ZebraID ngrok Tunnel (port 5173)" cmd /k "ngrok http 5173"

echo.
echo Waiting for ngrok local API (http://127.0.0.1:4040/api/tunnels) to report the public HTTPS URL...
timeout /t 4 /nobreak >nul

powershell -NoProfile -Command "try { $t = (Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 5).tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1; if ($t) { Write-Host ('[PUBLIC DEMO URL] ' + $t.public_url) -ForegroundColor Green } else { Write-Host '[INFO] ngrok is starting; check the ngrok window or http://127.0.0.1:4040 for the HTTPS URL.' -ForegroundColor Yellow } } catch { Write-Host '[INFO] Check the ngrok terminal window or http://127.0.0.1:4040 for your public HTTPS URL.' -ForegroundColor Yellow }"

echo.
echo IMPORTANT SECURITY REMINDERS:
echo - This URL is publicly reachable. Share it only with your professor for this demo.
echo - Close the ngrok window immediately after the demonstration ends.
echo - FastAPI (port 8000), PostgreSQL, and .env secrets remain private on localhost.
echo.
endlocal
