@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Translate GNU-style launch options to Windows PowerShell script switches.
set "MORPH_ARGS="
:parse
if "%~1"=="" goto launch
if /I "%~1"=="--backend-only" (
    set "MORPH_ARGS=!MORPH_ARGS! -BackendOnly"
    shift
    goto parse
)
if /I "%~1"=="--lan" (
    set "MORPH_ARGS=!MORPH_ARGS! -Lan"
    shift
    goto parse
)
if /I "%~1"=="--port" (
    set "MORPH_ARGS=!MORPH_ARGS! -Port"
    shift
    goto parse
)
set "MORPH_ARGS=!MORPH_ARGS! %1"
shift
goto parse
:launch
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" !MORPH_ARGS!
exit /b %ERRORLEVEL%
