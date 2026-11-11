# Run Completion Contract

- Contract ID: `arcgrav.shared.run-completion`
- Version: `2.0.0`
- Status: published
- Compatibility scope: execution completion, archive publication, retained report readers and archive import

## Completion record

Every published current archive MUST contain a completion record with `schema_id: arcgrav.shared.run-completion`, `schema_version: 2.0.0`, exact `generation_id`, timezone-aware `completed_at`, `status`, `validation`, and `report`. The archive writer binds it to core evidence with `core_sha256`.

Execution outcome, validation outcome, and report completion are separate facts. A terminal run or an in-memory completion record does not prove successful archive publication.

| Completion status | Meaning | `validation.status` | `report` |
| --- | --- | --- | --- |
| `complete` | Required validation passed and all report components were published together. | `passed` | Complete component set |
| `validation_failed` | Required post-treatment, source, or prepublication validation failed. | `failed` | null |
| `report_failed` | Report context, rendering, retention, publication, or archive readback failed. | Preserved validation outcome: `passed`, `failed`, or `not_applicable` | null |
| `not_applicable` | The terminal outcome is not accepted scored report authority. | `not_applicable` | null |

A publication or readback failure can supersede any earlier completion status without changing the validation outcome. It MUST NOT be presented as successful completion. Application-only publication diagnostics do not establish a valid sealed archive or authorize extra archive fields.

`validation.diagnostic` is an admitted fixed completion/error classification or null. Optional `diagnostics` contain only admitted structured stage classifications. `report` is null unless status is `complete`; unsuccessful archives MUST contain no final report members.

A complete report identifies its `report_id` and exactly one component for each role: `markdown`, `machine_json`, `canonical_evidence_json`, and `manifest`. Each descriptor contains `role`, `reference`, `sha256`, and `artifact_id`. Cross-generation, duplicate, missing, unknown, ambiguous, or unsafe bindings MUST fail validation. Completion records have no claim-permission field.

## Automatic completion

After treatment execution and scoring, the application MUST validate retained evidence before building a report. The resolved report request is bound to the finalized accepted generation. A missing request factory on a scored run is an explicit report failure, never a deferred manual action.

The application exposes completion and report results by generation identity. No manual Generate, Verify, or Re-verify command is available. Safe diagnostic evidence remains available on failure without being presented as a completed report.

## Import and reopen

Import MUST validate copied archive bytes, supported format and completion schema, core digest, component identities and hashes, and coherent completion/report state before committing an import or showing a report. It MUST reject unsafe paths, duplicate entries, hash mismatches, cross-run references, unsupported versions, and incomplete required metadata. Import MUST NOT overwrite another retained generation.

An archive missing the completion record or GUI presentation snapshot cannot satisfy this contract. Neither archive upgrades nor evidence reconstruction or report regeneration can substitute for those records. A GUI snapshot never authorizes report bytes.

After validation, Open, restart, and Export preserve the exact original report bytes. They MUST NOT rerun providers, invoke scorers, regenerate reports, or execute benchmark policy. Import does not modify the original archive.

## Integrity limits

Internal SHA-256 manifests detect differences relative to recorded identities. A separately supplied whole-archive digest can bind exact archive bytes. Import reports the checks performed and their outcomes; internal hashes alone do not establish an independent source of trust.

## Failure behavior

No ready state may be exposed before successful archive publication. Failure MUST NOT substitute a neighboring report or stale GUI snapshot. Import rejection MUST leave the original file and existing history unchanged. Missing or failed reports remain explicitly unavailable, with fixed diagnostic classifications rather than arbitrary exception prose or invented data.

## Current evidence archive

Current archives use format `4` and MUST satisfy
[`arcgrav.shared.evidence-minimization@1.0.0`](EVIDENCE_MINIMIZATION.md).
Formats `1`, `2`, and `3` are unsupported; readers do not upgrade or migrate them.
Relabeling an old archive does not establish admission: manifest, completion,
execution boundaries, and every golden/treatment observation must independently
satisfy the current closed evidence policy. Raw diagnostic prose and unknown
completion or manifest fields are rejected.
Format acceptance does not resolve the documented
[nested scorer-data gap](EVIDENCE_MINIMIZATION.md#current-implementation-limit).
