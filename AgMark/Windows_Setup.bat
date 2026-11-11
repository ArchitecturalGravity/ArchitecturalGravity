@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE="

rem The Windows Python launcher is the sole bootstrap resolver. No PATH fallback.
for /f "delims=" %%I in ('py -3 -B -c "import sys; ok = sys.version_info.major == 3 and sys.version_info.minor in (10, 11, 12, 13, 14); print(sys.executable) if ok else sys.exit(1)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
    echo.
    echo [AgMark GUI] SETUP FAILED
    echo [AgMark GUI] The Windows Python launcher must select Python 3.10 through 3.14 with py -3.
    echo [AgMark GUI] Install or configure the supported runtime, then rerun Windows_Setup.bat.
    exit /b 1
)

rem Bootstrap without bytecode until the helper validates Runtime paths.
"%PYTHON_EXE%" -B "%SCRIPT_DIR%gui\setup_environment.py"
exit /b %ERRORLEVEL%
