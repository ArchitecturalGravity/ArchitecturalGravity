# Failure Taxonomy and Precedence Contract

- Contract ID: `arcgrav.shared.failure-taxonomy`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared evaluation, accepted runtime finalization, validation, aggregation, reporting, and reconstruction consumers that classify or resolve benchmark-neutral failure evidence

## Purpose

This contract defines canonical failure classes, authority layers, precedence, candidate retention, and deterministic primary-failure resolution for an accepted evidence scope. It records what failed without deleting evidence, inventing benchmark semantics, or deciding metric disposition.

Availability states remain governed by their owning specifications and registrations. A state such as unavailable, excluded, non-comparable, or completed-non-scorable becomes a failure candidate only when the owning lifecycle or registered metric rule says that the state prevents a required authority transition or measurement.

## Current implementation limit

The standalone [resolver](../evaluation/failures/resolver.py) implements failure precedence, but accepted runtime orchestration does not invoke it. Runtime diagnostic strings are not the canonical candidate, primary, and suppressed-failure records required below. Resolver conformance tests do not establish lifecycle integration.

## Authority and inputs

Failure resolution MUST consume already-detected failure candidates from compatible lifecycle, validation, runner, evidence, or registered scoring boundaries. It MUST NOT discover benchmark-specific incorrectness by inspecting task output itself.

Every candidate entering shared resolution MUST identify:

- one exact canonical class from this contract or one validated namespaced extension class;
- the authority layer to which that class belongs;
- the affected evidence, observation, score, artifact, registration, or lifecycle identity;
- the source boundary that detected the candidate;
- a stable diagnostic or rule identity sufficient to explain why the candidate exists;
- permitted structured supporting details when available.

When a candidate is produced from behavior governed by another published shared contract, retained evidence MUST preserve that exact contract identity/version where applicable. Runner terminal outcomes used as candidates MUST preserve the compatible runner contract identity, including `arcgrav.shared.runner-invocation@2.0.0` when that version governs the observation. Golden or run-lifecycle candidates MUST preserve their governing `arcgrav.shared.golden-execution@2.0.0` or `arcgrav.shared.run-lifecycle@1.0.0` identity when applicable.

## Canonical authority layers

Shared failure authority is ordered from earliest to latest. A candidate in an earlier layer MUST dominate every candidate in a later layer:

1. `registration`
2. `identity_integrity`
3. `admission_isolation`
4. `execution`
5. `evidence`
6. `scoring`
7. `availability`
8. `task`

This ordering reflects authority, not severity. A later failure MAY be more severe, but it MUST NOT replace an earlier failure that invalidates later authority.

## Canonical classes and default within-layer precedence

Within each layer, classes are listed from highest to lowest default precedence. Exact class identifiers are stable contract data.

| Layer | Canonical classes in default precedence order |
| --- | --- |
| `registration` | `contract_incompatible`, `schema_incompatible`, `registration_invalid` |
| `identity_integrity` | `secret_retention_violation`, `artifact_integrity_mismatch`, `identity_mismatch`, `source_drift` |
| `admission_isolation` | `admission_blocked`, `isolation_violation` |
| `execution` | `unsupported_execution`, `timed_out`, `cancelled`, `execution_failed` |
| `evidence` | `evidence_invalid`, `evidence_missing`, `evidence_duplicate`, `evidence_unexpected`, `evidence_nonterminal` |
| `scoring` | `scorer_unavailable`, `scorer_failed`, `score_artifact_invalid` |
| `availability` | `required_input_unavailable`, `required_measurement_unavailable`, `non_comparable`, `completed_non_scorable` |
| `task` | `task_malformed`, `task_refused`, `task_incorrect` |

The canonical classes have these meanings:

- `contract_incompatible`: a required declared behavioral contract identity/version is unknown, unsupported, ambiguous, or incompatible.
- `schema_incompatible`: a required declared schema identity/version is unknown, unsupported, ambiguous, or incompatible.
- `registration_invalid`: required registered authority is absent, invalid, ambiguous, or incompatible for the attempted operation.
- `secret_retention_violation`: secret or secret-bearing transient material entered retained evidence, identity, diagnostics, reports, or another prohibited durable surface.
- `artifact_integrity_mismatch`: required bytes, hashes, references, or path confinement do not match accepted authority.
- `identity_mismatch`: an evidence or lifecycle identity does not match the exact accepted identity it claims to represent.
- `source_drift`: a mutable comparison-relevant source no longer matches the source identity frozen by accepted authority.
- `admission_blocked`: a required pre-execution admission gate failed or could not establish authority.
- `isolation_violation`: required clean process, conversation, session, cache, memory, retry, tool, or equivalent isolation was not preserved.
- `unsupported_execution`: the accepted execution boundary could not be honored before or without conforming workload execution.
- `timed_out`: execution terminated because the accepted timeout policy was reached.
- `cancelled`: execution terminated through accepted orchestration cancellation.
- `execution_failed`: execution was attempted but did not produce a conforming successful terminal execution outcome and no higher-precedence execution class applies.
- `evidence_invalid`: retained evidence exists but violates required structural, chronological, provenance, integrity, lifecycle, or contract invariants not already classified in an earlier layer.
- `evidence_missing`: required evidence was not retained or cannot be located for the affected accepted identity.
- `evidence_duplicate`: more than one evidence item occupies a role or identity that requires uniqueness.
- `evidence_unexpected`: retained evidence claims an unplanned, unauthorized, or otherwise unexpected role or identity.
- `evidence_nonterminal`: final reconciliation encountered evidence that remained in a transient/nonterminal state where terminal evidence was required.
- `scorer_unavailable`: a required registered scorer or scoring dependency could not be invoked or resolved.
- `scorer_failed`: registered scorer invocation ran but failed to return a conforming result.
- `score_artifact_invalid`: scorer output was returned but failed shared score-artifact conformance.
- `required_input_unavailable`: a required scoring or measurement input is explicitly unavailable after earlier authority remains otherwise valid.
- `required_measurement_unavailable`: a required measurement could not be established even though its required retained inputs are otherwise valid.
- `non_comparable`: the affected evidence cannot validly participate in the registered comparison scope.
- `completed_non_scorable`: execution completed, but the registered scoring contract cannot produce a score from the retained output.
- `task_malformed`: a registered benchmark parser/scorer determined that completed task output violates the benchmark-owned required task format.
- `task_refused`: a registered benchmark parser/scorer determined, under registered benchmark-owned rules, that completed task output is a refusal.
- `task_incorrect`: a registered benchmark scorer determined, under registered benchmark-owned rules, that otherwise scorable task output is incorrect.

