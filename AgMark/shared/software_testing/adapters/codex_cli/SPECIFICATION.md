# Codex scored-session parity tests Specification

Parent: [specification](../SPECIFICATION.md).

## Session telemetry contract

**R001.** Scored-session coverage SHOULD distinguish retained-record parsing, token usage, cache policy, tools, timing, and measurement construction, with fewer facade-level integration/reconstruction cases.

**R002.** Extractor differential/regression tests MUST prove equivalent pre/post-refactor serialized session records, roles, token values, cache telemetry/policy, thread identity, availability, source hashes, tool events, timing estimates, and reconstruction results.

**R003.** Regression tests MUST prove identical scored Results projections and report resource values.

**R004.** Scored tests MUST preserve final cumulative counter authority and earliest-retained-snapshot meaning without requiring fresh cached input to be zero.

**R005.** Cache-key wire-policy tests MUST remain independent and verify the existing fresh-root, within-invocation, concurrent, helper, and Guardian namespace invariants.

**R006.** Scored parity evidence MUST precede provider-request validation implementation.
