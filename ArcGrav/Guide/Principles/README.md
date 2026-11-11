<a id="ag-arcgrav-design-principles"></a>
# ArcGrav Design Principles

Design principles for creating clear, compact, reusable, deterministic, and auditable systems using ArcGrav.

These principles define the qualities an ArcGrav system should preserve across tasks and implementations.

- For syntax and operators, see [Syntax Reference](../Syntax/)
- For reusable implementation structures, see [ArcGrav Design Pattern Catalogue](../Patterns/README.md)
- For lexical naming and instruction compression guidance, see [Lexical Representation](./Lexical_Representation.md)
- For context-dependent grammatical omission and simplification, see [Grammatical Reduction](./Grammatical_Reduction.md)

---

<a id="ag-purpose"></a>
## Purpose

ArcGrav is designed to maximize signal density while minimizing unnecessary inference.

A well-designed ArcGrav prompt makes the following explicit when they materially affect the task:

- Authoritative information
- Applicable context
- Scope and objectives
- Assumptions and constraints
- Data and state representations
- Required operations
- Execution order
- Success and failure conditions
- Uncertainty and conflict handling
- Validation and publication requirements

The goal is not maximum compression by itself.

The goal is the smallest representation that remains sufficiently precise, interpretable, operational, and verifiable.

---

<a id="ag-signal-and-boundaries"></a>
# Signal and Boundaries

<a id="ag-maximize-signal-density"></a>
## Maximize Signal Density

Every section, symbol, instruction, example, and reference should make a distinct contribution to interpretation or execution.

Remove repetition that adds no meaning.

Do not remove context required to establish:

- Authority
- Scope
- Intent
- Dependencies
- Constraints
- Failure behavior
- Verification

Compression is useful only while meaning remains explicit.

---

<a id="ag-make-governing-context-explicit"></a>
## Make Governing Context Explicit

State material boundaries and decision criteria directly instead of requiring inference.

When relevant, define:

```text
[Scope]:
- src/auth/*
- tests/auth/*

[Objectives]:
- Preserve public behavior
- Remove duplicated validation

[Assumptions]:
- Input files are UTF-8

[Success]:
- Existing tests pass
- No unrelated edits

[Authority]:
P0. Governing policy
P1. Explicit task constraints
P2. Local conventions
P3. General practice
```

A prompt should distinguish facts, assumptions, goals, constraints, and success conditions.

---

<a id="ag-separate-retrieval-framing-refinement-and-execution"></a>
## Separate Retrieval, Framing, Refinement, and Execution

Keep the context being operated on separate from instructions that determine how it is interpreted and what must be done.

```text
[Source]:
- architecture.md
- api-contract.md

Constraint:
- Treat [Source] as authoritative
- Preserve unresolved conflicts

Output:
- Report only material contradictions

Task:
1. Compare [Source]
2. Validate each reported contradiction
3. Return the validated result
```

The exact section names may vary, but their responsibilities should remain distinguishable.

---

<a id="ag-prefer-explicit-operations"></a>
## Prefer Explicit Operations

Use operation statements when context must be transformed, filtered, compared, resolved, validated, or generated.

```text
[NormalizedRecords]:
=> Parse [RawRecords]
=> Remove empty rows
=> Sort by `accountId`
```

Do not describe dynamic work as static context.

Do not introduce an operation when a static definition is sufficient.

---

<a id="ag-context-and-composition"></a>
# Context and Composition

<a id="ag-give-each-component-one-dominant-responsibility"></a>
## Give Each Component One Dominant Responsibility

A symbol, module, operation, model, validator, or output should represent one coherent responsibility.

Prefer:

```text
[FindingSchema]
[Findings]
[ResolveFindings]
[ValidateFindings]
[RenderReport]
```

over one component that mixes modeling, mutation, transformation, verification, and presentation.

Split a component when its parts:

- Change for different reasons
- Serve different consumers
- Require different permissions
- Need independent validation
- Can be reused separately

---

<a id="ag-define-before-reference"></a>
## Define Before Reference

Create symbolic references before invoking them.

Keep their meanings stable after definition.

```text
[Policy]:
- Preserve uncertainty
- Prefer minimal changes

Task:
- Apply [Policy]
```

Avoid forward references, silent redefinition, and overloaded symbols when procedural interpretation matters.

---

<a id="ag-prefer-composition-over-duplication"></a>
## Prefer Composition Over Duplication

Combine or reference authoritative components instead of copying their contents into every consumer.

```text
[Standard]:
- [SafetyPolicy]
- [FindingModel]
- [Validation]
```

