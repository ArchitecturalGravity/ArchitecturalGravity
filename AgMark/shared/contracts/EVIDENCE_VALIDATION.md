# Evidence Validation Contract

- Contract ID: `arcgrav.shared.evidence-validation`
- Version: `1.0.0`
- Status: published
- Compatibility scope: shared validation, accepted runtime finalization, evaluation, reporting, reconstruction, and other authority-sensitive consumers of retained benchmark evidence

## Purpose

This contract governs validation before retained evidence authorizes a lifecycle transition, accepted finalization, scoring, reporting, reconstruction, or another authority-sensitive use. Validation checks declared identity, integrity, provenance, lifecycle, availability, and compatibility. It does not repair evidence, infer benchmark semantics, or create missing authority.

## Current implementation limit

The current [validation result](../validation/core.py) carries code, source, message, optional JSON Pointer, and optional schema identity. It sorts by source, pointer, code, schema ID/version, then message. This differs from the lifecycle-first ordering below and omits dedicated rule, lifecycle, blocking-status, and expected/observed fields. Its `valid` boolean and structural schema are not evidence of full behavioral conformance.

## Authority and inputs

Evidence validation MUST operate against an explicit validation context that identifies the authority being checked. Depending on lifecycle stage, that context MUST include the exact accepted generation, accepted snapshot or other governing source identity, execution-boundary fingerprint, required artifact/evidence roles, and applicable schema, contract, and registration identities.

A validator MUST resolve durable behavioral authority only through published compatible contracts. Structural authority MUST come from the exact declared schema identity/version where a schema applies. Registered benchmark or adapter extensions MAY add requirements only through validated registrations and namespaced extension points.

When validation consumes evidence governed by another published shared contract, it MUST validate the declared exact contract identity/version before relying on that evidence. In particular, planning and observation evidence MAY be governed by `arcgrav.shared.run-lifecycle@1.0.0`, golden evidence by `arcgrav.shared.golden-execution@2.0.0`, runner observations by `arcgrav.shared.runner-invocation@2.0.0`, failure evidence by `arcgrav.shared.failure-taxonomy@1.0.0`, and transient-material exclusions by `arcgrav.shared.transient-invocation@1.0.0`.

An unpublished contract family, missing contract declaration, unknown contract ID/version, or ambiguous compatibility result MUST NOT be replaced by inferred behavior from current code, filenames, neighboring specifications, frontends, tests, or retained prose.

## Validation requirements

A conforming evidence validator MUST, for every authority-sensitive validation request:

1. identify the exact validation context and required evidence scope before evaluating retained evidence;
2. validate every declared contract and schema identity/version needed to interpret that evidence;
3. validate that retained evidence identities belong to the exact accepted generation and governing execution boundary they claim to represent;
4. verify required SHA-256 identities or equivalent integrity-verifiable references against the exact retained bytes or referenced artifact when those bytes/references are available for validation;
5. validate provenance links from retained evidence to the accepted plan, accepted snapshot, registration, runner, golden, scorer, metric, artifact, or other declared source authority applicable to that evidence role;
6. validate required path/reference confinement and reject traversal, symlink escape, unauthorized external references, or role/path substitution where the owning authority requires confinement;
7. preserve and validate explicit availability states, including distinctions among retained, not-produced, unavailable, invalid, excluded, missing, not-applicable, non-comparable, completed-non-scorable, and available states where applicable;
8. validate lifecycle chronology and authority ordering, including planning before acceptance, required golden admission before treatment, treatment terminalization before dependent scoring, and evidence validation before accepted finalization;
9. reconcile evidence that is required to be complete against its authoritative declared set, including the exact accepted planned observation matrix when treatment execution was authorized;
10. detect required-role omissions, duplicate identities, unexpected identities, identity mismatches, nonterminal evidence at a terminal boundary, and incompatible cross-artifact references;
11. preserve accepted and blocked evidence as distinct terminal authorities and reject any artifact set that mixes, promotes, or aliases blocked diagnostics as accepted evidence;
12. reject secret or secret-bearing transient material on durable evidence surfaces governed by `arcgrav.shared.transient-invocation@1.0.0`;
13. validate namespaced extensions as additive and non-overriding, preserving unknown extension payloads only where structure and the current retention policy permit, without granting them shared authority;
14. return deterministic validation results without mutating, normalizing, repairing, deleting, synthesizing, or reserializing source evidence as a means of making it valid.

Schema validity alone MUST NOT establish evidence validity. A structurally valid artifact that has the wrong generation, hash, chronology, provenance, lifecycle state, contract version, or authority relationship is invalid for the affected authority-sensitive use.

A genuinely empty retained value that is valid under its owning contract MUST remain distinguishable from missing or unavailable evidence. Validation MUST NOT infer missing evidence solely from zero byte length or an empty collection when the owning authority permits an empty successful value.

## Deterministic validation results

Every validation request MUST produce one deterministic outcome:

- `valid`: no blocking validation issue exists for the requested authority transition or evidence use;
- `invalid`: one or more blocking validation issues prevent the requested authority transition or evidence use.

Validation issues MUST be deterministic and MUST retain:

- a stable issue code;
- the affected source/evidence identity;
- the validation rule or requirement identity;
- path, artifact reference, or JSON Pointer when applicable;
- the expected authority or invariant in non-secret form;
- the observed non-secret condition when safe to retain;
- the owning lifecycle stage or authority-sensitive use;
- blocking status;
- fixed diagnostic classification;
- applicable contract/schema/registration identity and version;
- allowlisted registered namespaced extensions when present.

