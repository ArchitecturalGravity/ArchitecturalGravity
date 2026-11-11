# Codex CLI Capture Update Runbook

Use this procedure whenever the selected Codex CLI version changes, including
patch releases and prerelease/build variants. Each change requires a review;
parser changes depend on the interfaces and behavior actually observed. Record
a validation-only update when those interfaces remain compatible.

The capture reference identifies the CLI release used to maintain capture. It
must follow evidence that AgMark remains aligned with what that CLI exposes and
how it exposes it. Changing the reference alone does not establish compatibility.

The [0.167.0 audit](CAPTURE_AUDIT_0_167_0.md) and its
[retained summary](fixtures/capture_audit_0_167_0.json) are a worked example.
Keep this runbook version independent; put each release's findings in a separate
audit record. Use current repository files, pinned upstream release source and
observed output. Project git history is not required by this procedure.

## 1. Identify the candidate and preserve the baseline

Record the currently declared capture reference and revision from
[registration.json](../../../adapters/Codex_CLI/registration.json), then record:

- The candidate's full `codex --version` result and exact executable SHA-256.
- Platform, architecture, Python version, launch mode and selected WSL
  distribution. Resolve the executable in the environment that will launch it.
- Upstream release/tag, its resolved source commit, and the downloaded archive
  hash when obtaining a candidate binary. Check available release digests.
- The supported environments and capture profiles this update will claim to cover.

Use an isolated candidate executable where practical. The audit harness uses
disposable homes and a local Responses server; it needs no copied credentials
or paid provider execution. Keep generated files under
`AgMark/Runtime/capture-audit/<version>/<environment>-attempt-<number>/`.
Use a new directory for every attempt so failed runs cannot inherit an earlier
`summary.json` or overwrite evidence of a failure.

Preserve existing version-specific audits, capability declarations and retained
plans/archives. Record the baseline limitations, including features whose source
audit is older than the capture reference.

## 2. Audit the CLI's exposed interfaces

Inspect the candidate's actual help, relevant schemas/configuration definitions,
and source at the resolved release commit. Follow the implementation when files
move; the worked example's source paths are navigation aids, not a fixed inventory.

| Surface | Questions to resolve |
| --- | --- |
| Launch and configuration | Which flags, configuration keys and environment variables activate capture? What are their defaults, precedence and platform restrictions? Are commands hidden from ordinary help? |
| `exec --json` | What events, fields, identity values, terminal states and tool item types are emitted? What ordering/completeness can be established? |
| Persisted sessions | Where and how are records stored? How is the exact thread matched? What establishes writer settlement, terminal state and source completeness? |
| Usage and cache counters | Which records describe a response, turn or thread? Which totals are cumulative? What is authoritative, and which representations must never be added together? |
| OTLP logs, traces and metrics | What exporters, protocols, endpoints and envelopes are supported? Verify names, attributes, types, units, timestamps, unspecified values, temporality and dimensions. |
| HTTP and WebSocket | How are generations, warmups, retries and completions exposed and correlated? Identify ancillary requests that must not count as generations. |
| Deep diagnostics | What enables diagnostic output? Which raw/bundle/reduced schemas and reducer invocation apply? How are root identity, links and recording completion represented? |
| Cache policy and derived contexts | Which claims are directly observed or source inferred? What evidence covers helpers, Guardian, forks and configurable policies? |

Create a mapping in the release audit for every relevant signal, including new,
changed and removed signals. Record its CLI source and activation method, field
names/types, units, scope, identity/correlation rule, AgMark extraction and
presentation, evidence reference, and availability or reason for exclusion.

Distinguish a field being exposed from its meaning being established. For
example, an exported duration does not by itself establish direct time to first
token, and observed cache tokens do not establish cache-key policy or eviction.

## 3. Run baseline probes and adapt capture

