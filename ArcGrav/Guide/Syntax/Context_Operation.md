<a id="ag-context-operation"></a>
# Context Operation

A context operation is invoked using an `=>` arrow followed by defining the operation to tell the model how to transform child context. The model treats it accordingly as an operation and not a context item.

Context Operations define procedural manipulation of context, improving inference clarity and compactness without expanding prompt prose or requiring multiple prompts to accomplish the same thing.

<a id="ag-purpose"></a>
### Purpose

- Encodes a transformation applied to context
- Separates context from operation

**Definition**

```text
[Source]:
- Input value one
- Input value two

[Derived]:
=> Transform [Source] into [Shape]
```

**Nested Operations**

```text
[Phrase]:
=> Repeat 3 times:
  => Concatenate without line break:
    - "Lorem ipsum dolor sit amet"
    - "consectetur adipiscing elit"
    - "sed do eiusmod tempor"
```

**Operation Composition**

```text
[RawRecords]:
- CSV attachment rows

[NormalizedRecords]:
=> Parse [RawRecords]
=> Convert headers to camelCase
=> Remove empty rows
=> Group by `accountId`
```

<a id="ag-rules"></a>
### Rules

- **Nearest Context Binding** — operations apply to their context children
- **One Operation Per Line** — keep each `=>` instruction singular and explicit
- **Nested Order** — indent child operations under the parent operation
- **No Sequencing** — do not combine `=>` with `-`, `1.`, or priority markers on the same line
- **Child White Spacing** — add two spaces to children following operation instruction

<a id="ag-constraints"></a>
### Constraints

- Avoid using `=>` when a static list is sufficient
- Use explicit operations over vague or subjective instructions

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-context-operation-2"></a>
### Context Operation

Apply one explicit behavior to context.

```text
[Parsed]:
=> Parse [Source]
```

<a id="ag-derived-anchor"></a>
### Derived Anchor

Define an anchor as the output of an operation.

```text
[Normalized]:
=> Normalize [RawRecords]
```

<a id="ag-operation-chain"></a>
### Operation Chain

Apply several singular transformations in sequence.

```text
[NormalizedRecords]:
=> Parse [RawRecords]
=> Normalize field names
=> Remove empty rows
=> Group by `accountId`
```

<a id="ag-nested-operation"></a>
### Nested Operation

Indent a child operation beneath the operation controlling it.

```text
[Phrase]:
=> Repeat 3 times:
  => Concatenate without line break:
    - "Alpha"
    - "Beta"
```

<a id="ag-apply-to-invocation"></a>
### Apply-To Invocation

Apply a reusable operation, standard, schema, or gate to a named target.

```text
[Finding]:
=> Apply [Validation] to [SourceExcerpt]
```

<a id="ag-conditional-gate"></a>
### Conditional Gate

Prevent an operation from proceeding unless its preconditions are satisfied.

```text
[Generate]:
=> Apply [ContextGate]
=> If the gate passes, produce [Artifact]
```

<a id="ag-fail-fast-stop"></a>
### Fail-Fast Stop

Terminate when later output would be structurally invalid or misleading.

```text
[Parsed]:
=> Parse [Source]
=> Raise when required structure is invalid
```

<a id="ag-recursive-self-application"></a>
### Recursive Self-Application

Reapply an operation after making progress toward termination.

```text
[Traverse]:
=> Process the current node
=> Add unvisited children to [Pending]
=> Select the next node
=> Apply [Traverse]
```

<a id="ag-independent-verification-operation"></a>
### Independent Verification Operation

Inspect an artifact without modifying it.

```text
[Verify]:
=> Compare [Artifact] directly with [Source]
=> Report defects
=> Do not modify [Artifact]
```

<a id="ag-instrumented-operation"></a>
### Instrumented Operation

Produce execution statistics alongside the operation's domain result.

```text
[Finalize]:
=> Populate [ExecutionStats]
=> Return [Artifact] with [ExecutionStats]
```
