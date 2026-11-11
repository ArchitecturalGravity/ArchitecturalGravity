#requires -Version 5.1
<#
.SYNOPSIS
Verifies the production AgMark desktop bootstrap and launch surfaces on Windows.

.DESCRIPTION
This testing-owned harness runs the production setup, probes the module and batch
launch surfaces for the AgMark desktop window, validates visible
missing-environment failures, and writes machine-readable execution evidence.
It does not create benchmark evidence or production authority.
#>

[CmdletBinding()]
param(
    [ValidateRange(5, 120)]
    [int]$StartupTimeoutSeconds = 30,

    [string]$EvidencePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Supported-Windows operability verification must run on Windows."
}

$HarnessRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = (Resolve-Path (Join-Path $HarnessRoot "..\..\..\..\..")).Path
$GuiRoot = Join-Path $RepositoryRoot "AgMark\gui"
$AgMarkRoot = Split-Path -Parent $GuiRoot
$RuntimeRoot = Join-Path $AgMarkRoot "Runtime"
$SetupBat = Join-Path $AgMarkRoot "Windows_Setup.bat"
$RunBat = Join-Path $AgMarkRoot "Windows_Run.bat"
$SetupHelper = Join-Path $GuiRoot "setup_environment.py"
$RuntimeHelper = Join-Path $GuiRoot "runtime_environment.py"
$Requirements = Join-Path $GuiRoot "requirements.txt"
$VenvRoot = Join-Path $RuntimeRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$ApplicationTitle = "AgMark"

if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
    $EvidencePath = Join-Path $RuntimeRoot "diagnostics\windows_operability_evidence.json"
} elseif (-not [System.IO.Path]::IsPathRooted($EvidencePath)) {
    $EvidencePath = Join-Path (Get-Location) $EvidencePath
}

$Checks = New-Object System.Collections.Generic.List[object]
$Failure = $null
$RuntimeInfo = $null

function Add-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Details
    )

    $Checks.Add([pscustomobject]@{
        name = $Name
        passed = $true
        details = $Details
    }) | Out-Null
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $ProbeProcess = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $ProbeProcess) { return }
    # Native stderr can become a terminating PowerShell error when a child
    # exits during /T enumeration. Check actual target liveness after teardown.
    $StopInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StopInfo.FileName = "taskkill.exe"
    $StopInfo.Arguments = "/PID $ProcessId /T /F"
    $StopInfo.UseShellExecute = $false
    $StopInfo.CreateNoWindow = $true
    $StopInfo.RedirectStandardOutput = $true
    $StopInfo.RedirectStandardError = $true
    $Stopper = [System.Diagnostics.Process]::Start($StopInfo)
    try {
        $Stopper.StandardOutput.ReadToEnd() | Out-Null
        $StopError = $Stopper.StandardError.ReadToEnd()
        $Stopper.WaitForExit()
        if (-not $ProbeProcess.WaitForExit(5000)) {
            throw "Operability probe process $ProcessId remains running: $StopError"
        }
    } finally {
        $Stopper.Dispose()
        $ProbeProcess.Dispose()
    }
}

function Get-WindowProcessIds {
    param([Parameter(Mandatory = $true)][string]$Title)

    return @(
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -eq $Title } |
            ForEach-Object { $_.Id }
    )
}

function Wait-NewWindowProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [int[]]$BaselineProcessIds = @(),
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $Deadline) {
        $Candidate = Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.MainWindowTitle -eq $Title -and
                $_.Id -notin $BaselineProcessIds
            } |
            Select-Object -First 1
        if ($null -ne $Candidate) {
            return $Candidate
        }
        Start-Sleep -Milliseconds 250
    }

    throw "Timed out waiting for visible window '$Title'."
}

function Invoke-LaunchProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    $Baseline = Get-WindowProcessIds -Title $ApplicationTitle
    $StartArgs = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        WorkingDirectory = $RepositoryRoot
        PassThru = $true
    }
    $Started = Start-Process @StartArgs
    $WindowProcess = $null

    try {
        $WindowProcess = Wait-NewWindowProcess -Title $ApplicationTitle -BaselineProcessIds $Baseline -TimeoutSeconds $StartupTimeoutSeconds
        Add-Check -Name $Name -Details ("Visible production window reached through {0}; window process id {1}." -f $Name, $WindowProcess.Id)
    } finally {
        if ($null -ne $WindowProcess) {
            Stop-ProcessTree -ProcessId $WindowProcess.Id
        }
        if ($null -ne $Started) {
            try {
                if (-not $Started.HasExited) {
                    Stop-ProcessTree -ProcessId $Started.Id
                }
            } catch {
                # The process may already have exited after its GUI child is terminated.
            }
        }
    }
}