Composition reduces token use, prevents inconsistent copies, and allows components to evolve independently.

---

<a id="ag-prefer-semantic-references-over-embedded-summaries"></a>
## Prefer Semantic References Over Embedded Summaries

Reference complete authoritative context when it already exists.

Local context should describe additions, specialization, or exceptions.

```text
[SecurityStandard]:
- policies/security.md

[FeatureContext]:
- Apply [SecurityStandard]
- Require feature-specific audit logging
```

A partial embedded summary may omit constraints, lose provenance, or become stale.

Resolve the reference before depending on its contents.

---

<a id="ag-require-a-distinct-contribution"></a>
## Require a Distinct Contribution

Every included file, symbol, example, operation, or validator should contribute at least one of the following:

- Required information
- Governing authority
- Provenance
- A dependency
- A transformation
- An independent verification path

For each component, determine:

1. What does it contribute?
2. Is that contribution already available or inherited?
3. Does the workflow use it?
4. Would removing it materially change the result?
5. Is it still required as independent evidence or verification?

Remove components that make no distinct contribution.

---

<a id="ag-use-the-smallest-sufficient-context"></a>
## Use the Smallest Sufficient Context

Include only the context required to complete the task correctly.

Smallest does not mean incomplete.

Sufficiency governs compression.

Do not include unrelated history, duplicated summaries, unused examples, speculative resources, or optional context that does not affect the result.

---

<a id="ag-place-information-at-the-narrowest-valid-scope"></a>
## Place Information at the Narrowest Valid Scope

Define broad rules once and inherit them.

Keep specialized rules close to the context where they apply.

```text
[RepositoryPolicy]:
- All changes require tests

[PaymentsPolicy]:
- Apply [RepositoryPolicy]
- Payment changes require idempotency checks
```

Move a rule upward only when it is valid for every affected descendant.

A narrower context may add or specialize inherited context, but it must not silently weaken higher-authority constraints.

---

<a id="ag-choose-structures-by-semantic-need"></a>
## Choose Structures by Semantic Need

Select a representation according to what its structure means.

- Use an unordered list when sequence does not affect meaning
- Use an ordered list when sequence affects execution or interpretation
- Use a priority list when authority, severity, or preference determines selection
- Use a hierarchy when inheritance or containment determines applicability
- Use a map for independent keyed relationships
- Use a registry for resource discovery
- Use a route for ordered context or execution
- Use a template when output shape is fixed
- Use a worklist or queue when pending work must be selected and tracked
- Use a canonical model and signature when stable comparison is required

Do not use numbering, nesting, hierarchy, or symbolic references merely for visual decoration.

---

<a id="ag-declare-component-dependencies"></a>
## Declare Component Dependencies

A reusable component should declare the context it requires.

The surrounding system should supply and validate those dependencies before execution.

```text
[Worker]:
- Resolves: workers/audit.md
- Import:
  - [Policy]
  - [FindingSchema]
  - [Validation]
```

Keep the logical dependency contract separate from the physical resource location.

Missing or incompatible dependencies should produce an explicit integration failure.

---

<a id="ag-design-for-extension"></a>
## Design for Extension

Consumers should operate against stable contracts rather than fixed implementation lists.

New compatible policies, validators, models, renderers, or strategies should be addable without rewriting established consumers.

Extension must not weaken:

- Existing contracts
- Independent testability
- Deterministic ordering
- Validation responsibilities
- Failure handling

---

<a id="ag-data-state-and-execution"></a>
# Data, State, and Execution

<a id="ag-separate-configuration-state-operations-validation-and-rendering"></a>
## Separate Configuration, State, Operations, Validation, and Rendering

Keep the following independently understandable:

- Stable configuration
- Mutable working state
- Transforming operations
- Verification
- Presentation

```text
[SeverityOrder]:
1. Blocking
2. Major
3. Minor

[Findings]: []

[SortFindings]:
=> Sort [Findings] using [SeverityOrder]

[ValidateFindings]:
=> Validate [Findings] against [FindingSchema]

[RenderFindings]:
=> Render [Findings] using [ReportTemplate]
```

This separation improves inspection, replacement, reuse, and testing.

---

<a id="ag-define-models-before-operations"></a>
## Define Models Before Operations

Specify the structure of records exchanged between phases before defining the operations that create or consume them.

```text
[FindingSchema]:
- `id`
- `category`
- `evidence`
- `resolution`
- `confidence`
```

When a name identifies an exact member of an external or modeled structure, preserve it with backticks everywhere it appears as that identifier. Backticks identify structure; double quotes identify text.