Run the existing audit against the candidate before advancing the reference.
Retain failures and inspect the corresponding output and source. A new version
may fail because its schema has no declaration yet, even when it emits the
expected records. Investigate that result rather than changing expected values
merely to obtain a pass.

Use the interface mapping to update only the components that need changes:

| Area | Implementation to inspect |
| --- | --- |
| Runtime/schema declarations | [runtime_reference.py](../../../telemetry/runtime_reference.py), especially `capture_schema_audit`; [profile.py](../../../telemetry/profile.py) |
| Collection, retention and interpretation | [telemetry/](../../../telemetry/): capture, collector, privacy, evidence, normalization and WSL bridge/worker/process handling |
| Session and stdout extraction | [Codex_CLI/](../../../adapters/Codex_CLI/): events, session discovery, record projection, token usage, tools and timing |
| Request capability probes and replay | [codex_cache/](../../../validation/codex_cache/): host worker, collector, capability admission and normalization |
| Plans and presentation | [projector.py](../../../../gui/application/projector.py), retained-history presentation and their tests |
| Reproducible audit | [capture_audit.py](capture_audit.py), its controlled provider and regression fixtures |

After source inspection and observed records establish a candidate schema, add
or adjust its exact-release schema declaration in the working implementation
and rerun verification. Keep earlier declarations. A declaration awaiting the
full audit is not permission to advance the published capture reference.

Keep registered implementation artifact digests synchronized with candidate
source edits before running registration-backed tests. A stale digest causes
an identity-validation failure even when the capture change is correct. Updating
those digests does not advance the capture reference; verify them again when
finalizing the update in step 6.

Preserve these rules while adapting capture:

- Keep counter scopes, authoritative totals and correlation explicit. Test
  values against independently supplied provider tuples and cumulative totals.
- Validate newly exposed fields before extending retention allowlists. Preserve
  exclusions, sanitization, bounds, source health and diagnostic consent.
- Missing, malformed, unknown or incomplete sources must produce explicit
  partial/unavailable outcomes. Benchmark completion does not prove capture
  completion. Keep capture failure distinct from benchmark execution failure.
- Keep exact launch-time version/binary checks. Numeric-core equality in the
  advisory does not grant schema capability; prerelease/build variants do not
  inherit a stock source audit without evidence.
- Preserve old records' interpretation. Use retained capability markers or a
  versioned extraction/normalization/schema path when semantics change; prove
  reconstruction of earlier evidence. Review the applicable protocol, sanitizer,
  extraction and normalization versions rather than bumping them automatically.
- Audit the fixture itself: it must distinguish Responses traffic from ancillary
  requests and generations from warmups, and exercise actual tool activity.

## 4. Verify the candidate with real CLI execution

Run commands below from the repository root, the directory containing `AgMark`.
Replace candidate paths, `X.Y.Z`, distribution and attempt number. Use the
selected platform's supported Python. These commands run the local controlled
provider; they do not run a scored or paid benchmark.

Windows native, in PowerShell:

```powershell
$captureVersion = "X.Y.Z"
$captureBinary = "C:\path\to\candidate\codex.exe"
$captureOutput = "AgMark/Runtime/capture-audit/$captureVersion/windows-native-attempt-01"
py -3 -m AgMark.shared.software_testing.adapters.codex_cli.capture_audit --binary "$captureBinary" --output "$captureOutput"
```

Linux native, including the baseline from the selected distribution:

```bash
capture_version="X.Y.Z"
capture_binary="/absolute/path/to/candidate/codex"
capture_output="AgMark/Runtime/capture-audit/${capture_version}/linux-native-attempt-01"
python3 -m AgMark.shared.software_testing.adapters.codex_cli.capture_audit --binary "$capture_binary" --output "$capture_output"
```

Actual WSL bridge: run from the same Linux distribution named by
`--distribution`, with Windows interop available. This harness option uses
`wsl.exe` and the production bridge; a Linux-native pass alone does not cover it.

