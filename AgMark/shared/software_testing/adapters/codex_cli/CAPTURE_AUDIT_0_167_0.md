# Codex CLI 0.167.0 capture audit

Capture update: `runtime-neutral-capture-v2`, reference runtime `0.167.0`.
Performed on 2026-11-10. Project git history was not used.

Maintenance procedure: [Codex CLI capture update runbook](CAPTURE_MAINTENANCE.md).

## Evidence and scope

The release tag `rust-v0.167.0` resolves to upstream source commit
`086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`. The source archive was inspected
alongside the actual CLI help and controlled executions. This is an audit of
the release's capture interfaces, not a claim that every binary bearing that
version is identical or that exporter delivery is complete.

| Execution | Observed executable SHA-256 | Result |
| --- | --- | --- |
| Installed Linux CLI, native process | `cdcb45aaa01d0f14e298985e09465aebccd47f64ecd298aea44814af7b62bbda` | 8 cases passed |
| Same Linux CLI through actual `wsl.exe`, Ubuntu, production capture bridge and process guard | `cdcb45aaa01d0f14e298985e09465aebccd47f64ecd298aea44814af7b62bbda` | 8 cases passed |
| Official Windows x64 CLI, Windows Python 3.14.3 | `edfdd48f8b458af0906e507b4cb05217b326c3d6e515e9f024e05e3b8d650f70` | 8 cases passed |

The Windows release archive digest was checked against GitHub release metadata:
`94b51ca84648a6923784ef71f06e2feb1e10796ddb3f5d033ccb0fbe8daa2f16`.
It was extracted under `AgMark/Runtime/capture-audit/`, without replacing the
user's CLI installation.

Each execution covers Session, Telemetry and Deep Telemetry over HTTP and
WebSocket, plus a controlled failed response and cancellation. The harness uses
the production launch builders, configuration overrides, selected-host bridge,
session reader, extractor, sanitizer, collector, normalizer and evidence validator.
It checks reconstruction of retained session measurements and normalized facts.
Response counters are checked against independently supplied tuples, including
the cumulative totals of the root's completed responses. The separate stock
HTTP/WebSocket request capability probe is admitted against the observed binary
hash and version before the capture cases run.

The provider is a loopback-only Responses server with synthetic usage and a
scripted `echo` tool call. Disposable homes contain no copied authentication.
These observations establish actual CLI emission and AgMark interpretation for
the exercised cases; they do not measure a real provider's caching, billing,
latency, request trajectory or model behavior.

The durable [audit summary](fixtures/capture_audit_0_167_0.json) contains binary
identities, source identity, harness hash, checks, source health and evidence
digests. Full sanitized capture bundles remain in `Runtime/capture-audit/`.

## Interface mapping

All source links below are pinned to the audited release commit.

| CLI surface and exposure | AgMark handling and verified meaning |
| --- | --- |
| [`exec --json` JSONL events](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/exec/src/exec_events.rs) and [JSONL event processor](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/exec/src/event_processor_with_jsonl_output.rs) | `thread.started` identifies the exact invocation thread. Turn/item events establish lifecycle and tool observations. Terminal output and persisted session completion are checked separately. Stdout totals are not added to rollout totals. |
| [Persisted session and completed-response usage types](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/protocol/src/protocol.rs) | Capture finds the exact thread's JSONL under its isolated home, verifies `session_meta`, waits for settlement and retains a bounded projection. `usage`, `turn_token_usage` and `thread_token_usage` are distinct scopes. Final `token_count.info.total_token_usage` remains authoritative; demonstrated completed-response thread usage is a fallback. |
| [OTEL configuration](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/config/src/types.rs) and [exporter implementation](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/otel/src/provider.rs) | Stock `-c` overrides select OTLP/HTTP JSON at `/v1/logs`, `/v1/traces` and `/v1/metrics`. The collector runs beside the CLI, including inside WSL. All three signals were received through production capture. Unspecified zero timestamps are omitted before source-relative clock conversion. |
| [Response usage spans](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/session/turn.rs) and [WebSocket request/warmup lifecycle](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/client.rs) | Request validation uses explicit correlation and admitted span ancestry. Controlled checks establish input, cached input, cache-write input, output and reasoning counts. WebSocket warmups are distinct from generations; the production launch can produce multiple warmups. Native metric points keep their units, temporality, bucket counts and dimension completeness. Histograms are not expanded into request records. |
| [`CODEX_ROLLOUT_TRACE_ROOT`, bundle schema](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/rollout-trace/src/bundle.rs), [raw event schema](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/rollout-trace/src/raw_event.rs) and [hidden `debug trace-reduce` command](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/cli/src/main.rs) | Deep capture uses the existing explicit instrumentation consent, invocation-private scratch and the stock offline reducer. It supports reduced graph schemas 1 and 2 and retains schema 2's `recording_complete` flag. Structural nodes and explicit links survive; payload files, message bodies and tool text are excluded. Unknown graph schemas or incomplete recordings remain partial. |
| [Cache-key policy](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/client.rs) | The newer CLI has configurable key policy. This capture audit does not establish all fresh-root, helper, Guardian and fork namespaces. The existing `0.159.0` inference guard stays unchanged: cache-key policy on `0.167.0` remains explicitly unavailable, while observed cache token counters remain available. |

