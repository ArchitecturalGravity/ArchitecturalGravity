#requires -Version 5.1
<#
.SYNOPSIS
Launch the managed AgMark runtime with Python fault handling.
.DESCRIPTION
Requires AgMark/Runtime/.venv. Crash diagnostics are written only beneath
AgMark/Runtime/diagnostics. No interpreter or output-directory overrides.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$RuntimeRoot = Join-Path $RepositoryRoot "AgMark/Runtime"
$PythonPath = Join-Path $RuntimeRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "The isolated GUI environment is missing. Run AgMark/Windows_Setup.bat."
}

$RuntimeEnvironment = @{
    PYTHONPYCACHEPREFIX = (Join-Path $RuntimeRoot "__pycache__")
    TEMP = (Join-Path $RuntimeRoot "temp")
    TMP = (Join-Path $RuntimeRoot "temp")
    TMPDIR = (Join-Path $RuntimeRoot "temp")
    PIP_CACHE_DIR = (Join-Path $RuntimeRoot "pip-cache")
}
$PreviousEnvironment = @{}
$GuiExitCode = 1
Push-Location -LiteralPath $RepositoryRoot
try {
    foreach ($Name in $RuntimeEnvironment.Keys) {
        $PreviousEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
        [Environment]::SetEnvironmentVariable($Name, $RuntimeEnvironment[$Name], "Process")
    }
    # Fail before creating logs or starting Qt if the hook/layout is invalid.
    $Admission = @'
from pathlib import Path
from AgMark.gui.runtime_environment import plain_directory, require_managed_runtime
root = Path.cwd() / 'AgMark'
require_managed_runtime(root)
plain_directory(root / 'Runtime' / 'diagnostics')
'@
    & $PythonPath -c $Admission
    if ($LASTEXITCODE -ne 0) {
        throw "AgMark Runtime validation failed. Run AgMark/Windows_Setup.bat."
    }
    $OutputRoot = Join-Path $RuntimeRoot "diagnostics"
    $RunDirectory = Join-Path $OutputRoot ("agmark-crash-{0}-{1}" -f [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"), [Guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path $RunDirectory -Force | Out-Null
    $CrashLog = Join-Path $RunDirectory "agmark-crash.log"
    $ExitCodePath = Join-Path $RunDirectory "exit-code.txt"
    $RuntimePath = Join-Path $RunDirectory "runtime-info.txt"
    Write-Host "Python: $PythonPath"
    Write-Host "Crash log: $CrashLog"
    Write-Host "Reproduce the crash, or close AgMark normally to finish capture."

    $VersionProbe = @'
import platform, sys, PySide6
from PySide6.QtCore import qVersion
print('Python: ' + sys.version.replace('\n', ' '))
print('Executable: ' + sys.executable)
print('Platform: ' + platform.platform())
print('PySide6: ' + PySide6.__version__)
print('Qt: ' + qVersion())
'@
    # Retain native stderr without treating logged crash output as a PS error.
    $ErrorActionPreference = "Continue"
    $PSNativeCommandUseErrorActionPreference = $false
    "PowerShell: $($PSVersionTable.PSVersion)" | Out-File -LiteralPath $RuntimePath -Encoding utf8
    & $PythonPath -u -c $VersionProbe *>> $RuntimePath
    $GuiExitCode = $LASTEXITCODE
    if ($GuiExitCode -eq 0) {
        & $PythonPath -X faulthandler -u -m AgMark.gui *> $CrashLog
        $GuiExitCode = $LASTEXITCODE
    }
    [System.IO.File]::WriteAllText($ExitCodePath, "$GuiExitCode`r`n")
    Write-Host "AgMark exited with code $GuiExitCode. Diagnostics: $RunDirectory"
} finally {
    foreach ($Name in $PreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousEnvironment[$Name], "Process")
    }
    Pop-Location
}
exit $GuiExitCode
