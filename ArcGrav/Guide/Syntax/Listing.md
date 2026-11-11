<a id="ag-listing"></a>
# Listing

Listing uses line prefixes to express membership, sequence, or precedence within a section. The selected prefix tells the model whether child items are independent values, ordered steps, or ranked priorities.

Listing encodes membership, sequence, and precedence directly into prompt structure, reducing prose while preserving deterministic interpretation.

<a id="ag-purpose"></a>
### Purpose

- Represent multiple values compactly
- Distinguish unordered context from ordered execution
- Encode priority without explanatory prose
- Preserve item-level scope and readability

**Unordered List**

Use `-` when items are members of the same context and order does not control interpretation.

```text
Files:
- package.json
- tsconfig.json
- README.md
```

**Ordered List**

Use `1.` numbering when items must be performed or interpreted in sequence.

```text
Task:
1. Read [Files]
2. Identify inconsistencies
3. Apply corrections
4. Summarize changes
```

**Priority List**

Use `P0.`, `P1.`, and subsequent levels when items compete and precedence matters more than order of execution.

```text
Constraint:
P0. Preserve public behavior
P1. Minimize changed files
P2. Improve naming where obvious
```

Lower priority numbers represent stronger precedence. Items at the same priority level are co-equal unless another operation defines their order.

**Mixed Roles Across Sections**

```text
Scope:
- src/*.ts
- test/*.ts

Constraint:
P0. Do not change the public API
P1. Avoid unrelated refactors

Task:
1. Inspect [Scope]
2. Fix confirmed defects
3. Run relevant tests
```

<a id="ag-rules"></a>
### Rules

- **Dash for Membership** — use `-` for unordered values or parallel instructions
- **Number for Sequence** — use `1.` numbering only when order is meaningful
- **Priority for Precedence** — use `P0.` upward when conflicts must be resolved predictably
- **One Item Per Line** — keep each list item semantically singular
- **Atomic Ideas** — when an element contains a comma-separated set of distinct ideas:
  - Keep the shared statement as the parent
  - Move each idea into an indented bullet
- **Element Form** — begin each element with a capital letter and omit trailing punctuation unless exact form is semantically required by a:
  - Literal
  - Identifier
  - Path
  - Code fragment
  - Executable syntax
- **Local Consistency** — use one list type for one purpose within a list
- **Child Binding** — indented content belongs to the immediately preceding list item

<a id="ag-constraints"></a>
### Constraints

- Do not number items solely for decoration
- Do not use priority notation where ordinary order is sufficient
- Avoid combining `-`, numeric ordering, and priority notation on the same line
- Keep priority levels sparse; introduce only distinctions that affect behavior
- State dependencies explicitly rather than assuming adjacency implies them

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-unordered-membership"></a>
#### Unordered Membership

Represent members whose relative position does not affect meaning.

```text
[Files]:
- architecture.md
- testing.md
- ownership.md
```

<a id="ag-constraint-set"></a>
#### Constraint Set

Represent independent requirements without implying precedence.

```text
[Constraint]:
- Preserve existing behavior
- Minimize file changes
- Use friendly names
```

<a id="ag-schema-field-list"></a>
#### Schema Field List

Declare the fields belonging to a model.

```text
[FindingSchema]:
- `id`
- `category`
- `evidence`
- `resolution`
```

<a id="ag-import-set"></a>
#### Import Set

Declare independently required symbolic dependencies.

```text
Import:
- [Standard]
- [FindingSchema]
- [Validation]
```

<a id="ag-scoped-validator"></a>
#### Scoped Validator

State what a validator does and does not cover.

```text
[SchemaValidator]:
- Confirm required fields
- Confirm recognized types
- Do not validate semantic correctness
```

<a id="ag-composite-membership"></a>
#### Composite Membership

Represent one conceptual component as a collection of reusable members.

```text
[ArtifactSystem]:
- [Tree]
- [Map]
- [Route]
- [Registry]
```

---

<a id="ag-ordered-list"></a>
### Ordered List

<a id="ag-ordered-sequence"></a>
#### Ordered Sequence

Represent steps whose order affects execution or interpretation.

```text
Task:
1. Read [Source]
2. Extract [Candidates]
3. Validate [Candidates]
4. Render the result
```

<a id="ag-resolve-before-use"></a>
#### Resolve-Before-Use

Resolve a file-backed reference before treating it as loaded context.

```text
Task:
1. Resolve [Validator]
2. Apply [Validator] to [Artifact]
```

<a id="ag-lifecycle-bracketing"></a>
#### Lifecycle Bracketing

Initialize or clear mutable state before work and consume or discard it afterward.

```text
Task:
1. Clear [Results]
2. Populate [Results]
3. Validate [Results]
4. Render [Results]
5. Discard temporary state
```

<a id="ag-validator-chain"></a>
#### Validator Chain

Run focused validation passes in prerequisite order.

```text
Validation:
1. Run [SchemaValidation]
2. Run [ReferenceValidation]
3. Run [SemanticValidation]
4. Run [ConsistencyValidation]
```

<a id="ag-direct-source-verification"></a>
#### Direct Source Verification

Verify generated output against its authoritative source.

```text
Verify:
1. Read [Source]
2. Compare [Artifact] directly with [Source]
3. Report differences
```

<a id="ag-postcondition-check"></a>
#### Postcondition Check

Run a final focused check before returning or publishing.

```text
Task:
1. Generate [Artifact]
2. Validate [Artifact]
3. Apply [Postcheck]
4. Return [Artifact]
```

<a id="ag-idempotence-check"></a>
#### Idempotence Check

Run maintenance twice and confirm the second run makes no further changes.

```text
[Verify]:
1. Run [Maintenance]
2. Run [Maintenance] again
3. Confirm no additional changes
```

<a id="ag-conditional-continuation"></a>
#### Conditional Continuation

Evaluate a condition before performing dependent work.

```text
Task:
1. Determine feasibility AS [Fulfillable]
2. If [Fulfillable] is true, proceed with [Goal]
```

---

<a id="ag-priority-list"></a>
### Priority List

<a id="ag-priority-sequence"></a>
#### Priority Sequence

Rank items by authority, severity, urgency, or preference.

```text
[Constraint]:
P0. Do not change the public API
P1. Minimize file edits
P2. Improve naming
```

<a id="ag-authority-ranking"></a>
#### Authority Ranking

Prefer evidence from higher-authority sources.

```text
[Authority]:
P0. Authoritative source
P1. Maintained secondary source
P2. Inferred evidence
```

<a id="ag-severity-ranking"></a>
#### Severity Ranking

Order findings by impact rather than discovery order.

```text
[Severity]:
P0. Blocking
P1. Major
P2. Minor
P3. Informational
```

<a id="ag-stable-ordering-specification"></a>
#### Stable Ordering Specification

Define ranking keys and tie-breaking behavior explicitly.

```text
[Ordering]:
P0. Category rank
P1. Identifier
P2. Original position
```

<a id="ag-dependency-aware-priority"></a>
#### Dependency-Aware Priority

Separate urgency from prerequisite order before combining them.

```text
[Repair]:
P0. Blocking prerequisites
P1. Blocking dependents
P2. Major findings
P3. Minor findings
```
