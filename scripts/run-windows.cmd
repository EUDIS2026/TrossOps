@echo off
rem Double-click to start the API and UI, run the browser acceptance script, and push to GitHub.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-windows.ps1" -Verify -Push
echo.
echo Run finished. See _logs\run.txt, _logs\verify.txt and _logs\push.txt
pause
