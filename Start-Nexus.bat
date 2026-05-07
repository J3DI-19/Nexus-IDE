@echo off
title Nexus IDE Launcher

echo =====================================
echo        Starting Nexus IDE
echo =====================================

REM --- Kill existing processes ---
echo Cleaning old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173') do taskkill /PID %%a /F >nul 2>&1

REM --- Start Backend ---
echo Starting Backend (FastAPI)...
cd backend
start "Nexus Backend" cmd /k "uvicorn main:app --reload --host 127.0.0.1 --port 8000"

REM --- Start Frontend ---
echo Starting Frontend (Vite)...
cd ../frontend
start "Nexus Frontend" cmd /k "npm run dev"

REM --- Wait ---
echo Waiting for servers to start...
timeout /t 5 > nul

REM --- Open Browser ---
start http://localhost:5173

echo =====================================
echo Nexus IDE is running.
echo =====================================

pause