```bash
capture_version="X.Y.Z"
capture_binary="/absolute/path/to/candidate/codex"
capture_output="AgMark/Runtime/capture-audit/${capture_version}/wsl-attempt-01"
python3 -m AgMark.shared.software_testing.adapters.codex_cli.capture_audit --binary "$capture_binary" --output "$capture_output" --wsl-launcher /mnt/c/Windows/System32/wsl.exe --distribution Ubuntu
```

Run Windows native and selected-WSL checks for the Windows application; include
Linux native or additional platforms when claiming their coverage. Document
unverified environments explicitly. A missing required environment leaves that
part of the update incomplete.

The current harness admits the stock request capability probe, then runs eight
cases per environment: Session, Telemetry and Deep Telemetry over both HTTP and
WebSocket, plus Telemetry/HTTP failure and cancellation. Extend this matrix when
new surfaces or changed behavior require it; the existing case count is not an
acceptance criterion by itself.

Require a successful exit and inspect `summary.json` plus the corresponding
capture bundles. Check identities, independent counters (including cache writes),
tool activity, source health, evidence integrity and reconstruction. A passed
summary must not conceal missing cases, unexpected emissions or source loss.

Any allowed partial outcome needs an explicit reason and scope. The existing
auxiliary-root graph exception requires a complete retained primary graph with
matching node counts and no primary parse errors, drops or incomplete recording.
It must not turn diagnostic coverage into a claim of complete coverage.

## 5. Run regressions and check retained history

Use [TESTING.md](../../TESTING.md) for the centralized test workflow. Relevant
coverage lives in these directories and modules:

- `telemetry/`: capture, normalization, adversarial privacy, runtime-reference
  behavior and WSL bridge/process tests.
- `adapters/codex_cli/`: session parity, completed-response usage, source privacy,
  token/cache counters, tool telemetry and timing.
- `validation/codex_cache/`: probe surfaces, capability admission, runtime
  identity, transport diagnostics and replay evidence.
- `integration/test_runtime_reference_planning.py` and
  `integration/test_capture_progress.py`.
- `adapters/test_registered_runner_identity.py` and registration/contract tests.
- `frontends/gui/test_runtime_reference_projection.py`,
  `test_runtime_reference_history.py`, `test_runtime_version_binding.py`,
  `test_runtime_reference_advisory_qt.py` and
  `test_build_plan_registered_smoke_qt.py`.

For a baseline check from the repository root:

```text
python -m unittest AgMark.shared.software_testing.telemetry.test_capture AgMark.shared.software_testing.telemetry.test_normalization AgMark.shared.software_testing.adapters.codex_cli.test_completed_response_usage AgMark.shared.software_testing.validation.codex_cache.test_probe_surface AgMark.shared.software_testing.telemetry.test_runtime_reference AgMark.shared.software_testing.integration.test_runtime_reference_planning AgMark.shared.software_testing.frontends.gui.test_runtime_reference_history AgMark.shared.software_testing.adapters.test_registered_runner_identity
```

Select further tests by the affected behavior. Use a Qt-capable Windows Python
for GUI checks, with the project's dependency in
[requirements-ci.txt](../../requirements-ci.txt). For the full centralized
suite, run `python shared/software_testing/ci.py --all` from the AgMark directory;
`--all` bypasses git impact selection. Report skipped tests, failures and reruns
with their evidence; synthetic tests do not substitute for actual binary probes.

Prove that old retained sources still reconstruct identically, old plans and
archives retain their recorded capture reference, and version/binary drift
checks remain effective. After the metadata update below, verify that a newly
built matching plan omits the warning and a mismatching plan still shows the
nonblocking advisory. Restart AgMark before the final GUI check.

## 6. Advance metadata only after verification

When the claimed coverage is demonstrated, make these changes together:

1. In `registration.json`, set
   `extensions.agmark.telemetry:capture-capability-update.reference_runtime_version`
   to the actual audited release and advance its `revision` to identify this
   maintenance update. Never substitute the installed runtime during planning.
