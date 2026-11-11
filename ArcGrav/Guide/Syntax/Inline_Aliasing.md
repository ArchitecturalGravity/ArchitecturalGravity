<a id="ag-inline-aliasing"></a>
# Inline Aliasing

Inline aliasing uses `AS` like a keyword to anchor a new symbolic reference like `AS [Alias]` that embodies the immediately preceding context. The alias symbol can then be referenced to later like a normal symbolic reference. This is the sole exception to normal symbolc reference rules prohibiting instantating symbols within another symbol body.

Inline Aliasing creates reusable symbolic references during interpretation or execution, allowing intermediate context to be named and reused without restating or predefining it.

<a id="ag-purpose"></a>
### Purpose

- Capture a derived or observed context without repeating its definition
- Name intermediate results during execution
- Preserve continuity across multi-step instructions
- Reduce ambiguity when later steps depend on prior output

**Definition**

```text
Context:
- Immediate context AS [Alias]
```

Referenced after creation as:

```text
Task:
- Evaluate [Alias]
```

**Observation Aliasing**

```text
[Files]:
- ALL component.json files

[Property]:
- `inspector`

Observation:
- [Files] contains [Property] AS [FileProperties]

Task:
- Compare [FileProperties]
```

**Execution Aliasing**

```text
Task:
1. Combine [Primary] and [Secondary] AS [Combined]
2. Normalize [Combined] AS [Normalized]
3. Evaluate [Normalized]
```

**Scoped Aliasing**

```text
Comparison:
- [CurrentState] against [DesiredState] AS [StateDelta]

Constraint:
- Limit changes to [StateDelta]
```

<a id="ag-rules"></a>
### Rules

- **Immediate Prior Binding** — `AS [Alias]` names the context directly preceding it
- **Procedurally Referenced** — invoke the alias only after it is created
- **Symbolic Form** — aliases use bracket-wrapped identifiers
- **Single Binding** — one alias should represent one derived context
- **Stable Identity** — later references retain the first identity; another `AS [Name]` is a duplicate instantiation, not a reference
- **Explicit Source** — the aliased context must be identifiable without inference

<a id="ag-constraints"></a>
### Constraints

- Do not use `AS` before the context it names
- Every instantiated alias must have a subsequent reference; do not create unused aliases
- Do not use `AS` as ordinary prose when it could be mistaken for an alias declaration
- Prefer direct symbolic definition when the reference does not depend on immediate prior context
- Keep alias names clear, concise, and semantically specific

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-transformation-alias"></a>
### Transformation Alias

Name each stage of a transformation.

```text
Task:
1. Parse [Source] AS [Parsed]
2. Normalize [Parsed] AS [Normalized]
3. Validate [Normalized] AS [Validated]
4. Output [Validated]
```

<a id="ag-boolean-alias"></a>
### Boolean Alias

Name the result of a condition or feasibility check.

```text
Determine whether [Goal] is supported AS [Fulfillable]
```

<a id="ag-candidate-alias"></a>
### Candidate Alias

Capture discovered values for later resolution.

```text
Collect matching records AS [Candidates]
```

<a id="ag-filtered-alias"></a>
### Filtered Alias

Name the subset produced by a filtering operation.

```text
Remove invalid records from [Records] AS [ValidRecords]
```

<a id="ag-comparison-alias"></a>
### Comparison Alias

Name a normalized or canonical representation used for comparison.

```text
Canonicalize [Candidate] AS [Signature]
```

<a id="ag-immediate-binding-rule"></a>
### Immediate-Binding Rule

Bind the alias only to the directly preceding expression.

```text
Extract records AS [Records]
```
