<a id="ag-constraint-gating"></a>
# Constraint Gating

Converts policies, rules, permissions, capabilities, preconditions, invariants, postconditions, formatting requirements, etc. into explicit checks that control whether an operation may begin, continue, or complete. It expands and enforces operating contract boundaries.

<a id="ag-policies-policy-first-gate"></a>
## Policies — Policy-First Gate

Evaluate governing policies before planning an action.

```text
[PolicyGate]:
=> Identify applicable policies
=> Reject prohibited actions
=> Preserve the allowed portion of the task
```

<a id="ag-safety-constraints-safe-execution-envelope"></a>
## Safety Constraints — Safe Execution Envelope

Define hazardous boundaries and safer fallback behavior.

```text
[Safety]:
- Do not expose secrets
- Do not perform destructive writes without explicit scope
- Redact sensitive evidence in published output
```

<a id="ag-business-rules-domain-rule-gate"></a>
## Business Rules — Domain Rule Gate

Express business rules as testable conditions rather than narrative guidance.

```text
[Rules]:
- A published pattern must belong to exactly one primary category
- Every category file must contain at least one pattern
```

<a id="ag-scope-constraints-target-membership-check"></a>
## Scope Constraints — Target Membership Check

Verify every proposed operation is within the declared scope.

```text
[ScopeGate]:
=> Confirm each target is under Guide/Patterns
=> Reject unrelated paths
```

<a id="ag-capability-checks-tool-capability-gate"></a>
## Capability Checks — Tool Capability Gate

Confirm that required read, write, and validation capabilities actually exist.

```text
[CapabilityGate]:
- Can read current files
- Can create or update Markdown files
- Can verify resulting content
```

<a id="ag-preconditions-entry-contract"></a>
## Preconditions — Entry Contract

List conditions that must be true before execution.

```text
[Preconditions]:
- Categories are defined
- Source material is available
- Target directory resolves
```

<a id="ag-invariants-must-remain-true-contract"></a>
## Invariants — Must-Remain-True Contract

Declare properties that must hold throughout the workflow.

```text
[Invariants]:
- Source files remain unchanged
- Category names remain canonical
- No git history is used as source material
```

<a id="ag-execution-guards-guarded-mutation"></a>
## Execution Guards — Guarded Mutation

Place checks immediately before a side effect.

```text
Task:
1. Confirm target path and current existence
2. Select create or update operation
3. Write complete content
4. Verify the result
```

<a id="ag-formatting-constraints-render-gate"></a>
## Formatting Constraints — Render Gate

Validate output-specific requirements separately from semantic correctness.

```text
[FormatGate]:
- Markdown parses cleanly
- One H1 per file
- Code fences are balanced
- Links are repository-relative
```

<a id="ag-postconditions-exit-contract"></a>
## Postconditions — Exit Contract

Define the state required after completion.

```text
[Postconditions]:
- Ten category files exist
- Each file is populated
- The index links every category file
```

<a id="ag-failure-handling-bounded-failure-path"></a>
## Failure Handling — Bounded Failure Path

Specify how to fail without corrupting state or hiding partial completion.

```text
[Failure]:
- Stop writes to the failing path
- Preserve completed files
- Record the exact unmet condition
- Continue independent work when safe
```

<a id="ag-composite-pattern-guarded-execution-contract"></a>
## Composite Pattern — Guarded Execution Contract

Turns constraints into executable decision points instead of passive reminders.

```text
[Gate]:
=> Validate [Policies]
=> Validate [Preconditions]
=> Check [Capabilities]
=> Assert [Invariants]

[ExitGate]:
=> Validate [Postconditions]
=> Validate [FormatGate]
=> Apply [Failure] on any failed assertion

Task:
1. Execute only when [Gate] passes
2. Run [ExitGate]
```
