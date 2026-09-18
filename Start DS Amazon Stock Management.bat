@echo off
cd /d "%~dp0"
start "DS Amazon Stock Management - Server" cmd /k python app.py
timeout /t 3 /nobreak >nul
start "" http://localhost:5000
