# Evidence minimization

- Contract ID: `arcgrav.shared.evidence-minimization`
- Version: `1.0.0`
- Status: published
- Compatibility scope: every current producer, durable artifact, observation, telemetry profile, report and archive consumer

This policy is mandatory before persistence, not an optional export filter.
There is no fallback to older raw evidence.

## Current implementation limit

The [scorer boundary](../evaluation/scoring.py) checks extension names and JSON
compatibility, but does not recursively admit their contents against a registered
allowlist. Nested arbitrary data can reach score artifacts; ARB comparison metadata
currently includes expected/observed values, identifiers, and source keys.
This is a gap against the policy below, not permission to retain excluded data.
Schema acceptance or archive format `4` alone does not prove minimization.

## Permitted retained evidence

- Registered benchmark, adapter, runtime and model identities and versions;
  accepted run, treatment, observation and attempt relationships.
- Explicit relevant controls and their declared/observed distinctions, measured
  outcomes, availability, completeness, source/extraction versions and units.
- Integrity hashes for relevant resources, binaries and retained source bytes.
- Exact scoring inputs, expected golden output and extracted model answers
  required by registered scoring. These are purpose-bound scoring artifacts,
  not permission to retain surrounding logs or conversation history.
- Sufficient structured source records to rederive measurements: typed counters,
  event order, relative timing, tool categories and outcomes, and consistent
  invocation-local correlation aliases. Source records remain rich enough to
  explain individual measurements, missing data and conflicting observations.
- Confined references relative to the AgMark root or declared adapter runtime
  directory. The root is logical: its host filesystem location is transient.

## Excluded evidence

Personal/account/device identifiers, absolute host paths, home and workspace
locations, private endpoints, ambient environment values, credentials, arbitrary
configuration dumps, unrelated telemetry fields, raw session logs, raw OTLP,
raw diagnostic streams and free-form exception details MUST NOT be retained.
Neither a redacted string nor an unkeyed hash of unrelated identifying data
makes that data admissible. A digest is retained only for a relevant integrity
purpose. No unknown field gains permission merely because it is namespaced.

Required execution locators and private configuration may be used transiently
for launch and equality checks. They are not serialized into accepted identity,
observations, manifests, reports or archives. Such comparisons retain an explicit
result and limitation, not the private snapshot or a fingerprint of that snapshot.
Offline readers cannot independently establish equality of disposed private state.

## Production and reconstruction

Producers project allowlisted, type-checked fields before any durable write.
Correlation identifiers are scoped aliases, not hashes of original account or
session identifiers. Time needed for within-session measurements is relative;
framework run timestamps needed for lifecycle ordering remain permitted.
Malformed or unsupported source content yields explicit partial/unavailable
measurements rather than retaining raw content to recover it later.

Source hashes identify the exact retained projection. The projection must carry
its version and enough source ordering and binding to reproduce extraction;
a normalized scalar alone is not a substitute. Excluded transport channels carry
no raw-content digest or byte payload. Measurements reference their minimized
source projection; scoring answers retain exact byte identity separately.

Session, telemetry and deep telemetry share this exclusion boundary. A deeper
profile changes the relevant measurement surface, never the privacy policy.
Archive/report reconstruction validates the current contract and all required
source identities; unsupported old representations fail closed rather than being
silently read, upgraded, repaired or merged with current records.

Conformance must include identifying sentinels in accepted and rejected fields,
unknown extensions, malformed values, failure diagnostics, native and WSL paths,
all capture profiles and complete retained artifact scans. It must also establish
that necessary scores and measurements can still be derived from retained bytes.

## Current representation identities

- Runner invocation and golden execution: `2.0.0`.
- Golden observation, runner execution evidence and provider-request replay schemas: `2.0.0`.
- Codex measurement source: `measurement-source/1`, extraction `4.0.0`.
- Telemetry sanitizer: `agmark.safe-telemetry.v2`; capture:
  `agmark.telemetry.capture.v2`; protocol: `agmark.original-telemetry.v2`;
  profile and normalizer: `2.0.0`.

These identities select the current formats, not compatibility with earlier raw
representations. Unsupported versions remain unavailable or rejected.

The serialized `AgMark/` resource prefix is a logical AgMark-root namespace,
not an additional host path segment. Existing registered resource resolution
continues to enforce root containment beneath that marker.

Numeric byte counts may be retained when they directly establish a registered
output limit, collection health or measurement boundary. For example, golden
stderr byte count explains output-limit enforcement. Such a count does not
authorize retaining that stream, its content hash or arbitrary channel metadata.

Runtime release labels retain only a numeric major.minor.patch core (or explicit
unavailability). Prerelease/build suffixes are invocation-only. Exact executable
identity uses the executable SHA-256 where that capture surface observes it; a
numeric release label is not proof of binary equivalence. Session execution keeps
a planned full version in transient launch selection when needed and rejects
full-version drift, including suffix changes. Without that transient binding it
fails closed on a suffixed installed release. Capture/replay exact-version checks
continue to use transient full labels. Custom builds must not acquire audited
stock-runtime provenance merely by projecting to the same numeric core.
