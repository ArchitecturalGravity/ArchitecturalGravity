[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Run this script from the swe_rebench_07_2026_trajectories directory.
# All inputs and the default output are resolved from the current working directory.
$BasePath = [System.IO.Path]::GetFullPath((Get-Location).Path)
$SchemaPath = Join-Path $BasePath 'schema.json'
$TrajectoriesPath = Join-Path $BasePath 'trajectories'
$InputDirectory = Join-Path $TrajectoriesPath 'codex'

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $BasePath 'codex_operational_baseline.csv'
}
elseif ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
}
else {
    $OutputPath = [System.IO.Path]::GetFullPath((Join-Path $BasePath $OutputPath))
}

if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
    throw ('schema.json not found in current directory: {0}' -f $BasePath)
}
if (-not (Test-Path -LiteralPath $TrajectoriesPath -PathType Container)) {
    throw ('trajectories directory not found in current directory: {0}' -f $BasePath)
}
if (-not (Test-Path -LiteralPath $InputDirectory -PathType Container)) {
    throw ('Codex trajectory directory not found: {0}' -f $InputDirectory)
}

try {
    $LocalSchema = Get-Content -LiteralPath $SchemaPath -Raw | ConvertFrom-Json
}
catch {
    throw ('Failed to parse local schema.json: {0}' -f $_.Exception.Message)
}

$RequiredTopLevelFields = @($LocalSchema.required | ForEach-Object { [string]$_ })
$ExpectedSchemaVersion = [string]$LocalSchema.properties.schema_version.const
if ([string]::IsNullOrWhiteSpace($ExpectedSchemaVersion)) {
    throw 'Local schema.json does not define properties.schema_version.const.'
}

$ExpectedEpisodes = 555
$ExpectedInstances = 111
$ExpectedRuns = 0..4
$ExpectedEpisodesPerRun = 111
$KnownEventTypes = @(
    'assistant_message',
    'assistant_analysis',
    'prompt',
    'tool_call',
    'tool_result',
    'file_change',
    'agent_step',
    'final_message'
)

function Get-UnicodeCodePointCount {
    param([AllowNull()][string]$Text)

    if ($null -eq $Text) {
        return $null
    }

    $Count = 0
    for ($i = 0; $i -lt $Text.Length; $i++) {
        if (
            [char]::IsHighSurrogate($Text[$i]) -and
            ($i + 1) -lt $Text.Length -and
            [char]::IsLowSurrogate($Text[$i + 1])
        ) {
            $i++
        }
        $Count++
    }
    return $Count
}

function Add-Count {
    param(
        [hashtable]$Table,
        [string]$Key,
        [int]$Increment = 1
    )

    if ($Table.ContainsKey($Key)) {
        $Table[$Key] += $Increment
    }
    else {
        $Table[$Key] = $Increment
    }
}