Issue ordering MUST be independent of filesystem enumeration, dictionary order, frontend order, callback timing, or exception arrival. Validators MUST order issues canonically by lifecycle/authority scope, affected identity, stable issue code, path or pointer, and stable diagnostic identity, using canonical bytewise ordering for serialized identifiers when a tie remains.

Supplemental non-blocking diagnostics MAY be returned, but they MUST be clearly distinguished from blocking validation issues and MUST NOT upgrade or downgrade the validation outcome.

## Lifecycle and failure behavior

Validation is a gate on an authority transition; it does not own the transition itself. The caller responsible for discovery, preflight, planning, execution, finalization, reporting, reconstruction, or another lifecycle stage MUST apply an `invalid` result by blocking the local transition, marking the affected evidence invalid/unavailable as required by that owning stage.

Where validation issues also create failure candidates, classification and precedence MUST follow `arcgrav.shared.failure-taxonomy@1.0.0`. Validators MUST preserve the most specific applicable earlier-layer condition rather than collapsing every validation problem into `evidence_invalid`. For example, incompatible contract/schema authority, artifact-integrity mismatch, identity mismatch, source drift, and missing/duplicate/unexpected/nonterminal evidence remain distinct failure candidates under the failure taxonomy.

Validation MUST NOT convert an invalid result into a score value, successful empty evidence, accepted artifact authority, report authority, or successful completion. Revalidation after mutable-storage reuse MUST evaluate the retained evidence as it exists at the time of the authority-sensitive use; a prior successful validation result MUST NOT substitute for current integrity validation when mutation could have invalidated authority.

## Evidence and observable results

Retained validation evidence, when validation results themselves are persisted, MUST identify:

- this contract ID and version;
- validation request/context identity;
- accepted generation and execution-boundary identity when applicable;
- validated evidence/artifact roles and identities;
- exact applicable contract, schema, and registration identities/versions;
- validation outcome;
- canonically ordered blocking issues and supplemental diagnostics;
- integrity-check results and hash identities where applicable;
- chronology, completeness, and accepted/blocked-separation checks that were required;
- validation implementation identity/version when retained for reconstruction;
- validation timestamp or lifecycle position when required by the owning artifact;
- fixed diagnostic classifications;
- allowlisted registered namespaced extensions.

Retained validation results are diagnostic/authority-gating evidence. They do not by themselves constitute benchmark-performance evidence or establish task correctness.

## Prohibited behavior

A conforming validator MUST NOT:

- repair malformed registrations, evidence, reports, score artifacts, or retained artifacts;
- infer or synthesize missing values, observations, hashes, identities, scores, or availability states;
- substitute cached golden output, neighboring observations, prior-run artifacts, expected answers, report prose, or frontend state for required evidence;
- treat current implementation behavior, tests, filenames, module topology, or directory layout as undeclared behavioral authority;
- mutate source evidence to make hashes, identities, chronology, schemas, or contracts pass;
- silently discard duplicate, unexpected, mismatched, unavailable, invalid, or nonterminal evidence;
- reinterpret blocked evidence as accepted evidence;
- permit namespaced extensions to override shared identity, integrity, lifecycle, failure, availability, secret, or reconstruction requirements;
- retain secret material or reversible secret derivatives in validation issues, diagnostics, expected/observed fields, or extensions;
- infer benchmark-specific correctness, semantic equivalence, parsing meaning, or metric disposition.

## Extension rules

Validation extensions MUST be explicitly registered where registration is required, namespaced, additive, deterministic, and benchmark-neutral at the shared boundary.

A benchmark extension MAY add supplemental semantic validation only through benchmark-owned registered logic. Such validation MAY produce namespaced issues or task-layer failure candidates, but it MUST NOT weaken shared validation, suppress shared issues, repair evidence, alter accepted identity, or move benchmark semantics into shared validators.

An extension that adds a durable cross-implementation validation rule MUST declare stable rule/issue identities and compatibility scope. A breaking change to shared evidence-validity meaning, deterministic issue semantics, or authority-gating behavior requires a new major contract version.

## Conformance expectations

Conformance MUST include deterministic provider-free checks showing that:

- unknown or incompatible contract/schema identities fail closed;
- hash mismatch, source drift, and accepted-generation identity mismatch are detected;
- planning/acceptance/golden/treatment/scoring chronology violations are detected where those stages apply;
- missing, duplicate, unexpected, mismatched, and nonterminal evidence remain distinct and are never repaired;
- blocked and accepted evidence cannot be mixed or promoted across terminal authority;
- successful empty evidence remains distinct from missing/unavailable evidence;
- issue codes and ordering are stable regardless of enumeration or callback order;
- prior validation cannot substitute for required revalidation after mutable retained evidence changes;
- secret material is absent from validation results and diagnostics;
- namespaced extensions cannot override shared validation or lifecycle invariants;
- validation never creates benchmark-specific correctness or score authority.

## Current retention policy

All current evidence MUST follow
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md): retain
relevant scoring bytes and structured measurement sources; exclude identifying
or unrelated data before persistence. Extensions and diagnostic profiles grant
no exception. Host locators remain transient; retained references are relative.