Distinguish required, optional, nullable, unresolved, invalid, and derived fields when those states affect interpretation.

---

<a id="ag-keep-canonical-models-separate-from-derived-views"></a>
## Keep Canonical Models Separate from Derived Views

Maintain one authoritative representation.

Generate summaries, indexes, registries, reports, and specialized views from it.

```text
[Records]:
- `id`
- `value`
- `status`

[SummaryView]:
=> Project `id` and `status` from [Records]

[DiagnosticView]:
=> Project `id`, `value`, and `status` from [Records]
```

Do not independently maintain values in multiple views when they can be reproduced from canonical state.

---

<a id="ag-separate-comparison-forms-from-source-records"></a>
## Separate Comparison Forms from Source Records

Canonicalize values when stable comparison, grouping, or deduplication is required.

Retain original source records and metadata for output and verification.

```text
[Signature]:
=> Serialize candidate values using stable key ordering

[DetectConflict]:
1. Compare candidate [Signature] values
2. Preserve the original candidate records
```

A comparison signature is a derived representation, not an authoritative source record.

---

<a id="ag-keep-mutable-state-explicit"></a>
## Keep Mutable State Explicit

Represent changing data in named state anchors.

```text
[Findings]: []
[Pending]: []

[ExecutionStats]:
- `processed`: 0
- `resolved`: 0
- `unresolved`: 0
```

State must remain distinguishable from stable policies, schemas, contracts, and reusable operations.

---

<a id="ag-make-state-lifecycles-explicit"></a>
## Make State Lifecycles Explicit

Define when mutable state is:

1. Initialized
2. Populated
3. Transformed
4. Validated
5. Consumed
6. Reset or discarded

```text
[Run]:
1. Clear [Findings]
2. Populate [Findings]
3. Validate [Findings]
4. Render [Findings]
5. Discard temporary state
```

Do not leave initialization or cleanup implicit when repeated execution could reuse stale state.

---

<a id="ag-use-explicit-execution-phases"></a>
## Use Explicit Execution Phases

When order matters, divide work into stages with clear inputs, outputs, responsibilities, and failure boundaries.

```text
[Pipeline]:
1. Run [Parse]
2. Run [Scope]
3. Run [Analyze]
4. Run [Resolve]
5. Run [Validate]
6. Run [Render]
```

Do not combine stages merely to reduce the visible number of steps.

Preserve intermediate representations when they materially improve validation, replay, debugging, recovery, or traceability.

---

<a id="ag-define-traversal-and-selection-policy"></a>
## Define Traversal and Selection Policy

When processing collections, hierarchies, dependencies, or pending work, define:

- How the next item is selected
- How progress is demonstrated
- How termination is determined
- How duplicates are handled
- How cycles are handled
- How already-processed items are handled
- Whether traversal is resumable

Use an explicit worklist when order, observability, prioritization, or recovery matters.

---

<a id="ag-integrity-and-resolution"></a>
# Integrity and Resolution

<a id="ag-make-contracts-explicit"></a>
## Make Contracts Explicit

Define expected inputs, outputs, invariants, side effects, and failure behavior for operations whose correctness matters.

```text
[ResolveContract]:
- Input is a sequence of candidate records
- Output preserves unresolved values
- Input records remain unmodified
- Malformed required structure raises an error

[Resolve]:
=> Conform to [ResolveContract]
```

Distinguish invalid input from valid input that produces an unresolved result.

---

<a id="ag-preserve-evidence-and-provenance"></a>
## Preserve Evidence and Provenance

Derived conclusions should remain traceable to their supporting records and transformations.

Useful provenance may include:

- Source identifier
- Source location
- Source version
- Relevant excerpt or record
- Transformation or validator
- Authority or confidence
- Execution identifier or timestamp

Do not reconstruct a selected value while discarding the source record that justified it.

---

<a id="ag-preserve-uncertainty-instead-of-inventing-resolution"></a>
## Preserve Uncertainty Instead of Inventing Resolution

Unknown, absent, empty, false, invalid, conflicting, and not applicable are different states.

```text
[Uncertainties]: []

[ResolveOwner]:
=> When ownership cannot be established:
  - Preserve `owner` as unresolved
  - Record available evidence
  - Record missing evidence
  - Record why resolution failed
```

A deterministic system may deterministically return an unresolved result.

Determinism does not require inventing a winner.

---

<a id="ag-resolve-conflicts-by-declared-authority"></a>
## Resolve Conflicts by Declared Authority

Rank evidence sources before resolving disagreement.

Select a result only when authority or evidence supports the choice.

