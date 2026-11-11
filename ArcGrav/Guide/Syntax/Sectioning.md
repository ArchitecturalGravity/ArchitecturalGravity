<a id="ag-sectioning"></a>
# Sectioning

Sectioning uses a `Key:` header followed by child values to define a bounded context with an explicit semantic role. A section groups related information so the model can distinguish retrieval, framing, refinement, and execution context without relying on prose transitions.

Sectioning establishes explicit semantic boundaries, allowing the model to resolve prompt context by role, scope, and hierarchy with minimal inference.

<a id="ag-purpose"></a>
### Purpose

- Separate context by responsibility
- Establish clear scope and hierarchy
- Reduce ambiguity between data and instruction
- Make prompts easier to compose and scan

<a id="ag-section-verbiage"></a>
## Section Verbiage

These section headers are examples, not reserved terms. Any single-word header is valid if its role is clear.

<a id="ag-retrieval"></a>
### Retrieval

`Scope` `Boundary` `Focus` `Target` `Directory` `URL` `Attachment`

<a id="ag-framing"></a>
### Framing

`Context` `Observation` `Behavior` `Example` `Specification` `State` `Fact` `Error`

<a id="ag-refinement-optional"></a>
### Refinement (optional)

`Consideration` `Constraint` `Ambiguity` `Unknown` `Assumption` `Note` `Mode` `Limit` `Caution`

<a id="ag-execution"></a>
### Execution

`Task` `Action` `Question` `Evaluate` `Review` `Compare` `Explain` `Generate` `Simulate` `Modify` `Diagnose`

---

**Definition**

```text
Key:
- Value one
- Value two
```

**Common Section Roles**

```text
Scope:
- Guide/Syntax

Context:
- Existing pages define compact ArcGrav syntax

Constraint:
- Preserve the established documentation style

Task:
- Populate all empty syntax pages
```

Section names are descriptive rather than reserved. A section header should communicate how its children are meant to be interpreted.

**Nested Sections**

```text
Scope:
- Guide:
  - Syntax
  - Examples
- Research:
  - ArcGrav_Research.md
```

<a id="ag-rules"></a>
### Rules

- **Header Binding** — child context belongs to the nearest preceding `Key:` header at its indentation level
- **Single Responsibility** — each section should represent one clear semantic role
- **Explicit Children** — place section values on following lines rather than hiding them in the header
- **Consistent Indentation** — indent nested section children by two spaces
- **Clear Verbiage** — use concise headers whose role can be inferred directly
- **Operational Separation** — keep source context, constraints, and requested actions in distinct sections when practical

<a id="ag-constraints"></a>
### Constraints

- Avoid decorative or redundant sections
- Avoid vague headers such as `Stuff:` or `Other:`
- Do not overload one section with unrelated context types
- Prefer a single-word header when it remains clear
- Empty sections should be omitted

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-role-ordered-frame"></a>
### Role-Ordered Frame

Place grounding before interpretation, and interpretation before execution.

1. `Scope`
2. `Context`
3. `Refinement`
4. `Constraint`
5. `Task`

Typical order:

1. Retrieval
2. Framing and refinement
3. Execution

<a id="ag-sectioned-context"></a>
### Sectioned Context

Give one bounded concern a descriptive name.

```text
Constraint:
- Preserve the public API
- Hide secret keys
```

Headers describe roles; they are not reserved keywords.

<a id="ag-scalar-section"></a>
### Scalar Section

Bind a section directly to one value when membership is unnecessary.

```text
Scope: C:\Project
```

<a id="ag-capability-invocation"></a>
### Capability Invocation

Declare the skill, tool, or capability governing the task.

```text
Using:
- $cartographic-agentic-contexting
- $browser-skill
- http://www.webpage.com/instructions.txt
```

<a id="ag-completion-hook"></a>
### Completion Hook

Separate follow-up work that occurs after the primary task.

```text
OnComplete:
1. Update related references
2. Run [Orchestration] 
```

<a id="ag-phase-labeled-work"></a>
### Phase-Labeled Work

Use descriptive sections to separate kinds of work.

```text
ModifyComponentContext:
- Update the component
- Delete stale logic

VerifyComponentContext:
- Confirm the output shape
- Update the report
```
