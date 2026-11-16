@echo off
title Community Hall Management System

cd /d "%~dp0"

echo ========================================
echo   COMMUNITY HALL MANAGEMENT SYSTEM
echo ========================================

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    py -m venv .venv

    if errorlevel 1 (
        echo Failed to create Python environment.
        pause
        exit /b 1
    )

    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt

    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

set ADMIN_USERNAME=admin
set ADMIN_PASSWORD=HallAdmin@2026
set SECRET_KEY=college-demo-secret-key

echo.
echo Starting Community Hall website...
echo Open http://127.0.0.1:5000 in your browser.
echo.

".venv\Scripts\python.exe" app.py

pause
