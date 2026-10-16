@echo off
rem Double-click to install dependencies, run the checks and write logs to _logs\.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
echo.
echo Setup finished. See _logs\setup.txt
pause
