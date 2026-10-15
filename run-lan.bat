@echo off
setlocal EnableExtensions
if /I "%~1"=="--setup-wizard" goto setup_wizard
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" -Lan %*
exit /b %ERRORLEVEL%

:setup_wizard
shift
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" -Lan -SetupWizard %*
exit /b %ERRORLEVEL%
