@echo off
setlocal EnableExtensions
title Morphorum - Windows Bootstrap

rem One-file Windows entry point. In a checkout, use the local bootstrap.
rem When downloaded on its own, fetch the matching PowerShell bootstrap first.
rem Keep the fetch in a subroutine: CMD expands %%variables%% before executing
rem parenthesized blocks, which previously produced an empty -File argument.
set "MORPHORUM_BOOTSTRAP_SCRIPT=%~dp0scripts\bootstrap.ps1"
set "MORPHORUM_BOOTSTRAP_TEMP="
if not defined MORPHORUM_BOOTSTRAP_REF set "MORPHORUM_BOOTSTRAP_REF=main"

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell is required to install Morphorum.
  exit /b 1
)

if not exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" call :fetch_bootstrap
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%MORPHORUM_BOOTSTRAP_SCRIPT%" %*
set "MORPHORUM_BOOTSTRAP_EXIT=%ERRORLEVEL%"

if defined MORPHORUM_BOOTSTRAP_TEMP del /q "%MORPHORUM_BOOTSTRAP_TEMP%" >nul 2>&1
exit /b %MORPHORUM_BOOTSTRAP_EXIT%

:fetch_bootstrap
set "MORPHORUM_BOOTSTRAP_TEMP=%TEMP%\morphorum-bootstrap-%RANDOM%-%RANDOM%.ps1"
set "MORPHORUM_BOOTSTRAP_SCRIPT=%MORPHORUM_BOOTSTRAP_TEMP%"

echo.
echo [Morphorum] Downloading the Windows setup script...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri ('https://raw.githubusercontent.com/merberg-ai/Morphorum/' + $env:MORPHORUM_BOOTSTRAP_REF + '/scripts/bootstrap.ps1') -OutFile $env:MORPHORUM_BOOTSTRAP_SCRIPT | Out-Null"
if errorlevel 1 (
  echo [ERROR] The setup script could not be downloaded. Check your network or branch name.
  if exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" del /q "%MORPHORUM_BOOTSTRAP_SCRIPT%" >nul 2>&1
  exit /b 1
)
if not exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" (
  echo [ERROR] The download reported success but the setup script was not found.
  exit /b 1
)
for %%F in ("%MORPHORUM_BOOTSTRAP_SCRIPT%") do if %%~zF LSS 100 (
  echo [ERROR] The downloaded setup script is empty or incomplete.
  del /q "%MORPHORUM_BOOTSTRAP_SCRIPT%" >nul 2>&1
  exit /b 1
)
exit /b 0
