<a id="ag-context-integration"></a>
# Context Integration

Combines independently retrieved, remembered, derived, tool-produced context, etc. into a coherent whole while preserving source identity, qualifications, dependencies, provenance, and unresolved conflicts. It establishes relationships among context units rather than independently transforming or judging them.

<a id="ag-component-responsibility-single-responsibility-context-unit"></a>
## Component Responsibility — Single-Responsibility Context Unit

Give each reusable context component one dominant responsibility so retrieval, transformation, validation, rendering, mutation, and publication remain independently replaceable.

```text
[DiscoverPatterns]:
- Retrieve pattern source material

[ClassifyPatterns]:
- Assign patterns to categories

[ResolvePatterns]:
- Resolve conflicts and uncertainty

[RenderPatterns]:
- Produce category documents

[ValidatePatterns]:
- Verify structure, coverage, and semantics
```

**Rule:** split a component when its parts change for different reasons or require different contracts.

<a id="ag-dependency-contracts-explicit-context-interface"></a>
## Dependency Contracts — Explicit Context Interface

Declare the symbolic context a reusable component requires and the context it produces before integrating it into a workflow.

```text
[PatternAuditor]:
- Requires:
  - [PatternSchema]
  - [AcceptanceRules]
- Provides:
  - [Findings]
  - [CoverageResult]

[Integrated]:
=> Bind [PatternAuditor] dependencies from [ContextPack]
```

<a id="ag-memory-reconciliation-current-fact-reconciliation"></a>
## Memory Reconciliation — Current-Fact Reconciliation

Compare remembered facts with current authoritative sources before use.

```text
[ReconciledMemory]:
=> Compare [SessionFacts] with [CurrentSources]
=> Replace stale facts
=> Preserve unresolved conflicts
```

<a id="ag-retrieval-fusion-evidence-fusion"></a>
## Retrieval Fusion — Evidence Fusion

Merge overlapping retrieval results by claim while retaining every supporting source.

```text
[FusedEvidence]:
=> Group [RetrievedPassages] by supported claim
=> Deduplicate equivalent passages
=> Retain source references
```

<a id="ag-tool-result-integration-typed-tool-result-merge"></a>
## Tool Result Integration — Typed Tool Result Merge

Normalize tool outputs before adding them to the reasoning context.

```text
[ToolFacts]:
=> Normalize paths, identifiers, status, and content from [ToolResults]
=> Separate errors from successful observations
```

<a id="ag-representation-composition-compatible-model-composition"></a>
## Representation Composition — Compatible Model Composition

Compose representations only after mapping compatible fields and identifiers.

```text
[ComposedModel]:
=> Join [Patterns] with [Categories] on `categoryId`
=> Preserve unmatched records for examination
```

<a id="ag-intermediate-result-merging-deterministic-merge"></a>
## Intermediate Result Merging — Deterministic Merge

Merge partial results with explicit rules for duplicates and conflicts.

```text
[Merged]:
=> Union [PartialA] and [PartialB]
=> Deduplicate by canonical name
=> Route conflicting definitions to [Conflicts]
```

<a id="ag-context-stitching-boundary-preserving-stitch"></a>
## Context Stitching — Boundary-Preserving Stitch

Connect fragments without erasing their source boundaries or scope.

```text
[Stitched]:
=> Order fragments by topic
=> Add transitions
=> Keep source-specific qualifiers attached to claims
```

<a id="ag-knowledge-consolidation-reusable-knowledge-set"></a>
## Knowledge Consolidation — Reusable Knowledge Set

Convert repeated observations into concise, stable abstractions.

```text
[Consolidated]:
=> Combine recurring mechanisms across [Evidence]
=> Express each as one reusable pattern
```

<a id="ag-context-assembly-ordered-context-pack"></a>
## Context Assembly — Ordered Context Pack

Assemble context in dependency order: boundaries, source facts, derived state, then task instructions.

```text
[ContextPack]:
- [Boundary]
- [ResolvedResources]
- [CurrentState]
- [TaskContract]
```

<a id="ag-dependency-resolution-dependency-binding"></a>
## Dependency Resolution — Dependency Binding

Resolve symbolic or procedural dependencies before executing downstream steps.

```text
[ReadyWork]:
=> Select items whose dependencies are present in [ContextPack]
```

<a id="ag-extensible-composition-open-closed-context-set"></a>
## Extensible Composition — Open/Closed Context Set

Extend compatible context components through composition without modifying the established set consumed elsewhere.

Modification:
```text
[Validators]:
- [SchemaValidator]
- [ReferenceValidator]
- [SemanticValidator]

[ExpandValidators]:
=> Append [FreshnessValidator] to [Validators]
```

Extension:
```text
[Validators]:
- [SchemaValidator]
- [ReferenceValidator]
- [SemanticValidator]

[ExpandedValidators]:
- [Validators]
- [FreshnessValidator]
```

Invariant: extensions preserve the original context set and conform to the dependency, behavior, and output contract expected by the consumer.

<a id="ag-output-composition-section-aware-composition"></a>
## Output Composition — Section-Aware Composition

Compose the final artifact from validated components rather than free-form regeneration.

```text
[Output]:
=> Compose title, category intent, pattern entries, examples, and cautions
=> Render only validated components
```

<a id="ag-composite-pattern-integration-pipeline"></a>
## Composite Pattern — Integration Pipeline

Prevents source loss, accidental contradiction, and context fragmentation during multi-source work.

```text
[Integrated]:
=> Reconcile [Memory] with [CurrentSources]
=> Fuse [RetrievedEvidence]
=> Normalize [ToolResults]
=> Resolve dependencies
=> Merge intermediate results
=> Consolidate reusable knowledge

[Output]:
=> Compose [Integrated] using [OutputSchema]
```