function Get-Mean {
    param([object[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }
    return [double](($Values | Measure-Object -Average).Average)
}

function Get-Minimum {
    param([object[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }
    return ($Values | Measure-Object -Minimum).Minimum
}

function Get-Maximum {
    param([object[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }
    return ($Values | Measure-Object -Maximum).Maximum
}

function Format-NullableNumber {
    param(
        $Value,
        [string]$Format = 'N2'
    )

    if ($null -eq $Value) {
        return 'NA'
    }
    return ([double]$Value).ToString($Format, [System.Globalization.CultureInfo]::InvariantCulture)
}

$RunFiles = foreach ($RunIndex in $ExpectedRuns) {
    $Path = Join-Path $InputDirectory ('run_{0}.jsonl' -f $RunIndex)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ('Expected trajectory file not found: {0}' -f $Path)
    }
    $Path
}

if ((Test-Path -LiteralPath $OutputPath -PathType Leaf) -and -not $Force) {
    throw ('Output already exists: {0}. Re-run with -Force to overwrite it.' -f $OutputPath)
}

$Rows = New-Object 'System.Collections.Generic.List[object]'
$TrajectoryIds = New-Object 'System.Collections.Generic.HashSet[string]'
$InstanceCounts = @{}
$InstanceRuns = @{}
$RunCounts = @{}
$PromptRoleStatusCounts = @{}
$ParticipantTuples = New-Object 'System.Collections.Generic.HashSet[string]'
$IntegrityIssues = New-Object 'System.Collections.Generic.List[string]'

foreach ($RunIndex in $ExpectedRuns) {
    $RunCounts[$RunIndex] = 0
}

[long]$DirectToolCalls = 0
[long]$DirectSpecChars = 0
[int]$DirectSpecAvailableEpisodes = 0
[int]$TotalRecords = 0

Write-Host ('Dataset root: {0}' -f $BasePath)
Write-Host ('Schema:       {0} (schema_version={1})' -f $SchemaPath, $ExpectedSchemaVersion)
Write-Host ('Trajectories: {0}' -f $TrajectoriesPath)
Write-Host ('Codex input:  {0}' -f $InputDirectory)

foreach ($RunFile in $RunFiles) {
    $SourceRunFile = [System.IO.Path]::GetFileName($RunFile)
    $ExpectedRunIndex = [int]([System.IO.Path]::GetFileNameWithoutExtension($RunFile) -replace '^run_', '')
    $PhysicalLineNumber = 0
    $SourceRecordIndex = 0

    foreach ($Line in [System.IO.File]::ReadLines($RunFile)) {
        $PhysicalLineNumber++
        if ([string]::IsNullOrWhiteSpace($Line)) {
            continue
        }

        $SourceRecordIndex++
        $TotalRecords++

        try {
            $Record = $Line | ConvertFrom-Json

            $RecordPropertyNames = @($Record.PSObject.Properties.Name)
            foreach ($RequiredField in $RequiredTopLevelFields) {
                if ($RecordPropertyNames -notcontains $RequiredField) {
                    $IntegrityIssues.Add(('{0} record {1} is missing schema-required top-level field ''{2}''.' -f $SourceRunFile, $SourceRecordIndex, $RequiredField))
                }
            }

            if ([string]$Record.schema_version -ne $ExpectedSchemaVersion) {
                $IntegrityIssues.Add(('{0} record {1} has schema_version ''{2}''; expected ''{3}'' from local schema.json.' -f $SourceRunFile, $SourceRecordIndex, $Record.schema_version, $ExpectedSchemaVersion))
            }

            $TrajectoryId = [string]$Record.trajectory_id
            $InstanceId = [string]$Record.instance_id
            $RecordRunIndex = [int]$Record.run.index

            if ([string]::IsNullOrWhiteSpace($TrajectoryId)) {
                $IntegrityIssues.Add(('{0} record {1} has an empty trajectory_id.' -f $SourceRunFile, $SourceRecordIndex))
            }
            elseif (-not $TrajectoryIds.Add($TrajectoryId)) {
                $IntegrityIssues.Add(('Duplicate trajectory_id ''{0}'' at {1} record {2}.' -f $TrajectoryId, $SourceRunFile, $SourceRecordIndex))
            }

            if ([string]::IsNullOrWhiteSpace($InstanceId)) {
                $IntegrityIssues.Add(('{0} record {1} has an empty instance_id.' -f $SourceRunFile, $SourceRecordIndex))
            }
            else {
                if ($InstanceCounts.ContainsKey($InstanceId)) {
                    $InstanceCounts[$InstanceId]++
                }
                else {
                    $InstanceCounts[$InstanceId] = 1
                    $InstanceRuns[$InstanceId] = New-Object 'System.Collections.Generic.HashSet[int]'
                }
                [void]$InstanceRuns[$InstanceId].Add($RecordRunIndex)
            }

            if (-not $RunCounts.ContainsKey($RecordRunIndex)) {
                $RunCounts[$RecordRunIndex] = 0
                $IntegrityIssues.Add(('Unexpected run index {0} at {1} record {2}.' -f $RecordRunIndex, $SourceRunFile, $SourceRecordIndex))
            }
            $RunCounts[$RecordRunIndex]++

            if ($RecordRunIndex -ne $ExpectedRunIndex) {
                $IntegrityIssues.Add(('Run mismatch at {0} record {1}: record.run.index={2}, expected {3}.' -f $SourceRunFile, $SourceRecordIndex, $RecordRunIndex, $ExpectedRunIndex))
            }

            $ParticipantTuple = @(
                [string]$Record.participant.key,
                [string]$Record.participant.type,
                [string]$Record.participant.scaffold,
                [string]$Record.participant.model,
                [string]$Record.participant.reasoning_effort
            ) -join ' | '
            [void]$ParticipantTuples.Add($ParticipantTuple)

            $Prompts = @($Record.prompts)
            $UserPrompts = @($Prompts | Where-Object { $_.role -eq 'user' })
            $ExactTaskPrompts = @($UserPrompts | Where-Object { $_.status -eq 'exact_task_input' })

            foreach ($Prompt in $Prompts) {
                Add-Count -Table $PromptRoleStatusCounts -Key ('{0} | {1}' -f [string]$Prompt.role, [string]$Prompt.status)
            }

            $UserStatusGroups = @($UserPrompts | Group-Object -Property status | Sort-Object -Property Name)
            $SpecificationStatusSummary = ($UserStatusGroups | ForEach-Object { '{0}={1}' -f $_.Name, $_.Count }) -join ';'

            $SpecificationAvailable = $ExactTaskPrompts.Count -gt 0
            [long]$SpecCharsAccumulator = 0
            foreach ($Prompt in $ExactTaskPrompts) {
                if ($null -eq $Prompt.content -or -not ($Prompt.content -is [string])) {
                    $SpecificationAvailable = $false
                    continue
                }
                $SpecCharsAccumulator += Get-UnicodeCodePointCount -Text ([string]$Prompt.content)
            }

            $SpecChars = $null
            if ($SpecificationAvailable) {
                $SpecChars = $SpecCharsAccumulator
                $DirectSpecChars += $SpecCharsAccumulator
                $DirectSpecAvailableEpisodes++
            }

            $EventCounts = @{}
            foreach ($EventType in $KnownEventTypes) {
                $EventCounts[$EventType] = 0
            }

            $Events = @($Record.events)
            foreach ($Event in $Events) {
                $EventType = [string]$Event.type
                if (-not $EventCounts.ContainsKey($EventType)) {
                    $IntegrityIssues.Add(('Unexpected event type ''{0}'' at {1} record {2}.' -f $EventType, $SourceRunFile, $SourceRecordIndex))
                    $EventCounts[$EventType] = 0
                }
                $EventCounts[$EventType]++
            }

            $ToolCalls = [int]$EventCounts['tool_call']
            $DirectToolCalls += $ToolCalls

            $ToolCallsPer1kSpecChars = $null
            $EventsPer1kSpecChars = $null
            if ($SpecificationAvailable -and $SpecCharsAccumulator -gt 0) {
                $ToolCallsPer1kSpecChars = [double]$ToolCalls / ([double]$SpecCharsAccumulator / 1000.0)
                $EventsPer1kSpecChars = [double]$Events.Count / ([double]$SpecCharsAccumulator / 1000.0)
            }

            $InfrastructureRedactions = $Record.normalization.infrastructure_redactions
            $InfrastructureRedactionsJson = $InfrastructureRedactions | ConvertTo-Json -Compress -Depth 20
            $InfrastructureRedactionsPresent = @($InfrastructureRedactions.PSObject.Properties).Count -gt 0

            $Row = [pscustomobject][ordered]@{
                trajectory_id                     = $TrajectoryId
                instance_id                       = $InstanceId
                source_run_file                   = $SourceRunFile
                source_record_index               = $SourceRecordIndex
                source_line_number                = $PhysicalLineNumber
                language                          = [string]$Record.language
                repository                        = $Record.repository
                participant_key                   = [string]$Record.participant.key
                participant_type                  = [string]$Record.participant.type
                scaffold                          = [string]$Record.participant.scaffold
                model                             = [string]$Record.participant.model
                reasoning_effort                  = $Record.participant.reasoning_effort
                run_index                         = $RecordRunIndex
                run_attempt                       = [string]$Record.run.attempt
                retry_number                      = $Record.run.retry_number
                resolved                          = [bool]$Record.evaluation.resolved
                evaluation_status                 = [string]$Record.evaluation.status
                agent_exit_status                 = $Record.evaluation.agent_exit_status
                evaluation_matches_selected       = [bool]$Record.evaluation.evaluation_matches_selected
                prompt_count_total                = $Prompts.Count
                user_prompt_count                 = $UserPrompts.Count
                exact_task_input_count            = $ExactTaskPrompts.Count
                spec_chars                        = $SpecChars
                tool_calls                        = $ToolCalls
                tool_results                      = [int]$EventCounts['tool_result']
                file_changes                      = [int]$EventCounts['file_change']
                agent_steps                       = [int]$EventCounts['agent_step']
                assistant_analysis_events         = [int]$EventCounts['assistant_analysis']
                assistant_message_events          = [int]$EventCounts['assistant_message']
                prompt_events                     = [int]$EventCounts['prompt']
                final_message_events              = [int]$EventCounts['final_message']
                normalized_events_total           = $Events.Count
                tool_calls_per_1k_spec_chars      = $ToolCallsPer1kSpecChars
                events_per_1k_spec_chars          = $EventsPer1kSpecChars
                tool_result_limit_bytes           = [int]$Record.normalization.tool_result_limit_bytes
                truncated_tool_results            = [int]$Record.normalization.truncated_tool_results
                cache_tool_results_omitted        = [int]$Record.normalization.cache_tool_results_omitted
                infrastructure_redactions_present = $InfrastructureRedactionsPresent
                infrastructure_redactions_json    = $InfrastructureRedactionsJson
                specification_available           = $SpecificationAvailable
                specification_status_summary      = $SpecificationStatusSummary
            }

            $Rows.Add($Row)
        }
        catch {
            throw ('Failed to parse/process {0} physical line {1} (record {2}): {3}' -f $SourceRunFile, $PhysicalLineNumber, $SourceRecordIndex, $_.Exception.Message)
        }
    }
}

Write-Host ''
Write-Host 'Prompt role/status audit:'
foreach ($Entry in ($PromptRoleStatusCounts.GetEnumerator() | Sort-Object -Property Name)) {
    Write-Host ('  {0}: {1}' -f $Entry.Name, $Entry.Value)
}

Write-Host ''
Write-Host 'Participant tuples observed:'
foreach ($Tuple in ($ParticipantTuples | Sort-Object)) {
    Write-Host ('  {0}' -f $Tuple)
}

if ($TotalRecords -ne $ExpectedEpisodes) {
    $IntegrityIssues.Add(('Expected {0} records, found {1}.' -f $ExpectedEpisodes, $TotalRecords))
}
if ($TrajectoryIds.Count -ne $ExpectedEpisodes) {
    $IntegrityIssues.Add(('Expected {0} unique trajectory_id values, found {1}.' -f $ExpectedEpisodes, $TrajectoryIds.Count))
}
if ($InstanceCounts.Count -ne $ExpectedInstances) {
    $IntegrityIssues.Add(('Expected {0} unique instance_id values, found {1}.' -f $ExpectedInstances, $InstanceCounts.Count))
}

foreach ($RunIndex in $ExpectedRuns) {
    $Count = if ($RunCounts.ContainsKey($RunIndex)) { [int]$RunCounts[$RunIndex] } else { 0 }
    if ($Count -ne $ExpectedEpisodesPerRun) {
        $IntegrityIssues.Add(('Expected {0} episodes for run {1}, found {2}.' -f $ExpectedEpisodesPerRun, $RunIndex, $Count))
    }
}

foreach ($InstanceId in ($InstanceCounts.Keys | Sort-Object)) {
    if ([int]$InstanceCounts[$InstanceId] -ne $ExpectedRuns.Count) {
        $IntegrityIssues.Add(('instance_id ''{0}'' occurs {1} times; expected {2}.' -f $InstanceId, $InstanceCounts[$InstanceId], $ExpectedRuns.Count))
    }

    $RunsForInstance = $InstanceRuns[$InstanceId]
    if ($RunsForInstance.Count -ne $ExpectedRuns.Count) {
        $ObservedRuns = (@($RunsForInstance) | Sort-Object) -join ','
        $IntegrityIssues.Add(('instance_id ''{0}'' does not appear exactly once in each run; observed run set: {1}.' -f $InstanceId, $ObservedRuns))
    }
    else {
        foreach ($RunIndex in $ExpectedRuns) {
            if (-not $RunsForInstance.Contains([int]$RunIndex)) {
                $IntegrityIssues.Add(('instance_id ''{0}'' is missing run {1}.' -f $InstanceId, $RunIndex))
            }
        }
    }
}

if ($IntegrityIssues.Count -gt 0) {
    Write-Host ''
    Write-Host 'Integrity validation failed:' -ForegroundColor Red
    foreach ($Issue in $IntegrityIssues) {
        Write-Host ('  - {0}' -f $Issue) -ForegroundColor Red
    }
    throw 'Cohort integrity validation failed. CSV was not written.'
}

if ($DirectSpecAvailableEpisodes -ne $ExpectedEpisodes) {
    $Coverage = 100.0 * $DirectSpecAvailableEpisodes / $ExpectedEpisodes
    Write-Warning ('Exact user + exact_task_input specification content is usable for {0}/{1} episodes ({2:N2}%). Rows without usable specification content will have blank spec_chars and normalized ratios.' -f $DirectSpecAvailableEpisodes, $ExpectedEpisodes, $Coverage)
}

$OutputDirectory = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($OutputDirectory) -and -not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    [void](New-Item -ItemType Directory -Path $OutputDirectory -Force)
}

$Rows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding UTF8

$CsvRows = @(Import-Csv -LiteralPath $OutputPath)
if ($CsvRows.Count -ne $ExpectedEpisodes) {
    throw ('CSV validation failed: expected {0} rows, found {1}.' -f $ExpectedEpisodes, $CsvRows.Count)
}

$CsvUniqueTrajectoryIds = @($CsvRows | Select-Object -ExpandProperty trajectory_id -Unique)
if ($CsvUniqueTrajectoryIds.Count -ne $ExpectedEpisodes) {
    throw 'CSV validation failed: trajectory_id values are not unique.'
}

$CsvToolCalls = [long](($CsvRows | Measure-Object -Property tool_calls -Sum).Sum)
if ($CsvToolCalls -ne $DirectToolCalls) {
    throw ('CSV validation failed: tool-call total {0} does not match JSONL total {1}.' -f $CsvToolCalls, $DirectToolCalls)
}

$CsvSpecRows = @($CsvRows | Where-Object { -not [string]::IsNullOrWhiteSpace($_.spec_chars) })
[long]$CsvSpecChars = 0
if ($CsvSpecRows.Count -gt 0) {
    $CsvSpecChars = [long](($CsvSpecRows | Measure-Object -Property spec_chars -Sum).Sum)
}
if ($CsvSpecChars -ne $DirectSpecChars) {
    throw ('CSV validation failed: specification-character total {0} does not match JSONL total {1}.' -f $CsvSpecChars, $DirectSpecChars)
}

$CoveragePercent = 100.0 * $DirectSpecAvailableEpisodes / $ExpectedEpisodes
$MeanToolCalls = [double]$DirectToolCalls / $ExpectedEpisodes
$MeanSpecChars = $null
if ($DirectSpecAvailableEpisodes -eq $ExpectedEpisodes) {
    $MeanSpecChars = [double]$DirectSpecChars / $ExpectedEpisodes
}

$AggregateToolLeverage = $null
if ($DirectSpecChars -gt 0) {
    $AggregateToolLeverage = [double]$DirectToolCalls / ([double]$DirectSpecChars / 1000.0)
}

Write-Host ''
Write-Host 'Cohort summary:'
Write-Host ('  Episodes: {0}' -f $ExpectedEpisodes)
Write-Host ('  Exact task-input coverage: {0}/{1} ({2:N2}%)' -f $DirectSpecAvailableEpisodes, $ExpectedEpisodes, $CoveragePercent)
Write-Host ('  Total specification characters (available rows): {0}' -f $DirectSpecChars)
Write-Host ('  Mean specification characters per episode: {0}' -f (Format-NullableNumber -Value $MeanSpecChars))
Write-Host ('  Total tool calls: {0}' -f $DirectToolCalls)
Write-Host ('  Mean tool calls per episode: {0:N2}' -f $MeanToolCalls)
if ($DirectSpecAvailableEpisodes -eq $ExpectedEpisodes) {
    Write-Host ('  Aggregate tool calls per 1,000 specification characters: {0:N4}' -f $AggregateToolLeverage)
}
else {
    Write-Host ('  Aggregate tool calls per 1,000 available specification characters: {0:N4} (primary cohort statistic unavailable until coverage is complete)' -f $AggregateToolLeverage)
}

Write-Host ''
Write-Host 'Resolved versus unresolved tool depth:'
foreach ($ResolvedValue in @($true, $false)) {
    $GroupRows = @($Rows | Where-Object { $_.resolved -eq $ResolvedValue })
    $ToolValues = @($GroupRows | ForEach-Object { [int]$_.tool_calls })
    $Label = if ($ResolvedValue) { 'resolved' } else { 'unresolved' }
    Write-Host ('  {0}: n={1}, mean={2}, range={3}-{4}' -f $Label, $GroupRows.Count, (Format-NullableNumber -Value (Get-Mean -Values $ToolValues)), (Get-Minimum -Values $ToolValues), (Get-Maximum -Values $ToolValues))
}

Write-Host ''
Write-Host 'Run-level means and ranges:'
$RunSummary = foreach ($RunIndex in $ExpectedRuns) {
    $RunRows = @($Rows | Where-Object { $_.run_index -eq $RunIndex })
    $ToolValues = @($RunRows | ForEach-Object { [int]$_.tool_calls })
    $RunSpecRows = @($RunRows | Where-Object { $null -ne $_.spec_chars })
    $SpecValues = @($RunSpecRows | ForEach-Object { [long]$_.spec_chars })

    [long]$RunToolTotal = 0
    [long]$RunSpecTotal = 0
    if ($ToolValues.Count -gt 0) {
        $RunToolTotal = [long](($ToolValues | Measure-Object -Sum).Sum)
    }
    if ($SpecValues.Count -gt 0) {
        $RunSpecTotal = [long](($SpecValues | Measure-Object -Sum).Sum)
    }

    $RunLeverage = $null
    if ($RunSpecTotal -gt 0) {
        $RunLeverage = [double]$RunToolTotal / ([double]$RunSpecTotal / 1000.0)
    }

    [pscustomobject][ordered]@{
        run_index = $RunIndex
        episodes = $RunRows.Count
        spec_coverage = $RunSpecRows.Count
        mean_tool_calls = Format-NullableNumber -Value (Get-Mean -Values $ToolValues)
        min_tool_calls = Get-Minimum -Values $ToolValues
        max_tool_calls = Get-Maximum -Values $ToolValues
        mean_spec_chars = Format-NullableNumber -Value (Get-Mean -Values $SpecValues)
        min_spec_chars = Get-Minimum -Values $SpecValues
        max_spec_chars = Get-Maximum -Values $SpecValues
        aggregate_tool_calls_per_1k_spec_chars = Format-NullableNumber -Value $RunLeverage -Format 'N4'
    }
}

$RunSummary | Format-Table -AutoSize | Out-String | Write-Host
Write-Host ('CSV written and validated: {0}' -f $OutputPath) -ForegroundColor Green
