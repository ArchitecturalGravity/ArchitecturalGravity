# Scorer Invocation and Score Artifact Contract

- Contract ID: `arcgrav.shared.scorer-invocation`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared evaluation, accepted runtime scoring, validation, aggregation, reporting, and reconstruction consumers that invoke registered scoring or consume retained score artifacts

## Purpose

This contract governs registered parser, scorer, and annotation invocations over retained authoritative evidence and validation of their score artifacts. It establishes scoring authority, not benchmark correctness, semantic equivalence, metric meaning, aggregation conclusions, report interpretation, or implementation topology.

Scoring is an authority-preserving transformation of already-retained evidence under pre-registered metric and scorer rules. It MUST NOT create missing execution authority, repair source evidence, perform first-time golden execution, or infer benchmark semantics in shared code.

## Current implementation limits

- [Scorer invocation](../evaluation/scoring.py) returns explicit failure states in memory. [Accepted scoring](../runtime/orchestration/scoring.py) retains artifacts only for conforming returned results; failed, not-invoked, and invalid-result invocations contribute diagnostic codes, not durable per-invocation failure records. Full invocation retention below remains unimplemented.
- Extension checks enforce namespaced top-level keys and finite JSON values, not a recursive content allowlist. Nested scorer data can pass these checks without satisfying [Evidence Minimization](EVIDENCE_MINIMIZATION.md#current-implementation-limit). Structural acceptance is not conformance.

## Authority and inputs

A publication-capable scoring request MUST derive from one exact accepted generation and its retained authoritative evidence. Before invocation, the scoring boundary MUST identify and validate, as applicable:

- accepted generation and accepted-snapshot identity;
- canonical execution-boundary fingerprint;
- benchmark, case-set, treatment-set, case, treatment, repetition, request, and observation identities at the grain required by the metric;
- exact metric registration ID/version and metric version;
- exact scorer, parser, or annotation registration identity/version;
- the declared scorer input roles and the exact retained evidence identities supplying those roles;
- applicable golden, observation, telemetry, normalization, failure, availability, schema, and contract identities/versions;
- any registered comparison or primary-endpoint identity needed to interpret the result;
- namespaced comparison-relevant scorer controls already represented by accepted authority.

Source evidence supplied to scoring MUST first satisfy the authority-sensitive validation required by `arcgrav.shared.evidence-validation@1.0.0`. Treatment observation identity and lifecycle authority MUST remain consistent with `arcgrav.shared.run-lifecycle@1.0.0`. Failure candidates and precedence MUST remain consistent with `arcgrav.shared.failure-taxonomy@1.0.0`. Secret or invocation-only material MUST remain outside retained scorer requests and score artifacts according to `arcgrav.shared.transient-invocation@1.0.0`.

A scorer MAY consume only evidence roles declared by its validated registration and active metric registration. An undeclared input, unknown scorer identity/version, incompatible metric/scorer pairing, missing required registration, ambiguous compatibility result, or unauthorized cross-generation evidence reference MUST fail closed before benchmark-owned scoring behavior can establish score authority.

Scoring MUST NOT invoke a runner, treatment execution, or first-time golden execution. When retained golden evidence is a declared scorer input, scoring MAY consume only the already-admitted retained golden evidence for the exact accepted generation.

## Scorer invocation requirements

A conforming scorer invocation boundary MUST:

1. validate the exact metric, scorer/parser/annotation, schema, and contract identities required for the requested scoring operation before invocation;
2. validate that every input evidence item belongs to the exact accepted generation and execution boundary authorized for the score;
3. validate required input-role completeness, uniqueness, integrity, availability, and provenance before passing inputs to benchmark-owned logic;
4. construct the invocation only from declared retained evidence and validated registered rules, without consulting GUI state, ambient files, prior report prose, cached prior scores, or implementation topology as authority;
5. preserve source bytes, identities, availability states, and provenance without mutation;
6. invoke only the registered benchmark-owned parser/scorer or registered annotation procedure authorized for the metric;
7. preserve explicit invocation status and diagnostics for success, unavailability, execution failure, and returned-result conformance failure;
8. retain enough invocation provenance to identify the scorer implementation/procedure and exact registered rule set that produced or attempted to produce the score;
9. reject secret material in retained scorer inputs, diagnostics, outputs, and extensions;
10. validate the returned score artifact before it may contribute to aggregation, accepted finalization, reporting, or reconstruction.

A registered metric MAY define a deterministic disposition for a source state without executing benchmark-owned scoring logic, such as exclusion, non-comparability, not-applicability, or another explicit availability outcome. Such a disposition MUST be fixed by the exact preregistered metric rules, MUST retain its source evidence and reason, and MUST NOT fabricate a scorer-produced value or mark an invocation as successfully executed when no invocation occurred.

A metric rule MAY explicitly assign a numeric value such as zero to a failure or availability state only when that disposition was registered before result evidence was observed. Shared code MUST NOT infer that disposition from the failure class, output contents, missingness, or implementation convention.

## Score artifact requirements

A score artifact that can contribute to accepted evidence MUST retain, directly or through integrity-verifiable references, enough benchmark-neutral evidence to establish:

- this contract ID and version;
- accepted generation, accepted snapshot, and execution-boundary identities;
- benchmark, case-set, treatment-set, case, treatment, and applicable repetition/observation identities;
- exact metric ID/version and metric-registration identity/version;
- exact scorer/parser/annotation identity and version or registered procedure identity;
- declared scoring grain and exact contributing input evidence identities;
- input evidence integrity identities and provenance;
- invocation status and score availability state;
- score value only when the registered rules authorize a value for that state;
- unit, valid-range conformance, directionality, and required companion values defined by the metric registration;
- registered normalization, equivalence, denominator, failure, missing-data, exclusion, and non-comparability rules that materially determine the result;
- benchmark-owned task disposition or namespaced intermediate evidence when produced by registered benchmark logic;
- applicable failure candidates and resolved failure reference where scoring did not produce a normal available result;
- computation or invocation identity sufficient to distinguish this scoring attempt from another authorized attempt;
- score-artifact schema identity/version when a schema applies;
- fixed diagnostic classifications;
- allowlisted namespaced additive extensions.

A score artifact MUST preserve its true evidence grain. Repetition-level observations MAY contribute to a registered case-level score, but the resulting artifact MUST identify the contributing repetitions and MUST NOT represent repetitions as additional independent cases.

A successful numeric or categorical score MUST satisfy the active metric registration's value domain, unit, range, companion-value, and provenance requirements. A returned value that violates those requirements is not a successful score.

An artifact representing unavailable, not-applicable, non-comparable, excluded, completed-non-scorable, failed, missing, or invalid scoring evidence MUST retain that state and an explicit reason. It MUST NOT carry a fabricated successful value merely to satisfy a downstream serializer, aggregator, or report renderer.

Once a validated score artifact enters the accepted lifecycle, it is immutable. A retry or replacement scoring attempt MUST have distinct invocation/computation identity and MUST NOT overwrite prior retained score evidence in place or mutate the source observations from which it was derived.

## Failure and availability behavior

Scoring failures MUST preserve both the scorer invocation evidence and the source evidence that led to the attempt or disposition.

When applicable, shared failure candidates MUST use `arcgrav.shared.failure-taxonomy@1.0.0` without reclassifying benchmark semantics:

- failure to resolve or invoke a required registered scorer/dependency produces `scorer_unavailable` when that class applies;
- a scorer invocation that runs but fails to return a conforming result produces `scorer_failed` when no earlier failure dominates;
- returned scorer output that violates score-artifact conformance produces `score_artifact_invalid`;
- otherwise-valid scoring authority with a required unavailable input MAY produce `required_input_unavailable`;
- completed execution that the registered scoring contract explicitly cannot score MAY produce `completed_non_scorable`;
- benchmark-owned registered logic MAY produce task-layer candidates such as `task_malformed`, `task_refused`, or `task_incorrect`, but shared code MUST NOT infer those classes itself.

All detected candidates MUST remain available to failure resolution. A later task disposition MUST NOT hide an earlier registration, integrity, execution, evidence, scoring, or required-availability failure.

Scorer failure, score unavailability, task incorrectness, exclusion, non-comparability, and numeric zero are distinct states. None implies another unless the exact active metric registration explicitly defines that downstream disposition.

## Authority and lifecycle

Scoring authority enters only after the required accepted treatment/golden evidence exists and the declared scorer inputs have passed applicable validation.

A normal authority transition is:

1. accepted evidence and exact registered metric/scorer authority are identified;
2. declared scorer input roles are validated;
3. benchmark-owned parser/scorer or registered annotation procedure is invoked when required;
4. returned result and score artifact are validated;
5. validated score evidence and explicit failure/availability evidence are handed to later aggregation and accepted finalization.

Scoring does not itself create `AcceptedRun`, report authority or reconstruction authority. Those transitions remain owned by later lifecycle stages.

## Prohibited behavior

A conforming scorer invocation or score-artifact implementation MUST NOT:

- infer benchmark-specific correctness, parsing meaning, semantic equivalence, refusal, malformedness, or partial credit in shared code;
- invoke unregistered scorer/parser/annotation behavior or accept a caller-supplied callback as publication authority;
- score mutable or unvalidated source evidence as though it were accepted retained evidence;
- mutate treatment observations, golden evidence, run plans, execution boundaries, metric registrations, scorer registrations, or prior score artifacts;
- rerun treatment execution or perform first-time golden execution during scoring;
- use prior score artifacts, report prose, GUI state, current directory contents, filenames, benchmark names, provider names, or implementation topology as undeclared authority;
- silently drop failed, missing, unsupported, unavailable, non-comparable, excluded, or completed-non-scorable source evidence;
- convert an unavailable or failed score to zero unless the active preregistered metric rule explicitly requires zero;
- treat a successfully empty retained response as missing solely because its byte length or collection length is zero;
- let namespaced extensions replace required shared identity, integrity, availability, failure, or provenance evidence;
- retain secret material or reversible secret derivatives in scorer requests, artifacts, diagnostics, or extensions;
- permit score-artifact existence alone to establish accepted-run, report or verification authority.

## Extension rules

Scorer and score-artifact extensions MUST be namespaced, additive, validated where registration is required, and benchmark-neutral at the shared boundary.

Benchmark-owned extensions MAY retain parser intermediates, task-specific labels, semantic-equivalence traces, annotations, or metric-specific companion evidence when the active registration authorizes them. Those extensions MAY contribute to benchmark-owned scoring meaning, but they MUST NOT replace shared identity, input provenance, availability, failure, contract, schema, or accepted-generation requirements.

Additional scorer input roles MUST be declared by validated registration before accepted use. An extension MUST NOT introduce undeclared evidence lookup, weaken input-role validation, bypass source integrity checks, smuggle secrets or comparison-relevant controls outside accepted identity, or reinterpret an existing published contract field.

A breaking change to scorer invocation authority, required score-artifact semantics, or the distinction among successful, failed, unavailable, non-comparable, excluded, and non-scorable results requires a new major contract version.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- unknown or incompatible metric/scorer/contract identities fail closed before benchmark-owned scoring establishes authority;
- scorer inputs are restricted to declared roles from the exact accepted generation;
- source observations and golden evidence are not mutated by scoring;
- first-time golden or treatment execution cannot occur through the scorer boundary;
- missing and unavailable required inputs remain explicit and are not converted to successful empty values;
- scorer unavailability, scorer failure, invalid score artifacts, completed-non-scorable outcomes, task-layer dispositions, and successful scores remain distinguishable;
- numeric zero appears only when produced by scoring or explicitly required by the preregistered metric disposition;
- returned values outside registered domains/ranges or missing required companion evidence are rejected;
- repetition-level inputs cannot be misrepresented as independent case-level observations;
- benchmark task meaning enters only through validated registered benchmark-owned logic;
- prior score artifacts are immutable and retries/replacements receive distinct invocation/computation identity;
- secret material is absent from retained scorer inputs, diagnostics, score artifacts, and extensions;
- validated score artifacts do not by themselves create accepted-run, report or reconstruction authority.

All retained scorer inputs, artifacts, diagnostics, and extensions MUST follow
[Evidence Minimization](EVIDENCE_MINIMIZATION.md). Registered scoring meaning does
not authorize surrounding logs or unrelated identifying content.
