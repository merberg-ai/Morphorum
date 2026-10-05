@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1"
exit /b %ERRORLEVEL%