try {
    foreach ($RequiredPath in @($SetupBat, $SetupHelper, $RuntimeHelper, $RunBat, $Requirements)) {
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "Required production surface is missing: $RequiredPath"
        }
    }

    Push-Location $RepositoryRoot
    try {
        & cmd.exe /d /s /c "`"$SetupBat`""
        if ($LASTEXITCODE -ne 0) {
            throw "Windows_Setup.bat failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }

    foreach ($RequiredRuntime in @($VenvPython)) {
        if (-not (Test-Path -LiteralPath $RequiredRuntime -PathType Leaf)) {
            throw "Windows_Setup.bat did not create the required runtime: $RequiredRuntime"
        }
    }

    $RuntimeInfoJson = & $VenvPython -c "import json, platform, PySide6; print(json.dumps({'python': platform.python_version(), 'pyside6': PySide6.__version__}))"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query the isolated GUI runtime after setup."
    }
    $RuntimeInfo = $RuntimeInfoJson | ConvertFrom-Json
    Add-Check -Name "Windows_Setup.bat" -Details ("Isolated GUI runtime ready with Python {0} and PySide6 {1}." -f $RuntimeInfo.python, $RuntimeInfo.pyside6)

    Invoke-LaunchProbe -Name "python -m AgMark.gui" -FilePath $VenvPython -ArgumentList @("-m", "AgMark.gui")
    Invoke-LaunchProbe -Name "Windows_Run.bat" -FilePath "cmd.exe" -ArgumentList @("/d", "/s", "/c", "`"$RunBat`"")

    $HiddenVenv = Join-Path $RuntimeRoot (".venv.operability-probe-{0}" -f [Guid]::NewGuid().ToString("N"))
    Move-Item -LiteralPath $VenvRoot -Destination $HiddenVenv
    try {
        $BatchFailureOutput = (& cmd.exe /d /s /c "`"$RunBat`"" 2>&1 | Out-String)
        $BatchFailureCode = $LASTEXITCODE
        if ($BatchFailureCode -eq 0 -or $BatchFailureOutput -notmatch "isolated GUI environment is missing") {
            throw "Windows_Run.bat did not emit the required visible missing-environment failure."
        }
        Add-Check -Name "Windows_Run.bat missing-environment failure" -Details ("Console launcher failed visibly and actionably with exit code {0}." -f $BatchFailureCode)
    } finally {
        if (Test-Path -LiteralPath $HiddenVenv) {
            if (Test-Path -LiteralPath $VenvRoot) {
                throw "Cannot restore the isolated GUI environment because $VenvRoot already exists."
            }
            Move-Item -LiteralPath $HiddenVenv -Destination $VenvRoot
        }
    }
} catch {
    $Failure = $_.Exception.Message
} finally {
    $SourceHashes = [ordered]@{}
    foreach ($SourcePath in @($Requirements, $SetupHelper, $RuntimeHelper, $SetupBat, $RunBat, (Join-Path $GuiRoot "startup.py"), (Join-Path $GuiRoot "__main__.py"))) {
        if (Test-Path -LiteralPath $SourcePath -PathType Leaf) {
            $RelativePath = $SourcePath.Substring($RepositoryRoot.Length).TrimStart("\")
            $SourceHashes[$RelativePath] = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourcePath).Hash.ToLowerInvariant()
        }
    }

    $PythonVersion = $null
    $PySideVersion = $null
    if ($null -ne $RuntimeInfo) {
        $PythonVersion = $RuntimeInfo.python
        $PySideVersion = $RuntimeInfo.pyside6
    }

    $Evidence = [ordered]@{
        schema = "arcgrav.frontend.windows-operability/v1"
        generated_at_utc = [DateTime]::UtcNow.ToString("o")
        repository_root = $RepositoryRoot
        windows_version = [System.Environment]::OSVersion.VersionString
        powershell_version = $PSVersionTable.PSVersion.ToString()
        python_version = $PythonVersion
        pyside6_version = $PySideVersion
        source_sha256 = $SourceHashes
        checks = $Checks.ToArray()
        passed = [string]::IsNullOrEmpty($Failure)
        failure = $Failure
    }

    $EvidenceDirectory = Split-Path -Parent $EvidencePath
    if (-not [string]::IsNullOrWhiteSpace($EvidenceDirectory)) {
        New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
    }
    $EvidenceJson = $Evidence | ConvertTo-Json -Depth 6
    $EvidenceJson = $EvidenceJson.Replace("`r`n", "`n").Replace("`r", "`n")
    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($EvidencePath, $EvidenceJson + "`n", $Utf8NoBom)
}

if (-not [string]::IsNullOrEmpty($Failure)) {
    Write-Host "Supported-Windows operability verification failed: $Failure" -ForegroundColor Red
    Write-Host "Evidence: $EvidencePath"
    exit 1
}

Write-Host "Supported-Windows operability verification passed."
Write-Host "Evidence: $EvidencePath"
exit 0
