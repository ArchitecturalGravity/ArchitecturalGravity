@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "VENV_PYTHON=%SCRIPT_DIR%Runtime\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo.
    echo [AgMark GUI] STARTUP FAILED
    echo [AgMark GUI] The isolated GUI environment is missing.
    echo [AgMark GUI] Run AgMark\Windows_Setup.bat, then launch again.
    exit /b 1
)

set "PYTHONPYCACHEPREFIX=%SCRIPT_DIR%Runtime\__pycache__"
set "TEMP=%SCRIPT_DIR%Runtime\temp"
set "TMP=%TEMP%"
set "TMPDIR=%TEMP%"
set "PIP_CACHE_DIR=%SCRIPT_DIR%Runtime\pip-cache"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [AgMark GUI] STARTUP FAILED
    echo [AgMark GUI] Unable to enter the repository root: "%REPO_ROOT%"
    echo [AgMark GUI] Check that the checkout is readable and launch again.
    exit /b 1
)

"%VENV_PYTHON%" -m AgMark.gui
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [AgMark GUI] GUI exited with code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
