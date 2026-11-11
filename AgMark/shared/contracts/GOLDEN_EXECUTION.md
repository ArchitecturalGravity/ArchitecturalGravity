# Golden Execution and Admission Contract

- Contract ID: `arcgrav.shared.golden-execution`
- Version: `2.0.0`
- Status: published
- Compatibility scope: shared runtime, benchmark registrations that require golden authority, and registered golden executors

## Purpose

This contract governs registered golden execution, integrity-verifiable evidence, and required treatment admission. It establishes execution and lifecycle authority, not benchmark-specific golden semantics, scoring, or implementation topology.

## Current executor support

The current executor supports only `native` launch, `stdin` or `registered_file` input, and `stdout` output. Other environment families or transports block admission before workload submission. Runner WSL support does not provide a golden WSL executor.

The declaration binds an absolute transient executable locator to a logical runtime reference and exact binary SHA-256. Preflight uses the resolved executable; artifact and runtime hashes are checked again before launch. Registered timeouts and stdout/stderr byte limits apply, and non-empty output is required only when declared. Output-limit checks reject oversized results after collection; they do not establish an in-flight memory cap. Additional resource controls or output transports require an implemented, registered extension, not merely a declaration.

## Authority and inputs

A required golden gate MUST derive its authority from one exact accepted execution snapshot plus validated registrations and permitted transient invocation material.

The accepted authority MUST identify the complete golden work required for the run, the accepted case or input identities to which that work applies, the registered golden declaration and artifact identities, the accepted execution-boundary fingerprint, and the declared runtime/environment requirements needed to execute the golden implementation.

Golden execution MUST use `arcgrav.shared.launch-environment@1.0.0` for launch selection and exact preflight/launch reuse whenever an external runtime is launched. Secret or invocation-only values MUST use `arcgrav.shared.transient-invocation@1.0.0` and MUST remain outside accepted identity and retained golden evidence.

## Behavioral requirements

For a run whose validated registration requires golden authority, a conforming golden boundary MUST:

1. derive the complete required golden execution set from accepted plan/snapshot authority before treatment construction;
2. verify each registered golden implementation artifact by exact byte identity before launch and reject any mismatch;
3. confine registered artifact and input paths to their authorized benchmark/package roots and reject traversal or escape;
4. resolve the declared launch environment from the accepted execution boundary without ambient fallback;
5. preflight the exact registered runtime/executable and bind that resolved runtime identity to execution;
6. resolve permitted transient invocation material only through declared transient channels and only after comparison identity and compatibility checks that do not require the secret value;
7. execute the registered golden implementation against the accepted case/input authority without substituting cached, manually authored, inferred, or scorer-produced expected output;
8. retain structured command controls, input transport, process status, exact scoring stdout, stderr byte count, timing, runtime identity and integrity evidence; exclude raw stderr, host command lines and arbitrary diagnostics;
9. require successful execution, required output availability, non-empty output when required, hashing, and evidence retention before admitting the golden result;
10. complete and fix all required golden evidence before constructing or submitting the first treatment request;
11. produce a deterministic blocked result for any required golden failure and authorize zero treatment observations for that run.

A required golden admission outcome MUST be exactly one of:

- `admitted`: every required golden execution has completed and all required integrity, launch, output, hashing, and retention checks succeeded;
- `blocked`: at least one required golden prerequisite or execution could not establish authoritative retained golden evidence.

When validated registration declares that no golden authority is required, this contract MUST NOT cause a golden implementation to run or fabricate golden evidence merely to satisfy the lifecycle shape.

Golden execution MUST preserve raw output bytes. Shared golden mechanics MUST NOT parse, normalize, repair, trim, semantically interpret, or score golden output. Benchmark-owned semantics may consume admitted retained golden evidence only through their registered boundaries after admission.

## Blocking conditions

A required golden gate MUST block treatment execution when any required condition cannot be established, including:

- invalid or incompatible golden registration;
- missing, changed, unverifiable, or out-of-root golden artifacts;
- unsupported or ambiguous launch environment;
- runtime preflight failure or inability to reuse the exact preflighted runtime;
- undeclared, missing, unauthorized, or unresolved required transient invocation material;
- launch failure, timeout, resource-limit termination, or nonzero process outcome;
- missing required output, empty output when non-empty output is required, or output-limit failure;
- inability to hash, retain, or integrity-address required golden evidence;
- secret leakage into evidence or diagnostics;
- any mismatch between the accepted golden authority and the execution actually performed.

