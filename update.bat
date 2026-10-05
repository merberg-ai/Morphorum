@echo off
setlocal
echo [Morphorum] Updating repository...
git -C "%~dp0" pull --ff-only
if errorlevel 1 exit /b %ERRORLEVEL%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1" -Update
exit /b %ERRORLEVEL%
