# Treatment measurements

- Contract ID: `arcgrav.shared.treatment-measurements`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared adapters, telemetry, frontend projections, reporting and reconstruction

This contract preserves source meaning, availability, and exact evidence for
attempt consumption and treatment resource totals.

## Attempt measurement and aggregation

The namespaced `arcgrav.telemetry:attempt-measurements` extension binds
`arcgrav.shared.schema.attempt-measurements@1.0.0` to one observation attempt.
Multiple attempts use `arcgrav.telemetry:attempt-series`, keyed by exact attempt
number. Producers retain source SHA-256 evidence, extraction method, runtime
version, counter meaning and independent availability. Runtime counters are not
billing usage. Cached input/reasoning subsets are never added to their parent.

Treatment sums include all authorized measured attempts, including failed
attempts and retries. Missing attempts/components yield unavailable or partial
values with measured/observed attempt and planned observation coverage. Source,
unit, kind, runtime version, counting rules, comparison context and pricing
identity must agree before pooling. Attempt series must cover every exact
retained attempt number and may not conflict with a single-attempt envelope.
Tool counts deduplicate actual invocation identities within each attempt;
proposed events do not count. Failed calls require observed failed terminal
outcomes. Unknown outcomes and incomplete traces remain partial/unavailable;
complete empty traces establish zero. Conflicting identities/outcomes fail.

Duration uses first authorized treatment attempt start and last terminal UTC
wall-clock timestamp, including overlap, waiting and retries. Incomplete coverage
is labeled elapsed/incomplete; framework phases remain outside the boundary.

## Cost and comparison

Reported cost and estimated cost remain separate. Estimates require applicable
billing component evidence, retained price identity/date/currency and formula.
Applicable model, tokenizer, request framing, usage source and boundary must
be declared compatible; missing comparison context cannot establish prices
or baseline savings.
Opaque CLI counters establish no dollar amount. Registered efficiency ratios
retain numerator/denominator and formula identity; zero denominators and
incompatible baselines produce unavailable/non-comparable evidence.

Results and canonical/human reports use the same shared aggregation of exact
accepted-generation evidence. Reconstruction revalidates sources and hashes.

Extensions are namespaced and additive. They cannot replace shared roles,
alter availability or counting semantics, or grant unknown payloads authority.
Conformance must distinguish real zero from missing values, validate source
integrity, and cover independent components, overlap, duplicates, unknown tool
outcomes, retries, incomplete coverage, wall-clock boundaries, applicable prices,
registered ratios and incompatible baselines. Breaking behavioral changes
require a new major version.

## Session measurements

The additive `arcgrav.telemetry:session-metrics` extension uses
`arcgrav.shared.schema.session-metrics@1.0.0`. It retains session identity, model,
reasoning effort, extended independently available metrics and average sample
numerators/denominators. Shared pooling sums counts/spans, maximizes context
window, unions exact tool names, and weights average samples. Recorded session
spans are distinct from treatment wall-clock duration. Measurement-source
projections retain verified bytes and invocation-local session/observation/attempt
binding. Reconstruction never selects a current log from account storage. Extraction
uses measurement-source/1 with version 4.0.0 and rejects legacy raw session
representations. Original session/account identifiers and raw log bytes are absent.

Session aliases establish correlation only within their observation and attempt.
Aggregation keys them by `(observation_id, attempt, alias)` and rejects duplicate
observation inputs. Exact source/thread matching occurs transiently at capture;
a retained local alias does not prove native-session uniqueness across observations.
Reconstruction must not claim that unavailable cross-observation proof.

## Adapter-neutral attempt sources

The `arcgrav.telemetry:attempt-sources` extension binds each retained source
SHA-256 to an `agmark.attempt-source.v1` record containing `runtime_version`,
`tokens`, `tool_events` and `trace_complete`. Token roles are registered numeric
counters; completeness is boolean. Tool events contain invocation-local `call-N`
and `tool-N` aliases and admitted terminal statuses, without arguments or outputs.
Only sources linked to the observation attempt or attempt series are admitted.
Reconstruction rederives the exact attempt-measurement envelope from these bytes;
raw stdout is never a fallback source.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
