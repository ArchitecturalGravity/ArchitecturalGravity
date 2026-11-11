# Run Planning and Observation Lifecycle Contract

- Contract ID: `arcgrav.shared.run-lifecycle`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared application/runtime planning, accepted execution orchestration, runner adapters, and evidence consumers that reason about planned treatment observations

## Purpose

This contract governs complete run planning, immutable acceptance, treatment-request construction, and terminal observation reconciliation. It establishes planning and observation authority, not benchmark semantics, provider protocol, scoring, report interpretation, or implementation topology.

## Authority and inputs

Planning authority MUST derive from validated registrations, the registered case set, the registered treatment set, repetition intent, and one canonical execution boundary. Comparison-relevant non-secret controls MUST already be represented by that execution boundary before the plan is accepted. Secret and invocation-only values are governed by `arcgrav.shared.transient-invocation@1.0.0` and MUST NOT enter canonical plan or snapshot identity.

The plan MUST identify the complete case x treatment x repetition x execution-boundary matrix that the accepted generation is authorized to execute. Each planned treatment observation MUST have stable case, treatment, repetition, request, observation, and execution-boundary identities sufficient to distinguish it from every other planned observation in the same plan.

Where golden authority is required, admission is governed by `arcgrav.shared.golden-execution@2.0.0`. Treatment requests MUST NOT be constructed or submitted until the required golden gate is admitted.

Treatment execution through a runner adapter MUST use a compatible published runner-invocation contract, including `arcgrav.shared.runner-invocation@2.0.0` when version-compatible.

## Planning requirements

A conforming planning boundary MUST:

1. validate the registrations and identities required to enumerate the run;
2. fully materialize the complete planned case x treatment x repetition x execution-boundary matrix before acceptance;
3. assign deterministic stable identities to the run plan and each planned request/observation;
4. reject duplicate or ambiguous case, treatment, execution-boundary, request, or observation identities where uniqueness is required;
5. preserve exact prompt/input byte identity or an integrity-verifiable reference for every planned request;
6. include every comparison-relevant non-secret control required to reproduce request construction and lifecycle ordering;
7. keep namespaced extensions additive and canonical when they are comparison-relevant;
8. produce no accepted execution authority until the complete plan is accepted into an immutable snapshot.

A planner MUST NOT omit planned matrix members because of anticipated failure, unsupported capability, expected score, cached prior output, frontend state, or implementation convenience. Any registered exclusion that legitimately narrows planning MUST itself be explicit comparison authority before plan construction and MUST remain traceable in retained evidence.

## Acceptance and immutable snapshot behavior

Acceptance MUST freeze exactly one plan together with the exact validated source and execution-boundary identities on which that plan depends.

An accepted snapshot MUST:

- identify its governing run plan and execution boundary;
- preserve the accepted case, treatment, repetition, request, and observation identities;
- preserve the applicable contract/schema/registration identities and versions;
- preserve comparison-relevant source identities needed for pre-execution revalidation;
- exclude secret material and transient invocation values;
- be immutable after acceptance.

Only an accepted snapshot MAY authorize accepted execution. Before accepted execution begins, mutable comparison-relevant sources and referenced artifacts MUST be revalidated against the accepted snapshot. A mismatch, unavailable required source, incompatible contract, or failed integrity check MUST fail closed and MUST NOT be repaired by rewriting the accepted snapshot.

## Observation lifecycle

The authoritative observation set for a started treatment phase is the exact observation matrix declared by the accepted plan. A conforming orchestrator MUST materialize each treatment request from accepted snapshot authority and MUST preserve clean request/process/conversation/session/cache/memory/retry/tool state according to the accepted boundary and runner contract.

For each planned observation after treatment execution has begun, lifecycle evidence MUST distinguish at least these conditions without conflation:

- not started;
- started and awaiting terminal runner outcome;
- terminal completed;
- terminal failed;
- terminal timed out;
- terminal cancelled;
- terminal unsupported;
- required terminal observation missing or unavailable during reconciliation.

Transient in-process states MAY remain private, but retained/finalized evidence MUST make the terminal condition or explicit non-production/unavailability condition reconstructable for every planned observation whose treatment phase was authorized to begin.

A normalized runner result MUST preserve the planned request and observation identities unchanged. An adapter, frontend, scorer, report generator, or persistence layer MUST NOT renumber, merge, split, replace, synthesize, or silently drop planned observations.

A genuinely empty completed response MUST remain distinguishable from missing, unavailable, unsupported, failed, timed-out, cancelled, or malformed response evidence. This contract does not decide whether a completed response is scorable.

## Reconciliation and lifecycle authority

