# Transient Invocation Contract

- Contract ID: `arcgrav.shared.transient-invocation`
- Version: `1.0.0`
- Status: published
- Compatibility scope: frontends, shared runtime, golden execution, and runner adapters that handle invocation-only or secret values

## Purpose

This contract governs values needed for invocation but forbidden from canonical comparison identity and retained evidence: credentials, secret-bearing source handles, and other explicitly registered invocation-only values.

## Classification

A value is transient invocation material when a registration or owning specification marks it invocation-only, or when retaining it could disclose authentication material, credentials, session secrets, private tokens, cookies, or equivalent secret state.

A non-secret classification of how credentials are obtained MAY be comparison-relevant when explicitly registered. The secret value, a secret-bearing locator/handle, and any resolved credential material MUST remain transient and MUST NOT be promoted into accepted identity or retained evidence.

Consumers MUST NOT infer that arbitrary undeclared values are transient merely to avoid canonical identity requirements.

## Behavioral requirements

Transient invocation material MUST:

1. enter only through an explicitly permitted invocation boundary;
2. be resolved as late as practical, after accepted identity and compatibility checks that do not require the secret value;
3. be scoped to the minimum component and duration necessary for the invocation;
4. be supplied separately from canonical execution-boundary and retained evidence records;
5. never be used to silently choose a model, provider, runtime, access method, environment, retry policy, tool policy, or other comparison-relevant control;
6. be excluded from hashes, fingerprints, accepted snapshots, run plans, artifact indexes, reconstruction manifests, reports, normalized observations, and namespaced retained extensions;
7. be excluded before persistence from argv evidence, environment summaries, logs, stdout/stderr diagnostics, exceptions, validation issues, GUI diagnostics, and conformance output;
8. have references released or invalidated after the invocation boundary no longer needs them where the host/runtime permits.

A component MUST use only credential sources and transient-input classes declared by its registration. Missing, unresolved, unauthorized, or unsupported transient material MUST fail closed at the owning lifecycle stage. A consumer MUST NOT search arbitrary environment variables, credential stores, files, browser state, shell history, or parent-process state as an undeclared fallback.

Passing a transient value to a child process or provider is permitted only when required by the registered invocation mechanism. Retained command/environment evidence MUST omit transient values entirely and preserve only allowlisted relevant controls; it MUST NOT contain identifying placeholders, secret values or reversible encodings.

## Failure and redaction behavior

Failure to redact secret material is an evidence-safety failure. The affected evidence MUST NOT be promoted to accepted, report or reconstruction authority.

Errors about transient material MAY identify the source class or stable non-secret classification, but MUST NOT reveal the secret, secret-bearing handle, full credential locator, or recoverable derivative.

A frontend or adapter MUST NOT repair a missing credential by persisting it, adding it to canonical identity, or silently switching to a different credential source.

## Extension rules

Additional transient material classes MUST be explicitly registered and namespaced. Extensions MUST remain invocation-only, additive, and non-authoritative for benchmark semantics.

An extension MUST NOT use the transient channel to smuggle comparison-relevant non-secret controls around canonical identity, registration validation, or launch-environment selection.

## Conformance expectations

A conforming implementation MUST demonstrate that:

- transient inputs are absent from canonical serialization and retained evidence;
- only registered transient source classes are accepted;
- undeclared ambient fallback is rejected;
- redaction covers commands, environment summaries, diagnostics, exceptions, observations, reports, and extensions;
- changing a secret value alone does not change comparison identity;
- changing a registered non-secret comparison control still changes identity even if delivered alongside transient material;
- missing or unresolvable transient input fails closed without persistence or silent substitution;
- provider-free tests can exercise the transient boundary with synthetic secret values and prove they do not appear in retained artifacts.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
