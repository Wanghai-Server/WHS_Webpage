@echo off
chcp 65001 >nul
title WHS Webpage Launcher

echo ============================================
echo   WHS Webpage - Starting Services
echo ============================================
echo.

:: ========== Backend ==========
echo [1/2] Starting Backend (FastAPI)...
start "WHS-Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate.bat && echo Backend venv activated. && call uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

:: ========== Frontend ==========
echo [2/2] Starting Frontend (Vite)...
start "WHS-Frontend" cmd /k "cd /d "%~dp0whs" && echo Installing dependencies... && call npm install && echo Starting Vite dev server... && call npm run dev -- --host 0.0.0.0"

echo.
echo ============================================
echo   All services started!
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://localhost:5173
echo ============================================
echo.
echo You can close this window. The services are running in their own windows.
pause
