# Launch Environment Contract

- Contract ID: `arcgrav.shared.launch-environment`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared runtime, golden execution, and runner adapters that launch an external runtime

## Purpose

This contract governs the launch environment for golden implementations, CLIs, and other external runtimes. Environment selection is comparison authority and MUST come from the accepted execution boundary, not ambient host defaults.

## Current implementation support

| Execution path | Supported launch | Constraints |
| --- | --- | --- |
| Codex CLI | `native`; `wsl` on Windows hosts | Requires the selected executable, explicit launch mode, and selected WSL distribution when applicable. Registered defaults are resolved before planning; preflight must establish the selected runtime. |
| Mock Model | Native worker | Provider-free execution through the registered worker protocol; no WSL launch mode. |
| Golden executor | `native` only | Exact registered runtime binary; `stdin` or `registered_file` input; `stdout` output. See [golden limits](GOLDEN_EXECUTION.md#current-executor-support). |
| OpenAI API | None | Reserved adapter domain without a callable registration or implementation. |

This matrix describes available paths, not proof that a runtime is installed or conforms on a particular host. A compatible registration and successful required preflight remain mandatory. Codex WSL support does not imply golden WSL support. Unsupported selections MUST fail closed, never fall back to native execution.

## Behavioral requirements

Before launch, the consumer MUST derive a launch-environment request from the accepted execution boundary and compatible registration. That request MUST distinguish retained comparison controls from transient launch selectors. Environment family, runtime identity/version and relevant integrity hashes are retained. Exact executable locators, WSL instance selectors and other identifying host selectors are supplied separately for launch and MUST NOT enter canonical or retained evidence.

A resolver MUST:

1. validate that the requested environment family and selectors are supported;
2. resolve the requested environment without falling back to ambient host defaults;
3. preflight the exact runtime/executable in that resolved environment when the owning lifecycle requires runtime preflight;
4. bind the resolved runtime/executable identity used for preflight to the subsequent launch;
5. retain allowlisted declared environment controls separately from directly observed runtime identity/version and integrity evidence, excluding transient selectors;
6. return a deterministic unsupported or blocked result when the requested environment cannot be established exactly enough for the owning lifecycle.

The launch step MUST use the same resolved environment and runtime identity that passed preflight. It MUST NOT re-resolve through a different `PATH`, default shell, default WSL distribution, host-runtime lookup, or other ambient mechanism after preflight.

Comparison-relevant environment changes MUST alter canonical execution-boundary identity before acceptance. Only allowlisted comparison-relevant observed environment/runtime facts MUST be retained as effective execution evidence and MUST NOT silently rewrite the accepted declaration.

## Prohibited behavior

A conforming implementation MUST NOT:

- select an environment from `platform.system()`, the caller shell, ambient `PATH`, a default WSL distribution, GUI state, current working directory, or another undeclared host default;
- silently fall back from one environment family, distribution, runtime, executable, or access method to another;
- treat a successful preflight in one environment as authority to launch in another;
- place secret values or secret-bearing handles in canonical environment identity or retained environment evidence;
- let benchmark-specific semantics choose shared launch behavior;
- infer support merely because a runtime happens to be installed.

## Evidence and observable results

Launch-environment evidence MUST distinguish declared requirements from observed facts and retain, where applicable:

- this contract ID and version;
- accepted execution-boundary fingerprint;
- declared environment family and allowlisted comparison controls, excluding identifying or host-specific launch selectors;
- resolver outcome and support status;
- logical runtime-relative reference and exact runtime identity, version and binary hash binding preflight to launch;
- observed runtime/environment version or identity when available;
- preflight result and fixed diagnostic classifications;
- deviations or inability to verify requested controls;
- allowlisted registered namespaced extensions containing only relevant permitted evidence.

Failure to establish required launch authority MUST occur before the external workload is submitted whenever the unsupported condition is knowable at preflight.

## Extension rules

Environment-specific extensions MUST be allowlisted and registered, namespaced, canonical when comparison-relevant, non-identifying, and additive. They MUST NOT weaken exact selection, permit ambient fallback, or hide comparison-relevant controls outside accepted identity.

New environment families MAY be introduced through registration plus namespaced contract-compatible extensions when their selection and evidence semantics preserve this contract. A behavior change that weakens or changes the shared selection invariant requires a new contract version.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- identical accepted environment declarations resolve identically under the same registered test environment;
- unsupported selectors fail closed before workload submission;
- ambient host defaults cannot override accepted selection;
- preflight and launch use the same resolved runtime identity;
- declared and observed environment evidence remain distinct;
- secret material does not enter identity or retained diagnostics;
- namespaced extensions cannot bypass the shared selection invariant.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
