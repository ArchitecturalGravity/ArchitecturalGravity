# Report Generation Contract

- Contract ID: `arcgrav.shared.report-generation`
- Version: `3.0.0`
- Status: published
- Compatibility scope: automatic completion of scored accepted runs and exact retained report readers

## One completion operation

The application MUST validate the finalized accepted evidence and build its report as part of execution completion. Generate, Verify, and Re-verify are not separate user operations or fallback paths.

Execution outcome and report completion are distinct facts. A scored accepted run can retain valid diagnostic evidence while report completion fails. The application MUST NOT label a report ready until its exact components and completion record are durably published together. A missing report request factory, invalid evidence, rendering error, or publication error MUST produce an explicit failed completion outcome, not a deferred manual reporting action.

## Authority and admission

The report MUST derive from exactly one finalized `AcceptedRun`, with the exact accepted generation, accepted snapshot, execution boundary, benchmark registration, comparison track, report configuration, metric registrations and scorer contracts required to interpret its evidence.

Before consuming retained evidence, completion MUST revalidate accepted authority, required schemas and contracts, artifact identities, source hashes, completeness and evidence availability. Required invalid, missing, ambiguous or incompatible authority MUST fail closed. Blocked or unscored outcomes MUST NOT be presented as accepted scored reports; their completion is explicitly `not_applicable`.

The cataloged evidence-validation, scorer-invocation, failure-taxonomy, effective-execution-evidence, transient-invocation and evidence-minimization contracts govern source evidence. Completion MUST NOT repair evidence, rescore observations, rerun providers, invent measurements or substitute GUI state, cached reports, neighboring runs, current files or descriptive prose for the exact retained generation.

## Canonical model and exact output

Build one canonical report model from the validated retained inputs, then derive every report component from that model once. Completion MUST NOT regenerate the report to compare it with itself. Internal deterministic rendering primitives are not a second application reporting workflow.

The completed archive MUST retain exactly identified components for these roles:

- `machine_json`: machine-readable report identity, data and availability states;
- `canonical_evidence_json`: canonical retained report evidence;
- `markdown`: the human-readable report;
- `manifest`: the identities and hashes binding the generated components and inputs.

The machine report uses `arcgrav.shared.schema.report@3.0.0`, the report manifest uses `arcgrav.shared.schema.report-manifest@1.0.0`, and `report_manifest_id` binds the report to that manifest.

Each completion component descriptor MUST contain its role, artifact ID, archive reference and SHA-256 identity. The completion record binds those descriptors to the generation and the archive's core evidence digest. A manifest name or field name alone does not require or authorize a reconstruction operation.

The canonical model MUST preserve the registered report sections, metric/scorer identities, planned and finalized observation counts, treatment numerators and denominators, case-level results, failures, measurement availability, exclusions, deviations and bounded conclusions. Human and machine output MUST agree on values and states. Missing or unproducible evidence MUST remain explicitly unavailable, missing, failed, excluded, blocked, non-comparable or not applicable; it MUST NOT become a guessed value, zero or empty success.

A benchmark registration MAY select an integrity-bound report extension evaluator. The request resolver MUST verify the selected implementation and exact configuration resources. Shared completion invokes it only after finalized source admission, supplying the same generation, revalidated reporting input and artifact store used for the canonical report. A registered evaluator failure fails completion; it MUST NOT be replaced by copied configuration or guessed outcomes. Its returned namespaced extensions MUST NOT collide with existing report extensions.

## Report status

Report status remains distinct from completion status. Within the report, invalid authority takes precedence over dry-run semantics, missing required output, deviations and complete output, in that order. A complete report can describe failures or unavailable measurements only when its registered reporting rules permit those states and the required section representations remain present.

Reports preserve the evidence class, synthetic or dry-run identity, contamination findings, and measurement availability as factual data. Benchmark prerequisites are reported as satisfied or unsatisfied with concrete reasons. Reports and completion records have no claim-permission state.

## Publication, failure and access

Completion publication MUST be generation-bound and atomic from the reader's perspective. A reader MUST see either the complete, integrity-validated component set or an explicit unavailable/failed report state. Partial output MUST NOT appear ready. Diagnostic evidence MUST remain distinct from scored results.

Repeated completion notifications, selection changes, deletion and late worker callbacks MUST NOT replace another generation's report or manufacture a second report. Failure details MUST remain deterministic and redact secrets and invocation-only material.

Open and Export use the exact retained report bytes. They MUST NOT call a provider, scorer, generator, renderer or reconstruction verifier. Import MUST validate the supported archive and completion record before presenting those same bytes; it MUST reject unsupported formats instead of upgrading, rebuilding or falling back to a saved GUI projection.

## Conformance

Provider-free tests MUST cover automatic report creation without a report action; validation and publication failures; missing reporting context; retained-byte tampering and generation mismatches; duplicate, missing and unsafe archive members; unsupported archive formats; exact report bytes after import/restart/export; absent manual generation/verification commands; and factual evidence-class and prerequisite outcomes for synthetic and live runs. Tests MUST preserve evidence-integrity, secret-safety and generation-isolation assertions.
