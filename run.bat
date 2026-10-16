@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Preserve legacy command-line forwarding for normal Morphorum runs.
if /I "%~1"=="--backend-only" goto backend_only
if /I "%~1"=="--setup-wizard" goto setup_wizard
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" %*
exit /b %ERRORLEVEL%

:backend_only
rem Translate explicit GNU-style backend-only launch options into PowerShell.
set "MORPH_ARGS=-BackendOnly"
shift
:parse
if "%~1"=="" goto launch
if /I "%~1"=="--setup-wizard" (
    set "MORPH_ARGS=!MORPH_ARGS! -SetupWizard"
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

:setup_wizard
rem GNU-style first-run option for Windows CMD wrapper.
set "MORPH_ARGS=-SetupWizard"
shift
:setup_parse
if "%~1"=="" goto setup_launch
set "MORPH_ARGS=!MORPH_ARGS! %1"
shift
goto setup_parse
:setup_launch
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1" !MORPH_ARGS!
exit /b %ERRORLEVEL%
