@echo off
rem Called inside Windows_Setup.bat/Windows_Run.bat's SETLOCAL, before starting any Python.
rem Keep this source file outside the disposable Runtime directory.
if not defined STUDIO_DIR (
    echo [AgStudio] STUDIO_DIR must identify the AgStudio folder.
    exit /b 1
)
set "RUNTIME_DIR=%STUDIO_DIR%Runtime"
set "VENV_DIR=%RUNTIME_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PYTHONPYCACHEPREFIX=%RUNTIME_DIR%\__pycache__"
set "PIP_CACHE_DIR=%RUNTIME_DIR%\.cache\pip"
set "TEMP=%RUNTIME_DIR%\.tmp"
set "TMP=%TEMP%"
set "TMPDIR=%TEMP%"

for %%D in ("%RUNTIME_DIR%" "%PYTHONPYCACHEPREFIX%" "%PIP_CACHE_DIR%" "%TEMP%") do (
    if not exist "%%~D\" mkdir "%%~D"
    if not exist "%%~D\" (
        echo [AgStudio] Could not create runtime directory: "%%~D"
        exit /b 1
    )
)
exit /b 0
