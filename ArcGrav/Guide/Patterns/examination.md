<a id="ag-examination"></a>
# Examination

Inspects evidence, intermediate results, structures, candidate outputs, etc. against explicit criteria. It identifies errors, omissions, inconsistencies, unsupported claims, broken references, failed assertions, counterexamples, acceptance-test failures, etc. but does not determine how unresolved conflicts should ultimately be settled.

<a id="ag-observation-fact-only-observation"></a>
## Observation — Fact-Only Observation

Record what is directly present before explaining or judging it.

```text
[Observations]:
=> List in [Source] ↳
  - Visible headings
  - Rferences
  - Operations
  - Constraints
=> Do not infer intent yet
```

<a id="ag-inspection-targeted-inspection"></a>
## Inspection — Targeted Inspection

Inspect a bounded object for a declared class of defects.

```text
[Inspection]:
=> Inspect [Files] for:
  - Broken links
  - Duplicate headings
  - Empty sections
```

<a id="ag-structural-validation-structure-contract-check"></a>
## Structural Validation — Structure Contract Check

Validate required sections, ordering, and nesting.

```text
[StructureCheck]:
- Exactly one H1
- Pattern entries use H2
- Examples use fenced blocks
```

<a id="ag-schema-validation-field-level-validation"></a>
## Schema Validation — Field-Level Validation

Confirm records conform to the declared schema.

```text
[SchemaCheck]:
=> Validate every [Pattern] against [PatternSchema]
```

<a id="ag-semantic-validation-meaning-check"></a>
## Semantic Validation — Meaning Check

Confirm the content expresses the intended mechanism and does not contradict its example.

```text
[SemanticCheck]:
=> Compare each:
  - Pattern intent
  - Procedure
  - Example
=> Flag mismatched semantics
```

<a id="ag-referential-validation-reference-integrity-check"></a>
## Referential Validation — Reference Integrity Check

Verify that every symbolic reference or link resolves uniquely.

```text
[ReferenceCheck]:
=> Resolve every bracketed symbol and repository-relative link
=> Reject undefined or multiply defined references
```

<a id="ag-consistency-and-completeness-cross-artifact-check"></a>
## Consistency and Completeness — Cross-Artifact Check

Check terminology, coverage, and required content across all outputs.

```text
[Coverage]:
=> Confirm every [Category] has one file
=> Confirm every requested subcategory appears
```

<a id="ag-evidence-verification-claim-to-evidence-check"></a>
## Evidence Verification — Claim-to-Evidence Check

Require support for factual or derived claims.

```text
[EvidenceCheck]:
=> Map each derived pattern to one or more source mechanisms
=> Preserve source locations where available
```

<a id="ag-assertion-checking-explicit-assertion-set"></a>
## Assertion Checking — Explicit Assertion Set

Convert requirements into pass/fail assertions.

```text
[Assertions]:
- count(category files) = 10
- empty(category files) = 0
- missing(index links) = 0
```

<a id="ag-execution-instrumentation-structured-workflow-metrics"></a>
## Execution Instrumentation — Structured Workflow Metrics

Publish stable execution measurements alongside the domain result when completeness, coverage, skipped work, unresolved work, or validation status must be observable.

```text
[ExecutionMetrics]:
- `resources_requested`: 0
- `resources_resolved`: 0
- `records_processed`: 0
- `records_accepted`: 0
- `records_rejected`: 0
- `unresolved_items`: 0
- `validation_failures`: 0
- `postconditions_passed`: false

[Assessment]:
=> Populate [ExecutionMetrics]
=> Include [ExecutionMetrics] with [Result]
```

**Invariant:** metric meanings remain stable, values derive from observable workflow events, and completeness is claimed only when coverage can be demonstrated.

<a id="ag-instrumentation-validation-independent-metrics-check"></a>
## Instrumentation Validation — Independent Metrics Check

Verify execution measurements against source inventories, workflow state, and published results before using them as evidence of completeness or correctness.

```text
[MetricsCheck]:
=> Compare processed counts with [SourceInventory]
=> Confirm accepted, rejected, and unresolved totals reconcile
=> Confirm unresolved records appear in [Result]
=> Reject unsupported completeness claims
```

<a id="ag-cross-validation-independent-check-path"></a>
## Cross-Validation — Independent Check Path

Validate important conclusions through a second method or representation.

```text
[CrossCheck]:
=> Compare rendered file inventory with [Categories]
=> Independently compare index links with actual paths
```

<a id="ag-evaluation-criteria-based-evaluation"></a>
## Evaluation — Criteria-Based Evaluation

Judge an artifact against named criteria.

```text
[Evaluation]:
=> Evaluate [Candidate] against:
  - Precision
  - Completeness
  - Reuse
  - Token cost
```

<a id="ag-candidate-ranking-dimensioned-ranking"></a>
## Candidate Ranking — Dimensioned Ranking

Rank candidates using weighted or ordered criteria and retain tradeoffs.

```text
[Ranking]:
P0. Satisfies constraints
P1. Preserves source semantics
P2. Improves clarity
P3. Minimizes complexity
```

<a id="ag-quality-assessment-and-confidence-calibrated-assessment"></a>
## Quality Assessment and Confidence — Calibrated Assessment

Separate quality judgment from certainty about that judgment.

```text
[Assessment]:
- `quality`: "acceptable"
- `confidence`: 0.86
- `uncertainty`: "source directory inventory was partially constrained"
```

<a id="ag-acceptance-testing-consumer-level-test"></a>
## Acceptance Testing — Consumer-Level Test

Test the output as its intended consumer would use it.

```text
[Acceptance]:
- A reader can locate each category from the index
- A pattern can be copied without missing context
- Examples conform to ArcGrav syntax
```

<a id="ag-pass-fail-determination-explicit-verdict"></a>
## Pass/Fail Determination — Explicit Verdict

Publish a verdict only after assertions and acceptance tests complete.

Separates observation, validation, ranking, and acceptance so that confidence is earned rather than implied.

```text
[Verdict]:
=> PASS only when all P0 assertions pass
=> Otherwise FAIL with exact unmet assertions
```
