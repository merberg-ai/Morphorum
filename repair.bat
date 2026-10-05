@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair_windows.ps1"
exit /b %ERRORLEVEL%