2. Update `extensions.agmark.telemetry:profile.capability_audit` with the applicable
   runtime/source audit, and review the exact-release declarations in
   `runtime_reference.py`. Retain earlier declarations needed by existing evidence.
3. Refresh SHA-256 values in `implementation_artifacts` for edited implementation
   files. Add newly owned implementation files and their IDs to the declared
   `runner_implementation_artifact_ids` as applicable. Verify repository discovery
   and registration identity after refreshing them.
4. Update tests that intentionally assert the shipped reference/revision.
   Preserve older versions used to test mismatch, history or older capability
   semantics. Do not globally replace version strings or advance independent
   cache-policy audits without their own evidence.
5. Write the release audit and durable sanitized summary, then update relevant
   README links or current-reference text. Repeat the metadata, identity and GUI
   checks affected by these final edits.

If verification is incomplete or reveals unresolved incompatibility, keep the
previous reference and audited declarations as the published baseline. Record
the candidate's failed/unsupported scope and evidence. Do not relabel a mismatch
as compatibility. Isolate or remove only unsuccessful candidate changes; keep
previously accepted evidence intact.

## 7. Retain the release audit

Create `CAPTURE_AUDIT_<version_with_underscores>.md` beside this runbook and link
back to it. Use a distinct filename for build/prerelease variants. Retain a
corresponding sanitized summary under `fixtures/`; preserve earlier audit records.

Record the final harness/source hashes, binary identities, commands, exit codes,
case results, independent expected/observed values, evidence digests and locations,
regression results, exclusions and remaining limitations. Keep full sanitized
bundles available for review; a digest without accessible evidence is not a
replacement for that evidence. `Runtime/` is disposable and ignored, so record
how evidence will remain accessible or be reproduced before it is cleaned.

Copy this outline into the new release audit:

```markdown
# Codex CLI <full version> capture audit

Maintenance procedure: [Capture update runbook](CAPTURE_MAINTENANCE.md)
Date:
Prior capture reference/revision:
Candidate full version and proposed capture revision:
Outcome: verified / incomplete / unsupported

## Runtime and source identities
Platform, architecture, launch mode/distribution, Python, executable hashes,
release/tag, resolved source commit, archive digest and final harness hash.

## Interface mapping and changes
For each relevant signal: source/activation, fields/types, units, scope,
correlation, extraction/presentation, evidence and availability/exclusion.
Include unchanged interfaces that were checked and the source links used.

## Implementation and capability changes
Corrections, retained schema/capability behavior, registration artifact changes,
version decisions and independent audits intentionally left at their own basis.

## Controlled execution and regression evidence
Commands, environments, attempts, exit codes, cases, expected/observed counters,
source health, reconstruction/integrity checks, summary/bundle locations and
digests; tests, skips, failures and reruns; matching/mismatching plan checks.

## Limitations and decision
Partial/unavailable scopes, unverified environments, unresolved findings,
the acceptance decision and published reference/revision (if advanced).
```

## Acceptance checklist

- [ ] Exact candidate identities and pinned source are recorded for every claimed environment.
- [ ] Added, changed, removed and relevant unchanged interfaces have an evidence-backed capture mapping.
- [ ] Every measurement shown as available has a verified source, extraction rule, meaning and scope.
- [ ] Actual CLI probes cover the declared profiles/transports and relevant failure paths; independent counters agree.
- [ ] Partial/unavailable outcomes and intentional exclusions are explicit; exceptions cannot hide primary failures.
- [ ] Retention, diagnostic consent, old-source reconstruction, frozen history and exact runtime checks remain valid.
- [ ] Required regressions and GUI checks pass; skipped or unverified coverage is recorded accurately.
- [ ] Metadata, capability declarations, registered artifact identities and documentation agree with the verified result.
- [ ] A separate release audit and accessible sanitized evidence support the decision.
