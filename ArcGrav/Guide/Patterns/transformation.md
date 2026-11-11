<a id="ag-transformation"></a>
# Transformation

Derives new semantic content from supplied context through declared operations such as parsing, extraction, classification, normalization, comparison, analysis, synthesis, planning, translation, candidate generation, etc. It changes or derives meaning but does not retrieve sources, integrate independent results, validate correctness, etc.

<a id="ag-parsing-structure-recovery"></a>
## Parsing — Structure Recovery

Recover explicit units from raw input before interpreting them.

```text
[Parsed]:
=> Parse [Source] into:
  - Headings
  - Lists
  - References
  - Operations
```

<a id="ag-extraction-relevant-field-extraction"></a>
## Extraction — Relevant-Field Extraction

Select only facts required by the current objective while retaining source identity.

```text
[Extracted]:
=> Extract pattern from [Source] ↳
  - Name
  - Intent
  - Mechanics
  - Constraints
  - Example
```

<a id="ag-filtering-relevance-filter"></a>
## Filtering — Relevance Filter

Remove items that do not satisfy explicit inclusion criteria.

```text
[Filtered]:
=> Keep reusable prompt-operation patterns
=> Exclude repository history and incidental prose
```

<a id="ag-normalization-surface-normalization"></a>
## Normalization — Surface Normalization

Standardize spelling, headings, identifiers, and list structure without changing meaning.

```text
[Normalized]:
=> Normalize category names to canonical title case
=> Normalize file names to kebab-case
```

<a id="ag-canonicalization-semantic-equivalence-collapse"></a>
## Canonicalization — Semantic Equivalence Collapse

Merge equivalent variants into one canonical pattern.

```text
[Canonical]:
=> Merge patterns with equivalent intent and mechanics
=> Retain the clearest example and all unique constraints
```

<a id="ag-classification-primary-category-assignment"></a>
## Classification — Primary Category Assignment

Assign each item to the category that best describes its dominant function.

```text
[Classified]:
=> Classify [Extracted] by [Categories]
=> Preserve secondary-category tags when useful
```

<a id="ag-aggregation-category-aggregation"></a>
## Aggregation — Category Aggregation

Combine normalized records into category collections.

```text
[Grouped]:
=> Group [Canonical] by primary category
=> Sort by conceptual dependency
```

<a id="ag-analysis-mechanism-analysis"></a>
## Analysis — Mechanism Analysis

Explain why a pattern works by relating syntax to model interpretation.

```text
[Analysis]:
=> Identify:
  - Cue
  - Binding rule
  - Expected behavior
  - Failure mode
```

<a id="ag-synthesis-evidence-bounded-synthesis"></a>
## Synthesis — Evidence-Bounded Synthesis

Combine multiple source observations into a reusable abstraction without inventing unsupported mechanics.

```text
[Pattern]:
=> Synthesize [Evidence] into:
  - Intent
  - Procedure
  - Invariant
  - Example
```

<a id="ag-candidate-generation-bounded-candidate-set"></a>
## Candidate Generation — Bounded Candidate Set

Generate multiple options against the same contract, then pass them to examination.

```text
[Candidates]:
=> Generate 3 distinct implementations satisfying [Constraints]
=> Preserve tradeoffs for ranking
```

<a id="ag-comparison-dimensioned-comparison"></a>
## Comparison — Dimensioned Comparison

Compare candidates using declared dimensions rather than a general preference.

```text
[Comparison]:
=> Compare [Candidates] by:
  - Precision
  - Reuse
  - Token cost
  - Failure risk
```

<a id="ag-planning-dependency-aware-plan"></a>
## Planning — Dependency-Aware Plan

Transform objectives and constraints into ordered executable work.

```text
[Plan]:
=> Decompose [Goal]
=> Order steps by dependency
=> Mark validation and termination conditions
```

<a id="ag-translation-meaning-preserving-translation"></a>
## Translation — Meaning-Preserving Translation

Translate content while preserving references, hierarchy, literals, and operational semantics.

```text
[Translated]:
=> Translate prose in [Source]
=> Preserve symbols literally:
  - Paths
  - Code
  - Schema keys
```

<a id="ag-composite-pattern-transformation-chain"></a>
## Composite Pattern — Transformation Chain

Makes each semantic change visible and prevents extraction, interpretation, and publication from collapsing into one opaque step.

```text
[Derived]:
=> Parse [Existing]
=> Extract reusable mechanisms
=> Normalize terminology
=> Canonicalize equivalents
=> Classify by [Categories]
=> Aggregate into category collections
=> Synthesize publishable pattern entries
```
