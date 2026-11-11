# Codex SWE-rebench PowerShell CSV Generator Plan

## Objective

Create a reusable PowerShell script that is run **from inside** the vendored SWE-rebench July 2026 dataset directory and generates and validates the Codex operational-baseline CSV using only files available in that directory.

Repository:

`/ArcGrav`

Required working directory:

`Research/swe_rebench_07_2026_trajectories/`

Primary script artifact:

`generate_codex_operational_baseline.ps1`

Generated CSV output:

`codex_operational_baseline.csv`

Expected local layout:

```text
swe_rebench_07_2026_trajectories/
├── CSV_compatibility_plan.md
├── generate_codex_operational_baseline.ps1
├── schema.json
└── trajectories/
    └── codex/
        ├── run_0.jsonl
        ├── run_1.jsonl
        ├── run_2.jsonl
        ├── run_3.jsonl
        └── run_4.jsonl
```

Expected population: **555 Codex delegation episodes**, corresponding to 111 tasks × 5 runs.

The purpose is to derive a reproducible Codex external operational baseline that can later be compared with:

`Research/Operational_Leverage/Studies/ArcGrav_Single_Workstream_Delegation_Leverage.md`

The CSV is a generated artifact. The PowerShell script is the reusable implementation that should be kept under version control.

---

## Working-Directory Contract

The script must be launched while the current working directory is:

```text
swe_rebench_07_2026_trajectories\
```

For example, from the repository root:

```text
cd .\Research\swe_rebench_07_2026_trajectories\
```

Then run:

```text
.\generate_codex_operational_baseline.ps1
```

or with PowerShell 7+ explicitly:

```text
pwsh -File .\generate_codex_operational_baseline.ps1
```

For Windows PowerShell 5.1:

```text
powershell.exe -ExecutionPolicy Bypass -File .\generate_codex_operational_baseline.ps1
```

The script must resolve all default inputs and outputs relative to the **current working directory**, not the repository root and not `$PSScriptRoot`:

```text
.\schema.json
.\trajectories\
.\trajectories\codex\run_0.jsonl
.\trajectories\codex\run_1.jsonl
.\trajectories\codex\run_2.jsonl
.\trajectories\codex\run_3.jsonl
.\trajectories\codex\run_4.jsonl
.\codex_operational_baseline.csv
```

