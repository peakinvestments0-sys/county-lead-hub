@echo off
title Stop Florida Lead Hub
echo ========================================================
echo  Stopping Florida Lead Hub (Port 8505)...
echo ========================================================
powershell.exe -NoProfile -Command "Stop-ScheduledTask -TaskName 'Florida Lead Hub' -ErrorAction SilentlyContinue"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8505 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo Florida Lead Hub stopped successfully.
timeout /t 2 >nul
