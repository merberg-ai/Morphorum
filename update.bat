@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update_windows.ps1"
exit /b %ERRORLEVEL%
