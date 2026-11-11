<a id="ag-grouping"></a>
# Grouping

Grouping uses indentation to bind child context beneath a parent item or section. Whitespace establishes hierarchy: aligned items are peers, while indented items qualify, expand, or operate within the nearest parent context.

Grouping converts whitespace into semantic hierarchy, allowing dense prompts to preserve parent-child relationships with minimal repetition.

<a id="ag-purpose"></a>
### Purpose

- Represent hierarchy without repeated prose
- Bind details to the correct parent
- Express nested scope and substructure
- Preserve compact, readable context trees

**Definition**

```text
Key:
- Parent:
  - Child one
  - Child two
- Peer value
```

**Nested Grouping**

```text
Retrieval:
- Backend Services:
  1. Auth:
    - URL: website.com/auth
    - Owner: Identity team
  2. User:
    - Path: C:\Services\User
    - Owner: Platform team
- Frontend:
  - Path: C:\Project\Web
```

**Grouped Constraints**

```text
Constraint:
- API:
  P0. Preserve response shape
  P1. Preserve status codes
- Implementation:
  P0. Avoid new dependencies
  P1. Minimize file changes
```

<a id="ag-rules"></a>
### Rules

- **Nearest Parent Binding** — indented context belongs to the nearest preceding item at the prior indentation level
- **Peer Alignment** — items with equal indentation are interpreted as siblings
- **Two-Space Indentation** — use two spaces for each nesting level
- **Explicit Parenthood** — use a trailing `:` when an item exists primarily to contain children
- **Stable Hierarchy** — maintain the same indentation level for the duration of a group
- **Semantic Nesting** — nest only when the child qualifies or belongs to the parent

<a id="ag-constraints"></a>
### Constraints

- Avoid deep nesting when a symbolic reference would be clearer
- Do not use indentation decoratively
- Do not mix tabs and spaces
- Avoid attaching one child group ambiguously to multiple parents
- Flatten groups whose hierarchy does not affect interpretation

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-nested-grouping"></a>
### Nested Grouping

Represent parent-child or containing-contained context.

```text
Scope:
- Backend Services:
  - Auth: Services/auth
  - Users: Services/users
```

<a id="ag-contract-block"></a>
### Contract Block

Group inputs, outputs, invariants, side effects, and failure behavior.

```text
[ResolveContract]:
- Input: Candidate records
- Output: Resolved records
- Invariants: Preserve source records
- Failure: Raise on malformed structure
```

<a id="ag-explicit-uncertainty-record"></a>
### Explicit Uncertainty Record

Represent unresolved information as structured data.

```text
[Uncertainty]:
- `field`: `owner`
- `reason`: "Conflicting sources"
- `availableEvidence`:
  - [SourceA]
  - [SourceB]
- `status`: "unresolved"
```

<a id="ag-evidence-carrying-record"></a>
### Evidence-Carrying Record

Store a conclusion together with its evidence and provenance.

```text
[Finding]:
- `claim`: "Reference is stale"
- `source`: "repository-map.md"
- `location`: "line 42"
- `validator`: [ReferenceValidator]
```

<a id="ag-result-sidecar"></a>
### Result Sidecar

Return operational metadata beside, but separate from, domain output.

```text
[Result]:
- `artifact`: [Artifact]
- `executionStats`:
  - `processed`: 20
  - `resolved`: 18
  - `unresolved`: 2
```

<a id="ag-model-variant"></a>
### Model Variant

Group shared fields separately from variant-specific fields.

```text
[RootModel]:
- Apply [SharedFields]
- `parent`: null

[LeafModel]:
- Apply [SharedFields]
- `children`: []
```