## Corrections made from observed output

- OTLP log batches contained an unspecified zero timestamp alongside an actual
  timestamp. Treating zero as an epoch observation produced an invalid relative
  value and caused AgMark to reject the whole batch. Zero OTLP timestamps now
  remain unspecified; meaningful timestamps and receipt order survive.
- The stock reducer emits graph schema 2. Capture previously accepted only
  schema 1. Both demonstrated graph versions are now supported; schema 2 must
  supply a boolean recording outcome. False means partial capture, even when
  the benchmark process completed.
- New stock `0.167.0` captures can interpret completed-response usage through a
  retained schema-capability marker. The exact release label and matching
  session metadata are required. Prerelease/build variants do not inherit this
  audit. Already retained records without that marker keep their original
  extraction behavior and source bytes.
- The controlled provider previously treated every HTTP POST as a generation.
  The CLI can POST ancillary turn-cost queries. Only `/v1/responses` now consumes
  scripted responses/counters. The first generation receives the tool call
  regardless of the number of preceding warmups. The fixture command is portable
  `echo`, allowing the same probe on Windows.
- Capture schema audit code is now included in the runner's declared artifact
  identity; edited implementation artifact digests were refreshed.

## Explicit limitations

The production approval path can create a separate diagnostic bundle whose
root differs from the thread returned on stdout. Its graph is not joined to the
selected root. Capture reports `diagnostic_graph_root_unmatched` and partial
diagnostic coverage, while retaining the matched root graph. The audit accepts
this explicitly scoped partial outcome; it does not report complete coverage
for those cases. Unknown, malformed, dropped or incomplete primary evidence
does not receive that exception.

Exporters remain best effort. The capture does not establish individual token
arrival times, direct time to first token, exact wire latency, reconnect counts,
physical cache eviction, provider cache efficiency or complete helper-request
coverage. Free-form log bodies, prompt/response/tool payload text, raw OTLP,
arbitrary attributes and identity-bearing labels remain excluded by the
retention policy. Exclusions and dimension loss are recorded.

Future runtime drift remains nonblocking and visible. A reference match means
numeric-core equality for presentation; it does not bypass exact launch-time
version/binary checks or grant a new capture capability. Old plans and archives
retain the capture reference and capability facts they originally recorded.

## Repeat the audit

From the directory containing `AgMark`, using the selected platform's Python:

```text
python -m AgMark.shared.software_testing.adapters.codex_cli.capture_audit --binary /absolute/path/to/codex --output AgMark/Runtime/capture-audit/current-native
```

For the WSL bridge check, run from the selected Linux distribution with Windows
interop and the same Linux CLI:

```text
python3 -m AgMark.shared.software_testing.adapters.codex_cli.capture_audit --binary /absolute/path/to/codex --output AgMark/Runtime/capture-audit/current-wsl --wsl-launcher /mnt/c/Windows/System32/wsl.exe --distribution Ubuntu
```

The command exits nonzero when capability admission, a required source,
independent counter comparison, lifecycle outcome, reconstruction or binary
identity check fails. Inspect source health in `summary.json`; passing the audit
does not erase its documented partial diagnostic scope.

## Regression validation

The final matrix passed all 24 real CLI cases. A 351-test focused sweep had one
Mock Model cancellation timing failure under concurrent audit load; that check
passed on a focused rerun alongside the capture regressions (43 tests). The
planning, frozen-history, projection and runner-identity checks passed (36
tests), as did 23 Windows Qt plan/advisory checks and 13 additional privacy,
session-parity, probe-surface and identity checks. Three opt-in tests in the
broader sweep were skipped. Registered implementation digests were verified.
