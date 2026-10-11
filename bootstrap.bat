@echo off
setlocal EnableExtensions
title Morphorum - Windows Bootstrap

rem One-file Windows installer entry point. In a checkout it uses the local
rem bootstrap; as a downloaded standalone .bat it fetches the current script.
set "MORPHORUM_BOOTSTRAP_SCRIPT=%~dp0scripts\bootstrap.ps1"
set "MORPHORUM_BOOTSTRAP_TEMP="
if not defined MORPHORUM_BOOTSTRAP_REF set "MORPHORUM_BOOTSTRAP_REF=main"

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell is required to install Morphorum.
  exit /b 1
)

if not exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" (
  set "MORPHORUM_BOOTSTRAP_TEMP=%TEMP%\morphorum-bootstrap-%RANDOM%-%RANDOM%.ps1"
  set "MORPHORUM_BOOTSTRAP_SCRIPT=%MORPHORUM_BOOTSTRAP_TEMP%"
  echo.
  echo [Morphorum] Fetching the Windows installer from GitHub...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri ('https://raw.githubusercontent.com/merberg-ai/Morphorum/' + $env:MORPHORUM_BOOTSTRAP_REF + '/scripts/bootstrap.ps1') -OutFile $env:MORPHORUM_BOOTSTRAP_SCRIPT"
  if errorlevel 1 (
    echo [ERROR] Unable to download the installer. Check your network connection.
    if exist "%MORPHORUM_BOOTSTRAP_SCRIPT%" del /q "%MORPHORUM_BOOTSTRAP_SCRIPT%" >nul 2>&1
    exit /b 1
  )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%MORPHORUM_BOOTSTRAP_SCRIPT%" %*
set "MORPHORUM_BOOTSTRAP_EXIT=%ERRORLEVEL%"
if defined MORPHORUM_BOOTSTRAP_TEMP (
  del /q "%MORPHORUM_BOOTSTRAP_TEMP%" >nul 2>&1
)
exit /b %MORPHORUM_BOOTSTRAP_EXIT%