After treatment execution begins, reconciliation MUST compare retained terminal observation evidence against the exact accepted planned matrix.

Reconciliation MUST:

- detect missing, duplicate, unexpected, identity-mismatched, or nonterminal observation evidence;
- retain explicit availability and failure state rather than synthesizing response bytes or score values;
- preserve every started observation's terminal evidence when available;
- preserve the distinction between a run blocked before treatment and a started treatment phase with incomplete observations;
- produce deterministic blocking evidence when the accepted observation lifecycle cannot be reconciled.

A required golden-gate failure occurs before treatment authorization and therefore MUST yield zero treatment observations rather than a synthesized matrix of failed or missing treatment observations.

Observation reconciliation does not create scoring authority. Only later compatible contracts may authorize scorer invocation, evidence finalization, terminal `AcceptedRun | BlockedRun` classification, reporting, or verification.

## Evidence and observable results

Run-planning and observation-lifecycle evidence MUST retain, where applicable:

- this contract ID and version;
- run-plan identity and canonical plan integrity identity;
- accepted-snapshot identity;
- execution-boundary fingerprint;
- validated benchmark/case-set/treatment-set/repetition identities and versions;
- complete planned observation count and stable per-observation identities;
- per-request prompt/input byte identities or integrity-verifiable references;
- accepted source/artifact identities required for revalidation;
- golden requirement and admission reference when applicable;
- treatment-phase authorization state;
- per-observation start and terminal status/availability evidence;
- runner contract identity/version and adapter identity for started observations;
- response byte identity or explicit unavailability state;
- reconciliation results for missing, duplicate, unexpected, mismatched, or nonterminal evidence;
- fixed diagnostic classifications;
- allowlisted namespaced additive extensions.

Evidence MUST be sufficient to establish that complete planning preceded acceptance, acceptance preceded accepted execution, required golden admission preceded every treatment observation, and every started planned observation is accounted for during reconciliation.

## Prohibited behavior

A conforming implementation MUST NOT:

- execute an accepted treatment that is absent from the accepted plan;
- add, delete, replace, or mutate planned observations after acceptance;
- accept caller-supplied plan artifacts, exclusions, request identities, observation identities, golden bytes, adapter factories, scorer callbacks, or persistence hooks as undeclared publication authority;
- derive planning decisions from GUI selection state, current working directory, filenames, benchmark names, provider names, prior scores, or cached output;
- begin treatment construction or submission before required golden admission;
- convert missing, failed, timed-out, cancelled, unsupported, unavailable, malformed, or nonterminal observations into successful empty responses;
- synthesize treatment observations for a run blocked before treatment authorization;
- let scoring, reporting, reconstruction, verification, or frontend code retroactively establish planning or observation authority;
- place secret or transient invocation material in plan, snapshot, request identity, observation identity, retained diagnostics, or extensions.

## Extension rules

Planning and observation extensions MUST be namespaced, additive, benchmark-neutral at the shared boundary, and canonical when comparison-relevant.

Extensions MAY add registered planning dimensions, stricter identity data, additional observation telemetry, or additional explicit lifecycle states when those additions preserve the required shared distinctions.

An extension MUST NOT remove required matrix members, weaken immutable acceptance, bypass golden-before-treatment ordering, alter runner terminal-status meaning, hide missing evidence, or create score/report authority.

A breaking change to planning completeness, acceptance authority, observation identity, or lifecycle reconciliation meaning requires a new major contract version.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- the complete registered case x treatment x repetition x boundary matrix is materialized before acceptance;
- duplicate or ambiguous planned identities fail closed;
- accepted snapshots are immutable and source drift is detected before accepted execution;
- transient secrets do not enter plan or snapshot identity;
- required golden failure produces zero treatment observations;
- treatment requests are materialized only from accepted plan authority and begin from required clean state;
- each started planned observation resolves to one retained terminal condition or explicit reconciliation failure;
- missing, duplicate, unexpected, mismatched, and nonterminal observation evidence are detected without synthesis;
- a genuinely empty completed response remains distinct from unavailable or failed evidence;
- retained evidence proves planning-before-acceptance and golden-before-treatment ordering;
- namespaced extensions cannot weaken planning completeness, accepted immutability, or observation reconciliation.

## Current plan extension admission

Run-plan extensions admit only explicitly supported boolean execution flags,
validated benchmark content selection and the current validated runtime advisory.
Unknown extensions and legacy advisory qualifiers are rejected before acceptance
and retention. The plan is validated again during archive admission; changing an
archive format label does not make legacy or identifying plan metadata admissible.
All retained plan and observation evidence MUST follow
[Evidence Minimization](EVIDENCE_MINIMIZATION.md).
