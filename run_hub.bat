@echo off
title Florida Lead Hub
echo ========================================================
echo  Starting Florida Lead Hub - Public Records Platform
echo ========================================================
echo  Checking port 8505...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8505 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 >nul
echo  Launching server at http://localhost:8505...
python server.py
pause