When equally authoritative evidence remains materially inconsistent:

- Preserve the conflict
- Record the competing claims
- Retain their source records
- State what additional evidence would resolve it

Lower-authority evidence must not silently break a conflict among higher-authority sources.

---

<a id="ag-separate-modification-from-verification"></a>
## Separate Modification from Verification

Generation or repair and independent inspection should not silently share responsibilities.

```text
[Command]:
=> Modify [Artifacts]

[Verification]:
=> Inspect [Artifacts]
=> Do not modify [Artifacts]
```

Verification should report defects rather than silently repair them unless repair is explicitly included in its contract.

---

<a id="ag-validate-in-focused-layers"></a>
## Validate in Focused Layers

Separate validation concerns when they require different evidence or responsibilities.

```text
[Validation]:
1. Run [SchemaValidation]
2. Run [ReferenceValidation]
3. Run [SemanticValidation]
4. Run [ConsistencyValidation]
5. Apply [PostconditionGate]
```

Each validator should remain within its declared responsibility.

Validation order should reflect prerequisites.

---

<a id="ag-fail-fast-on-invalid-structure"></a>
## Fail Fast on Invalid Structure

Stop when a structural or contractual error makes later work untrustworthy.

A failure should identify:

- The failed condition
- The affected input
- The operation that stopped
- Whether partial state is safe to inspect
- Whether retry or remediation is possible

Do not use fail-fast behavior for ordinary uncertainty that the workflow is designed to preserve.

---

<a id="ag-verify-closure-against-the-original-task"></a>
## Verify Closure Against the Original Task

Final verification should evaluate the result against the original scope, objectives, constraints, and success criteria.

Do not establish completeness solely from the latest intermediate state.

Before publication, confirm:

- Required outputs exist
- Required coverage is complete
- References resolve
- Governing constraints remain satisfied
- Blocking uncertainty is reported
- Validation has completed
- Partial completion is identified accurately

---

<a id="ag-determinism-maintenance-and-observability"></a>
# Determinism, Maintenance, and Observability

<a id="ag-design-for-stable-determinism"></a>
## Design for Stable Determinism

Identical inputs and configuration should produce identically ordered and formatted results.

Define:

- Ordering and grouping
- Tie-breaking behavior
- Traversal order
- Key ordering
- Missing-value rendering
- Formatting and separators
- Stable fallback behavior

Determinism applies to successful, unresolved, partial, and error results.

---

<a id="ag-prefer-minimal-and-idempotent-changes"></a>
## Prefer Minimal and Idempotent Changes

Maintenance operations should change only what is necessary and converge when repeated.

```text
[Maintenance]:
- Update stale references
- Preserve valid content
- Do not rewrite unchanged sections
- Do not create duplicate entries
- Preserve stable ordering
```

Running the same operation again against the resulting state should produce no additional changes.

Non-idempotent output should be treated as a failed maintenance postcondition.

---

<a id="ag-make-execution-observable-when-it-matters"></a>
## Make Execution Observable When It Matters

Return structured execution information when completeness, coverage, performance, or benchmarking must be measured.

```text
[ExecutionStats]:
- `discovered`: 0
- `processed`: 0
- `resolved`: 0
- `unresolved`: 0
- `skipped`: 0
- `failed`: 0
- `validated`: false
- `complete`: false
```

Statistics should:

- Use stable definitions
- Distinguish attempted, completed, skipped, unresolved, and failed work
- Remain separate from domain findings
- Avoid claiming completeness unless full coverage can be demonstrated

---

<a id="ag-portability-and-restraint"></a>
# Portability and Restraint

<a id="ag-cross-model-portability"></a>
## Cross-Model Portability

ArcGrav's cross-model portability means that it *should* remain inspectable and usable across models, vendors, chat interfaces, and agents that understand natural language and common technical notation.

Prefer familiar:

- Headings
- Lists
- Indentation
- Symbolic references
- Literal blocks
- Directional operators

Avoid specialized grammar that requires an external parser or enforcement layer.

---

<a id="ag-avoid-unnecessary-structure"></a>
## Avoid Unnecessary Structure

Not every prompt requires symbols, state, pipelines, contracts, dependency injection, instrumentation, or layered validation.

Use additional structure only when it materially improves at least one of the following:

- Precision
- Reuse
- Traceability
- Determinism
- Maintainability
- Safety
- Validation
- Recovery
- Token efficiency

For a small one-off task, concise Retrieval, Framing, and Execution sections may be sufficient.

Larger systems should add structure incrementally as responsibilities, dependencies, state, and failure risks grow.