The script must not search parent directories, infer the repository root, or fetch source data remotely. If it is launched from the wrong directory, it should fail clearly because local `schema.json` and/or `trajectories\` are not present.

If the CSV already exists, require `-Force` to overwrite it:

```text
.\generate_codex_operational_baseline.ps1 -Force
```

An optional `-OutputPath` may be supported, but any relative output path should still be resolved from the current working directory.

---

## Script Requirements

1. **Use only the local dataset directory.** The script must not require network access, GitHub API access, Python, jq, or third-party PowerShell modules. It must not modify any source JSONL file.

2. **Use the local `schema.json` as a lightweight contract check.** Parse `./schema.json`, obtain its required top-level fields and declared `schema_version`, and verify each trajectory record against those basic requirements. Full JSON-Schema validation does not require an external module and is not necessary for this extraction task.

3. **Access the local `trajectories\` tree.** Read the five files under `./trajectories/codex/`. Do not fetch trajectory data from GitHub or any other remote source.

4. **Stream the five JSONL files.** Read records line-by-line rather than loading all five trajectory files into memory at once. Treat each nonblank JSONL record as one delegation episode and preserve the source filename plus record position.

5. **Validate cohort integrity before writing the CSV.** Confirm:
   - exactly 555 records;
   - exactly 555 unique `trajectory_id` values;
   - exactly 111 unique `instance_id` values;
   - run indices 0 through 4 only;
   - exactly 111 episodes in each run;
   - every `instance_id` occurs exactly five times and once in every run;
   - the `run.index` inside each record matches its source `run_N.jsonl` file.

   Malformed JSON, missing schema-required top-level fields, schema-version mismatches, duplicates, omissions, unexpected run values, or unexpected event types must cause a clear failure before the CSV is written.

6. **Report participant/model values encountered.** Print the distinct participant key/type/scaffold/model/reasoning-effort tuples so any unexpected cohort composition is visible before output is accepted.

7. **Audit prompt representation.** Count prompt entries by `(role, status)` across the cohort and print that audit. For each trajectory, retain total prompt count, user prompt count, exact-task-input count, and a compact user-status summary.

8. **Define the primary specification denominator narrowly.** `spec_chars` must use only prompt content satisfying:

```text
role == "user"
status == "exact_task_input"
```

Do not silently blend `exact_rendered`, `exact_cli_append`, `exact_cli_config`, system prompts, developer prompts, scaffold text, or unavailable prompt classes into the primary denominator.

9. **Count specification characters reproducibly.** Count Unicode code points in exact task-input strings. If an episode has no usable `user + exact_task_input` content, leave `spec_chars` and normalized ratios blank and set `specification_available = false`. Do not replace missing or zero denominators with arbitrary constants.

10. **Count tool depth from normalized events only.** `tool_calls` is the count of events where:

```text
event.type == "tool_call"
```

Do not include `tool_result`, `file_change`, `agent_step`, `assistant_analysis`, `assistant_message`, `prompt`, or `final_message` in tool-call depth. Preserve counts of those event categories separately for auditing.

11. **Retain outcome fields.** Include `resolved`, evaluation status, agent exit status, and `evaluation_matches_selected` so successful and unsuccessful trajectories can be analyzed separately.

12. **Retain normalization diagnostics.** Include at least truncated tool-result counts, cache-result omissions, tool-result byte limit, and infrastructure-redaction indicators/details so problematic trajectories remain identifiable.

13. **Calculate normalized per-episode variables.** When `spec_chars > 0`, calculate:

```text
tool_calls_per_1k_spec_chars = tool_calls / (spec_chars / 1000)
events_per_1k_spec_chars     = normalized_events_total / (spec_chars / 1000)
```

Otherwise leave these fields blank.

14. **Write and read back the CSV.** Write `./codex_operational_baseline.csv` by default. After export, re-import the generated CSV and verify:
   - exactly 555 rows;
   - unique `trajectory_id` values;
   - aggregate tool-call total matches the independently accumulated JSONL total;
   - aggregate available specification-character total matches the independently accumulated JSONL total.

15. **Print the required summary.** The script should report:
   - number of episodes;
   - number and percentage with exact task-input coverage;
   - total and mean specification characters per episode when full coverage exists;
   - total and mean tool calls per episode;
   - aggregate tool calls per 1,000 specification characters;
   - resolved versus unresolved tool depth;
   - five run-level means and ranges.

16. **Do not require the CSV to be committed.** The CSV should be reproducible locally from `schema.json` and the vendored `trajectories\` files. The `.ps1` script is the primary implementation artifact.

---

## CSV Schema

The generated CSV should contain at least the following columns:

| Column | Meaning |
| --- | --- |
| `trajectory_id` | Unique trajectory/episode identifier |
| `instance_id` | SWE-rebench task identifier |
| `source_run_file` | Source JSONL filename |
| `source_record_index` | Nonblank record position within the source file |
| `source_line_number` | Physical source-file line number |
| `language` | Task language |
| `repository` | Repository identifier |
| `participant_key` | Codex participant key |
| `participant_type` | Participant type |
| `scaffold` | Agent scaffold |
| `model` | Recorded model |
| `reasoning_effort` | Recorded reasoning configuration |
| `run_index` | 0–4 repeated-run index |
| `run_attempt` | Recorded run attempt type |
| `retry_number` | Recorded retry metadata |
| `resolved` | Benchmark resolution outcome |
| `evaluation_status` | Evaluation status |
| `agent_exit_status` | Agent termination state |
| `evaluation_matches_selected` | Evaluation-selection audit flag |
| `prompt_count_total` | Number of entries in `prompts` |
| `user_prompt_count` | Number of user-role prompt entries |
| `exact_task_input_count` | Number of `user + exact_task_input` entries |
| `spec_chars` | Unicode code points in usable exact externally supplied task input |
| `tool_calls` | Count of `tool_call` events |
| `tool_results` | Count of `tool_result` events |
| `file_changes` | Count of `file_change` events |
| `agent_steps` | Count of `agent_step` events |
| `assistant_analysis_events` | Count of `assistant_analysis` events |
| `assistant_message_events` | Count of `assistant_message` events |
| `prompt_events` | Count of normalized `prompt` events |
| `final_message_events` | Count of `final_message` events |
| `normalized_events_total` | Total entries in `events` |
| `tool_calls_per_1k_spec_chars` | Per-episode specification-normalized tool depth |
| `events_per_1k_spec_chars` | Per-episode normalized-event depth |
| `tool_result_limit_bytes` | Normalization byte limit |
| `truncated_tool_results` | Normalization diagnostic |
| `cache_tool_results_omitted` | Normalization diagnostic |
| `infrastructure_redactions_present` | Whether redaction metadata is present |
| `infrastructure_redactions_json` | Compact redaction metadata for auditing |
| `specification_available` | Boolean indicating usable exact task specification |
| `specification_status_summary` | Compact audit of user prompt statuses |

---

## Aggregate Compatibility Requirement

The key cohort quantities for the ArcGrav comparison are:

```math
D_{\mathrm{tool}}
=
\frac{\sum \mathrm{tool\ calls}}{555}
```

```math
H_{\mathrm{spec}}
=
\frac{\sum \mathrm{specification\ characters}}{555}
```

and

```math
L_{\mathrm{tool}}
=
\frac{\sum \mathrm{tool\ calls}}
{\sum \mathrm{specification\ characters}/1000}
```

The primary cohort leverage statistic must be the **ratio of aggregate totals**. Do **not** average the per-row `tool_calls_per_1k_spec_chars` values to obtain the primary leverage statistic.

If exact task-input coverage is incomplete, the script must make that visible and must not present an incomplete-coverage ratio as the final primary cohort statistic.
