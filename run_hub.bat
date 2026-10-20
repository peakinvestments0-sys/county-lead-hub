@echo off
title Florida Lead Hub
echo ========================================================
echo  Starting Florida Lead Hub - Public Records Platform
echo ========================================================
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_lead_hub.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
start "" "http://localhost:8505"
