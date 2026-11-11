# Shared Contract Catalog

This catalog binds published shared behavioral contracts to exact semantic versions. The linked documents define behavior; filenames, module names, and implementation topology do not establish authority.

## Published contracts

| Contract ID | Version | Status | Compatibility scope | Document |
| --- | --- | --- | --- | --- |
| `arcgrav.shared.runner-invocation` | `2.0.0` | published | Shared runtime callers and runner adapters | [RUNNER_INVOCATION.md](RUNNER_INVOCATION.md) |
| `arcgrav.shared.launch-environment` | `1.0.0` | published | Shared runtime, golden execution, and runner adapters that launch an external runtime | [LAUNCH_ENVIRONMENT.md](LAUNCH_ENVIRONMENT.md) |
| `arcgrav.shared.transient-invocation` | `1.0.0` | published | Frontends, shared runtime, golden execution, and runner adapters that handle invocation-only or secret values | [TRANSIENT_INVOCATION.md](TRANSIENT_INVOCATION.md) |
| `arcgrav.shared.golden-execution` | `2.0.0` | published | Shared runtime, benchmark registrations requiring golden authority, and registered golden executors | [GOLDEN_EXECUTION.md](GOLDEN_EXECUTION.md) |
| `arcgrav.shared.run-lifecycle` | `1.0.0` | published | Shared application/runtime planning, accepted execution orchestration, runner adapters, and evidence consumers that reason about planned treatment observations | [RUN_LIFECYCLE.md](RUN_LIFECYCLE.md) |
| `arcgrav.shared.evidence-validation` | `1.0.0` | published | Shared validation, accepted runtime finalization, evaluation, reporting, reconstruction, and other authority-sensitive consumers of retained benchmark evidence | [EVIDENCE_VALIDATION.md](EVIDENCE_VALIDATION.md) |
| `arcgrav.shared.scorer-invocation` | `1.0.0` | published | Shared evaluation, accepted runtime scoring, validation, aggregation, reporting, and reconstruction consumers that invoke registered scoring or consume retained score artifacts | [SCORER_INVOCATION.md](SCORER_INVOCATION.md) |
| `arcgrav.shared.failure-taxonomy` | `1.0.0` | published | Shared evaluation, accepted runtime finalization, validation, aggregation, reporting, and reconstruction consumers that classify or resolve benchmark-neutral failure evidence | [FAILURE_TAXONOMY.md](FAILURE_TAXONOMY.md) |
| `arcgrav.shared.effective-execution-evidence` | `1.0.0` | published | Shared runtime, runner and launch adapters, evidence validation, evaluation, reporting, reconstruction, and other authority-sensitive consumers of declared-versus-observed execution facts | [EFFECTIVE_EXECUTION.md](EFFECTIVE_EXECUTION.md) |
| `arcgrav.shared.report-generation` | `3.0.0` | published | Automatic completion of scored accepted runs and exact retained report readers | [REPORT_GENERATION.md](REPORT_GENERATION.md) |
| `arcgrav.shared.run-completion` | `2.0.0` | published | Execution completion, archive publication and exact retained report import | [RUN_COMPLETION.md](RUN_COMPLETION.md) |
| `arcgrav.shared.treatment-measurements` | `1.0.0` | published | Shared adapters, telemetry, projections, reporting and reconstruction | [TREATMENT_MEASUREMENTS.md](TREATMENT_MEASUREMENTS.md) |
| `arcgrav.telemetry:provider-request-cache-validation` | `2.0.0` | published | Isolated replay producers, Results, retained history, reporting and reconstruction | [PROVIDER_REQUEST_CACHE_VALIDATION.md](PROVIDER_REQUEST_CACHE_VALIDATION.md) |
| `arcgrav.shared.evidence-minimization` | `1.0.0` | published | Every current evidence producer and consumer | [EVIDENCE_MINIMIZATION.md](EVIDENCE_MINIMIZATION.md) |

## Compatibility rules

- A published contract identity is the pair of stable contract ID and semantic version.
- Retained evidence or registrations that declare a contract MUST identify the exact contract ID and version used.
- Consumers MUST validate the declared ID and version before use and MUST fail closed on an unknown, unsupported, or ambiguous contract identity.
- Patch and minor versions are compatible only when the consumer explicitly declares support for them. Major-version compatibility MUST NOT be inferred.
- A breaking behavioral change requires a new major contract version. Published meaning MUST NOT be rewritten in place.
- Contract documents define behavior. Schemas, when present, define structure and MUST NOT be treated as replacements for these behavioral requirements.
- Implementation modules may be cited as examples by downstream specifications, but implementation topology is not part of compatibility unless a contract explicitly says otherwise.

## Scope and current support

These documents state normative requirements. `published` identifies a stable contract, not verified implementation conformance. Current gaps remain in [effective-execution evidence](EFFECTIVE_EXECUTION.md#current-implementation-limit), [failure integration](FAILURE_TAXONOMY.md#current-implementation-limit), [scorer retention](SCORER_INVOCATION.md#current-implementation-limits), [validation metadata and ordering](EVIDENCE_VALIDATION.md#current-implementation-limit), and [nested scorer-data minimization](EVIDENCE_MINIMIZATION.md#current-implementation-limit). The requirements remain binding; the gaps are not exceptions.

The catalog lists published behavioral authority, not blanket implementation support. Consumers MUST resolve each required contract ID/version and fail closed on unsupported behavior. Current launch support and golden constraints are documented in [Launch Environment](LAUNCH_ENVIRONMENT.md#current-implementation-support) and [Golden Execution](GOLDEN_EXECUTION.md#current-executor-support).

Schemas define structure separately in the [schema catalog](../schemas/catalog.json). Reconstruction in these contracts means checking or rederiving permitted evidence from retained sources; it does not authorize report regeneration. [Run Completion](RUN_COMPLETION.md) and [Report Generation](REPORT_GENERATION.md) require exact retained report bytes on reopen, import, and export.

## Extension policy

Contract extensions MUST be additive and namespaced. An extension MUST NOT replace or reinterpret required shared fields, weaken identity or evidence integrity, introduce benchmark-specific semantics into shared behavior, bypass lifecycle gates, or carry secret material into retained evidence.

All current producers and consumers MUST also enforce [Evidence Minimization](EVIDENCE_MINIMIZATION.md). Structural permission for an extension does not authorize retention of unknown or identifying content.

## Conformance

A catalog consumer conforms when it resolves exact published identities, checks compatibility before use, preserves unknown namespaced extension data only where structure and minimization permit, and fails closed rather than guessing or repairing authority.