Shared code MUST NOT infer `task_malformed`, `task_refused`, or `task_incorrect` directly from benchmark output. Those candidates enter shared resolution only from validated registered benchmark-owned parsing/scoring authority.

A normalized runner outcome maps to the execution layer without changing the original runner evidence: runner `unsupported` maps to `unsupported_execution`, `timed_out` to `timed_out`, `cancelled` to `cancelled`, and terminal `failed` to `execution_failed`. Runner `completed` is not itself a failure candidate.

## Resolution requirements

A conforming resolver MUST:

1. validate every candidate class and its declared authority layer before ordering;
2. reject an unregistered alias, unknown canonical class, undeclared extension class, or class/layer mismatch rather than coercing it to a known class;
3. preserve every valid detected candidate;
4. select the earliest authority layer represented by the candidate set;
5. apply the default within-layer precedence unless an applicable registered metric rule explicitly supplies a permitted within-layer override;
6. select exactly one primary candidate from the winning class;
7. retain every other candidate as suppressed, including candidates from later layers;
8. produce deterministic output independent of input enumeration order.

When more than one candidate remains tied after layer and class precedence, the resolver MUST break ties deterministically by affected evidence identity, then source identity, then stable candidate identity using canonical bytewise ordering of their serialized identifiers. A caller MUST NOT use arrival order, dictionary order, filesystem order, GUI order, or exception timing as precedence.

A registered metric rule MAY reorder classes only within one authority layer and only for that metric's disposition. It MUST identify its metric registration ID/version and the exact ordered classes it overrides. It MUST NOT move a class to another authority layer, suppress candidate retention, turn an unknown class into a canonical class, or change the global primary failure used for lifecycle/evidence diagnostics unless the owning contract explicitly authorizes that use.

If candidate validation itself fails, resolution MUST fail closed with deterministic validation issues. An invalid candidate set MUST NOT yield a fabricated primary class.

## Failure evidence and observable results

Resolved failure evidence MUST retain:

- this contract ID and version;
- affected accepted generation, observation, score, artifact, or measurement identities as applicable;
- primary class, authority layer, and precedence basis;
- the selected primary candidate identity;
- all valid candidates in deterministic order;
- all suppressed candidate identities and their classes/layers;
- applicable registered metric rule identity/version when a permitted within-layer override is used;
- source diagnostic/rule identities and permitted structured details;
- exact upstream contract identities/versions where a candidate derives from another durable contract;
- namespaced additive extensions.

Failure evidence MUST remain separate from metric disposition. A primary failure class does not by itself mean numeric zero, exclusion from a denominator, terminal `BlockedRun`, or report omission. Those effects require the owning lifecycle or registered metric rule.

## Prohibited behavior

A conforming implementation MUST NOT:

- discard non-primary candidates;
- let task incorrectness, malformed output, or refusal hide registration, integrity, isolation, execution, evidence, scoring, or required-availability failures;
- convert a failure to numeric zero unless an active registered metric rule explicitly requires that disposition;
- infer a canonical class from an unregistered alias, free-form exception string, filename, benchmark name, provider name, GUI state, or implementation topology;
- classify successful empty response bytes as missing merely because their byte length is zero;
- classify missing or unavailable evidence as a successful empty value;
- use extension classes to weaken the fixed authority-layer ordering;
- retain secret material in failure details or extensions;
- mutate the source evidence being classified.

## Extension rules

An extension failure class MUST be namespaced, registered before accepted use, stable within its declared version, and assigned to exactly one existing shared authority layer.

Its registration MUST define the class ID, version, meaning, producing authority, applicable evidence scope, default within-layer position relative to canonical classes, and any compatibility constraints. Extension classes MAY add specificity but MUST NOT replace canonical evidence, remove candidates, create a new cross-layer precedence order, or introduce benchmark semantics into shared detection.

Benchmark-owned task extensions MAY add task-layer classes when a registered parser/scorer produces them. They MUST remain in the `task` layer and MUST NOT outrank shared authority failures.

A breaking change to canonical layer order, canonical class meaning, or default within-layer precedence requires a new major contract version.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- earlier authority layers dominate later layers;
- default within-layer precedence is stable;
- a permitted metric override can reorder only classes within one layer;
- input candidate order does not change the result;
- all suppressed candidates remain retained;
- unknown aliases and class/layer mismatches fail closed;
- runner non-completed terminal statuses map to the corresponding execution classes without mutating runner evidence;
- successful empty completed output is not treated as missing evidence;
- task-layer candidates cannot mask earlier shared failures;
- extension classes cannot change authority-layer ordering;
- secret values are absent from failure evidence and diagnostics.

All retained details MUST follow [Evidence Minimization](EVIDENCE_MINIMIZATION.md).
Redaction alone does not authorize free-form diagnostics or identifying data.
