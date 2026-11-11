<a id="ag-resolution"></a>
# Resolution

Determines the defensible final outcome from examined evidence by ranking authority, resolving supported conflicts, preserving material ambiguity, representing uncertainty, recording decisions and provenance, verifying closure, deciding what may be published, etc. It converts validated findings into a final conclusion without concealing unresolved limitations.

<a id="ag-source-record-preservation-immutable-source-layer"></a>
## Source-Record Preservation — Immutable Source Layer

Keep raw source records separate from normalized or derived records.

```text
[SourceRecords]:
- Unmodified retrieved content

[DerivedRecords]:
=> Transform [SourceRecords]
```

<a id="ag-evidence-retention-keep-supporting-evidence"></a>
## Evidence Retention — Keep Supporting Evidence

Retain evidence through transformation and publication.

```text
[Decision]:
- `outcome`: classify symbolic references under Representation Shaping
- `evidence`: reusable named context and composition behavior
```

<a id="ag-provenance-source-to-output-trace"></a>
## Provenance — Source-to-Output Trace

Record where a derived artifact came from and which operations produced it.

```text
[Provenance]:
- `source`: current ArcGrav syntax documentation
- `operations`:
  1. Extract
  2. Normalize
  3. Classify
  4. Synthesize
- `output`: relative path and filename
```

<a id="ag-authority-ranking-ranked-evidence-authority"></a>
## Authority Ranking — Ranked Evidence Authority

Rank sources before resolving disagreement.

```text
[Authority]:
P0. Explicit governing constraints
P1. Current authoritative source
P2. Repository-local convention
P3. Derived inference
P4. General convention
```

<a id="ag-conflict-resolution-rule-guided-conflict-resolution"></a>
## Conflict Resolution — Rule-Guided Conflict Resolution

Resolve only when authority or evidence justifies a choice.

```text
[Resolved]:
=> Compare conflicting claims by [Authority]
=> Select the higher-authority supported claim
=> Record the rejected alternative and reason
```

<a id="ag-ambiguity-preservation-preserve-material-ambiguity"></a>
## Ambiguity Preservation — Preserve Material Ambiguity

Do not collapse materially different interpretations without evidence.

```text
[Ambiguities]:
- "pattern" may mean source example or reusable abstraction
- Preserve both until the task contract selects one
```

<a id="ag-uncertainty-representation-calibrated-uncertainty-record"></a>
## Uncertainty Representation — Calibrated Uncertainty Record

State what is uncertain, why, and what would resolve it.

```text
[Uncertainty]:
- `claim`: uncertainty description
- `confidence`: confidence level for `claim`
- `cause`: what caused the uncertainty of `claim`
- `resolution`: proposed uncertainty resolution for `claim`
```

<a id="ag-decision-records-compact-decision-log"></a>
## Decision Records — Compact Decision Log

Record consequential decisions with alternatives and rationale.

```text
[DecisionRecord]:
- `decision`: one primary category per pattern
- `alternatives`: duplicate patterns across categories
- `rationale`: reduce drift and maintenance cost
```

<a id="ag-independent-verification-separate-verification-path"></a>
## Independent Verification — Separate Verification Path

Verify final claims using a method independent from the derivation path.

```text
[Verification]:
=> Rebuild expected file list directly from [Categories]
=> Compare with published paths
```

<a id="ag-final-completeness-checks-closure-audit"></a>
## Final Completeness Checks — Closure Audit

Perform a final audit against the original request rather than only the latest intermediate state.

```text
[Closure]:
- All categories represented
- Files created in target directory
- Files populated from derived patterns
- Git history not used as source material
```

<a id="ag-output-publication-validated-publication"></a>
## Output Publication — Validated Publication

Publish only artifacts that pass semantic and structural checks, while clearly reporting partial completion when necessary.

```text
[Publish]:
=> Publish outputs that pass [Acceptance]
=> Retain failed outputs as drafts
=> Report exact unresolved items
```

<a id="ag-composite-pattern-evidence-to-publication-resolution"></a>
## Composite Pattern — Evidence-to-Publication Resolution

Makes the final answer traceable, uncertainty-aware, and resistant to silent conflict resolution.

```text
[Resolution]:
=> Rank authorities
=> Resolve supported conflicts
=> Preserve unresolved ambiguity
=> Represent uncertainty
=> Retain evidence and provenance
=> Record consequential decisions
=> Independently verify completeness
=> Publish validated outputs
```
