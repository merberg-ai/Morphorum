@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" -Lan
exit /b %ERRORLEVEL%
