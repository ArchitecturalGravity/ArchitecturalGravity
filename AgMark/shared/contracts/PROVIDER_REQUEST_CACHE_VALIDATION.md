# Provider-request cache validation contract

- Contract ID: `arcgrav.telemetry:provider-request-cache-validation`
- Version: `2.0.0`
- Status: published
- Compatibility scope: isolated replay producers, Results, retained history, reporting and reconstruction that explicitly support this identity

## Replay authority

This contract governs isolated post-treatment configuration-equivalent replay
evidence, independently of `arcgrav.shared.treatment-measurements@1.0.0`.
Existing scored contracts, versions, scalar roles, retained extraction meanings,
resources, correctness, costs, tools, counts and denominators retain their meaning.

Every replay retains validation, accepted observation, treatment, repetition and
generation identity; `separate_invocation=true`, `included_in_score=false`, and
`validation_scope=configuration_equivalent_replay` are mandatory. Scheduling
requires all scored invocations to have terminated and finalized scored evidence
to remain immutable. An isolated restorable starting state is required; absent
authority yields unavailable validation with `replay_start_state_not_reproducible`.

Expected and observed accepted-boundary and additional starting-state values,
matched/unavailable fields and mismatch reasons are retained. Ordinary relevant
differences produce `non_comparable`; missing fields produce `partial` or
`unavailable`. Runtime identity independently preserves `exact_stock`,
`instrumented_equivalent`, `non_comparable`, `unavailable`. Instrumented
equivalence requires separately identified binaries, patch and controlled evidence
for request content, cache keys, transport, continuation, ordering, retries and
provider-visible metadata. Instrumentation never implies exact stock bytes.

## Request evidence

Normalized ordered requests are distinct from replay summaries and treatment
summaries. Each field retains its value, availability, source, method, reason and
evidence references. Unavailable values are null; absent observations never
become zero, empty strings or false. OTLP capabilities are independent and require
controlled evidence before enabling dependent fields. Timestamp/ordinal proximity
or similar counters cannot establish request/completion identity.

Request duration starts when a finalized provider request is committed for
transmission and ends at its deterministically correlated terminal completion.
Connection setup, send timing, transport spans and scored session timing do not
establish that interval. Unproven lifecycle duration remains unavailable.

Uncached input is input minus cached input only for available counters with
cached input no greater than input. An anomaly remains retained; derived values
are unavailable. Cache-read fraction requires positive input. Warmup reuse
requires an observed positive warmup write explicitly paired with the immediately
following generation. Neither warmup existence nor writes follow from cache reads.

## Aggregation and consumers

Requests aggregate within one replay before comparable replay summaries aggregate
within one treatment. Each numeric summary names its statistic and contributing
field/replay coverage. Treatment coverage distinguishes scored, planned, attempted,
completed, comparable, lifecycle-available and token-available counts; comparable
coverage with zero scored observations is unavailable. Repeated comparisons expose
mean/median/min/max and raw replay values rather than unlabeled sums. Sampling
retains policy, reason and selected observation IDs; launched processes do not
prove full coverage.

Results, history, reporting and reconstruction consume integrity-validated typed
records. They retain separate replay identity, request inspection, availability,
capabilities, statistics, coverage, provenance, configuration/runtime comparisons
and limitations. Replay values never replace or enter scored values. Raw OTLP,
credentials, prompt/response text and unrelated content are excluded. Replay
measurements describe configuration-equivalent requests and demonstrated
capabilities, not exact scored trajectories, shared cache identity or physical eviction.

Schema identities are `arcgrav.shared.schema.provider-request-cache-validation@2.0.0`
and `arcgrav.shared.schema.provider-request-cache-treatment@2.0.0`. Consumers reject
unknown versions, invalid structure/linkage, altered statistics or evidence.
Extensions require separately published additive namespaced authority and cannot
weaken these obligations. Positive and negative controlled conformance establishes
availability, arithmetic, identities, correlation, coverage and scored separation.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.

Private ambient configuration equality is checked only during the live selected-host
comparison. Evidence retains `ambient_configuration_equal` with explicit provenance;
startup evidence declares `ambient_state_validation=transient_equality_only`. Private
profile/instruction/environment fingerprints are not retained. Offline replay admission
checks linkage, counters, admitted controls and declared comparison outcomes, not the
disposed private snapshot.