A blocked golden gate MAY retain fixed diagnostic codes and partial non-authoritative evidence, but it MUST NOT create treatment observations, score artifacts, or accepted artifact authority.

## Evidence and observable results

Golden execution/admission evidence MUST distinguish declared requirements from observed facts and retain, where applicable:

- this contract ID and version;
- accepted snapshot, run-plan, and execution-boundary identities;
- registered golden declaration identity/version and artifact references;
- artifact byte-identity verification results;
- accepted case/input identities and input byte identity;
- declared launch-environment and runtime requirements;
- safe logical runtime reference, registered version and exact binary identity used for preflight and execution, without the transient host locator;
- safe structured command-control identity: logical runtime, registered relative entry and relevant arguments, plus declared input/output transport; no raw host command line;
- process start/completion timing and terminal process outcome;
- stdout availability, byte count and SHA-256 identity or integrity-verifiable reference, and stderr byte count without retaining its contents;
- required golden output availability, byte count, and SHA-256 identity;
- timeout/resource observations when available;
- fixed failure classification codes and explicit unavailable/invalid states;
- admission outcome and blocking reason when blocked;
- evidence sufficient to establish that required golden completion preceded every treatment observation;
- allowlisted registered namespaced extensions containing only relevant permitted evidence.

Observed runtime or environment evidence MUST NOT silently rewrite the accepted declaration. Evidence that cannot be retained or verified MUST remain explicitly unavailable or invalid rather than being represented as successful empty output.

## Prohibited behavior

A conforming implementation MUST NOT:

- perform first-time golden execution during scoring, reporting, reconstruction, or frontend rendering;
- allow a caller, frontend, scorer, report generator, or adapter to inject golden output as publication-capable authority;
- start treatment construction or submission before a required golden gate is admitted;
- convert a golden failure into synthetic empty output, implicit success, or a score value;
- select launch behavior from ambient `PATH`, the caller shell, a default WSL distribution, current working directory, GUI state, or other undeclared host defaults;
- re-resolve the runtime after preflight or execute through a runtime identity different from the one admitted at preflight;
- retain secret values, secret-bearing handles, or reversible secret derivatives in commands, environment evidence, stdout/stderr diagnostics, hashes, reports, or extensions;
- use benchmark-specific semantics inside shared golden execution to decide correctness;
- let extensions weaken artifact integrity, path confinement, exact launch reuse, golden-before-treatment ordering, or evidence retention requirements.

## Extension rules

Benchmark-specific golden extensions MUST be namespaced, additive, and registered. They MAY define stricter output requirements, non-stdout output artifacts, custom input transports, additional resource controls, or additional integrity evidence.

An extension MUST retain byte identity for authoritative inputs and outputs and MUST NOT replace shared required evidence, bypass admission, weaken launch or secret-handling contracts, or move benchmark semantic interpretation into shared execution behavior.

A breaking change to shared golden execution or admission meaning requires a new major contract version.

### Registered-file input extension

The native executor additionally supports `input_transport: registered_file`.
The selected golden authority declares an `input_artifact_id` and the complete
`implementation_artifact_ids` dependency list, including both its executable
source and the case file. The existing `artifact_id` continues to identify the
golden implementation. Registrations without these optional fields retain the
existing stdin behavior.

For this transport, the executor verifies the registered file against both its
artifact hash and the exact accepted case bytes. It stages verified dependencies
in a private workspace with their package-relative paths preserved, launches
the registered implementation there, and closes stdin. This allows the golden
to read a default file relative to its own source without depending on mutable
repository files during execution. The input artifact, relative path, byte
identity, and actual transport are retained in the namespaced golden evidence.
Missing, changed, or wrong-case input files block treatment admission.

Golden admission executes once per unique accepted case, before any treatment
requests. All treatment repetitions for that case consume the same retained
golden stdout; scoring, reporting, and treatment replay do not regenerate it.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- artifact hash mismatch and path escape block before launch;
- ambient host defaults cannot change accepted environment selection;
- preflight and execution use the same resolved runtime identity;
- cached or caller-supplied expected output cannot substitute for golden execution;
- launch failure, timeout, nonzero failure, missing required output, empty output when non-empty output is required, hashing failure, and retention failure each block treatment execution;
- any blocked required golden gate produces zero treatment observations;
- all required golden evidence is fixed before the first treatment observation begins;
- exact golden output bytes and hashes are retained without shared semantic normalization;
- transient secrets are absent from retained evidence and diagnostics;
- a registration that does not require golden authority does not trigger synthetic golden execution;
- namespaced extensions cannot bypass the admission gate or weaken shared invariants.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
