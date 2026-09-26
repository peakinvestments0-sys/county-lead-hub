@echo off
title Stop Florida Lead Hub
echo ========================================================
echo  Stopping Florida Lead Hub (Port 8505)...
echo ========================================================
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8505 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo Florida Lead Hub stopped successfully.
timeout /t 2 >nul
