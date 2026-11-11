@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "STUDIO_DIR=%~dp0"
set "REQUIREMENTS=%STUDIO_DIR%gui\requirements.txt"
set "PYTHON_EXE="

if not exist "%REQUIREMENTS%" (
    echo [AgStudio] Missing dependency file: "%REQUIREMENTS%"
    exit /b 1
)

call "%STUDIO_DIR%shared\runtime_environment.bat"
if errorlevel 1 exit /b 1

if not exist "%VENV_PYTHON%" (
    call :create_venv
    if errorlevel 1 exit /b 1
)

"%VENV_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [AgStudio] Runtime\.venv needs Python 3.10 or newer. Remove it and rerun Windows_Setup.bat.
    exit /b 1
)

echo [AgStudio] Installing desktop dependencies...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check --requirement "%REQUIREMENTS%"
if errorlevel 1 (
    echo [AgStudio] Dependency installation failed.
    exit /b 1
)

"%VENV_PYTHON%" -c "import PySide6; from PySide6.QtWidgets import QApplication; print('[AgStudio] PySide6 ' + PySide6.__version__ + ' ready.')"
if errorlevel 1 (
    echo [AgStudio] PySide6 could not be loaded from the virtual environment.
    exit /b 1
)

rem Retire the old layout only after the replacement environment is ready.
"%VENV_PYTHON%" -c "import sys; sys.path.insert(0, r'%STUDIO_DIR%.'); from arcgrav_language_engine.lint.spelling import _get_checker; assert _get_checker() is not None, 'Hunspell or its packaged dictionary is unavailable'; print('[AgStudio] Hunspell and technical vocabulary ready.')"
if errorlevel 1 (
    echo [AgStudio] Hunspell could not load its native engine or dictionary. Setup is incomplete.
    exit /b 1
)

rem Do not retain the replaced spelling backend in reused environments.
"%VENV_PYTHON%" -m pip uninstall --yes --disable-pip-version-check pyspellchecker
if errorlevel 1 exit /b 1

"%VENV_PYTHON%" "%STUDIO_DIR%shared\runtime_cleanup.py"
if errorlevel 1 (
    echo [AgStudio] Legacy runtime cleanup failed. Close AgStudio and rerun Windows_Setup.bat.
    exit /b 1
)

echo [AgStudio] Setup complete. Run Windows_Run.bat to launch the editor.
exit /b 0

:create_venv
call :resolve_python
if errorlevel 1 (
    echo [AgStudio] Python 3.10 or newer is required.
    exit /b 1
)
echo [AgStudio] Creating "%VENV_DIR%"...
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [AgStudio] Could not create the virtual environment.
    exit /b 1
)
exit /b 0

:resolve_python
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if defined PYTHON_EXE exit /b 0
for /f "delims=" %%I in ('python -c "import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if defined PYTHON_EXE exit /b 0
exit /b 1
