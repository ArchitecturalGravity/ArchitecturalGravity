# Runner Invocation Contract

- Contract ID: `arcgrav.shared.runner-invocation`
- Version: `2.0.0`
- Status: published
- Compatibility scope: shared runtime callers and runner adapters

## Purpose

This contract governs one runner request and its normalized terminal observation. It does not define benchmark parsing, scoring, provider protocols, report authority, or object/module topology.

## Adapter independence

This contract defines normalized boundary semantics, not a universal wire protocol or control inventory. Each registered adapter declares its own supported and fixed controls, transports, authentication, discovery, telemetry and limitations. Conformance does not require other adapters to imitate Codex CLI or any other provider. Adapter selection is registration-driven; a missing or unsupported implementation cannot be silently replaced with another runner. Adapter-specific support remains subject to this contract’s identity and unsupported-control rules.

## Behavioral requirements

A conforming runner boundary MUST provide stable semantics equivalent to `describe`, `execute`, and `close`:

- `describe` MUST expose the runner identity, contract compatibility, capabilities, supported controls, fixed controls, limitations, response-retention behavior, telemetry behavior, and secret-handling metadata needed to validate a request before execution. Repeated calls for the same configured runner MUST be stable.
- `execute` MUST consume exactly one immutable accepted runner request and MUST return exactly one terminal normalized observation.
- `close` MUST be idempotent and MUST NOT mutate already-retained evidence. Execution after close MUST fail deterministically without provider submission.

Before provider or external-runtime submission, `execute` MUST validate all comparison-relevant request identity it is responsible for enforcing, including observation identity, case/treatment/repetition identity, execution-boundary fingerprint, prompt/input byte identity, conversation isolation policy, and declared supported/fixed controls.

Unsupported or unenforceable comparison controls MUST produce an `unsupported` terminal observation before provider submission. A runner MUST NOT silently substitute a model, runtime, access method, request framing, tool policy, memory policy, retry policy, timeout policy, or other comparison-relevant control.

Prompt and input bytes MUST be preserved exactly except for request framing explicitly declared by the runner registration and accepted execution boundary. Output bytes MUST NOT be trimmed, normalized, repaired, semantically parsed, or guessed by the runner. If a provider mixes progress/logging with response content, extraction is permitted only when the extraction rule is registered and the retained evidence proves the exact extracted byte range or equivalent integrity-preserving reference.

Each accepted attempt MUST begin with the clean process, conversation, session, cache, memory, retry, and tool state required by the accepted boundary and runner registration. Prior observation state MUST NOT leak into a later observation.

## Terminal statuses

Exactly one of these terminal runner statuses MUST be returned:

- `completed`: execution finished under the accepted boundary and response availability is represented explicitly.
- `failed`: execution was attempted but could not produce a conforming completed observation.
- `timed_out`: the accepted timeout policy terminated the attempt.
- `cancelled`: accepted orchestration cancellation terminated the attempt.
- `unsupported`: the runner could not honor the accepted boundary or a required preflight condition before provider submission.

A missing, unavailable, unsupported, failed, or malformed response MUST NOT be represented as a successful empty response. A genuinely empty provider response, when allowed by the registered runner behavior, remains an explicit completed response with byte identity and availability evidence; later benchmark/runtime contracts decide whether that evidence is admissible or scorable.

## Normalized observation requirements

A terminal observation MUST retain enough benchmark-neutral evidence to establish:

- unchanged request and observation identities;
- runner/adapter identity and version;
- this contract ID and version;
- accepted execution-boundary fingerprint;
- terminal status and response availability state;
- start/completion timing and duration when observable;
- exact retained response bytes or an integrity-verifiable reference, with SHA-256 identity where a response exists;
- ordered retry/attempt evidence bounded by the accepted retry policy;
- provider/runtime identifiers when permitted and observed;
- error classification and fixed diagnostic classifications for non-completed outcomes;
- usage evidence only with its provenance, distinguishing provider-reported usage from runner-measured byte telemetry;
- deviations between declared and observed execution controls;
- allowlisted registered namespaced extensions.

Only the exact extracted scoring response and relevant projected measurement sources are retained. Surrounding raw provider material MUST NOT be retained or referenced as a fallback. Excluded channels MUST remain explicit without raw-content hashes or payloads. Missing permitted evidence MUST retain an explicit unavailability state, never invented content.

Observations MUST be immutable once returned into the accepted lifecycle. A runner MUST NOT create accepted-run, scoring, or report authority.

## Secret handling

Secret values and secret-bearing handles are governed by `arcgrav.shared.transient-invocation@1.0.0`. They MUST NOT enter canonical comparison identity, normalized retained observations, logs, diagnostics, commands, environment summaries, reports, or extensions.

## Extension rules

Runner-specific extensions MUST be namespaced and additive. They MAY add transport, provider, telemetry, or extraction evidence, but MUST NOT replace required shared identity/status fields, weaken isolation, bypass unsupported-control rejection, add benchmark semantics, or alter terminal-status meaning.

## Conformance expectations

A conforming implementation MUST demonstrate, without requiring a live provider:

- stable description and explicit compatibility declaration;
- immutable request handling;
- rejection of unsupported controls before provider submission;
- exact prompt/input framing and byte hashing;
- clean-state isolation between observations;
- exactly one terminal observation for completed, failed, timed-out, cancelled, and unsupported paths;
- bounded ordered retry evidence;
- explicit response availability and integrity evidence;
- secret redaction across retained evidence and diagnostics;
- absence of benchmark-specific imports, branching, parsing, scoring or report authority.

Current retained observations use `arcgrav.shared.schema.treatment-observation@1.0.0`. Their `arcgrav.runner:execution` extension, when present, uses `arcgrav.shared.schema.runner-execution-evidence@2.0.0`. Exact schema files and extension points are listed in the [schema catalog](../schemas/catalog.json). These schemas formalize retained structures, not a universal provider wire protocol; structural validity alone does not satisfy this contract.

In particular, current runtime `observed` labels do not establish every effective control independently; see the [effective-execution limitation](EFFECTIVE_EXECUTION.md#current-implementation-limit).

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
