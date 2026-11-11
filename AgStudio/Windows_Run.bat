@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "STUDIO_DIR=%~dp0"
call "%STUDIO_DIR%shared\runtime_environment.bat"
if errorlevel 1 exit /b 1

if not exist "%VENV_PYTHON%" (
    echo [AgStudio] Runtime\.venv is missing. Run Windows_Setup.bat first.
    exit /b 1
)

for %%I in ("%STUDIO_DIR%..") do set "REPO_ROOT=%%~fI"
set "PYTHONPATH=%REPO_ROOT%;%PYTHONPATH%"

"%VENV_PYTHON%" -m AgStudio.gui --arcgrav-version current %*
exit /b %ERRORLEVEL%
