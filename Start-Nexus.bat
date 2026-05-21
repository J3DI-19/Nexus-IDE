@echo off
title Nexus IDE Launcher
setlocal

set "ROOT_DIR=%~dp0"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "BACKEND_DIR=%ROOT_DIR%backend"

echo =====================================
echo        Starting Nexus IDE
echo =====================================

REM --- Kill existing processes ---
echo Cleaning old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173') do taskkill /PID %%a /F >nul 2>&1

REM --- Start Backend ---
echo Starting Backend (FastAPI)...
start "Nexus Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"

REM --- Start Frontend ---
echo Starting Frontend (Vite)...
if exist "%FRONTEND_DIR%\node_modules\.bin\vite.cmd" (
    start "Nexus Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"
) else (
    start "Nexus Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && echo Installing frontend dependencies... && npm install && npm run dev"
)

REM --- Wait ---
echo Waiting for servers to start...
timeout /t 5 > nul

REM --- Open Browser ---
start http://localhost:5173

echo =====================================
echo Nexus IDE is running.
echo =====================================

pause
