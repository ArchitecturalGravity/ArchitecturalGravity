<a id="ag-explicit-block-binding"></a>
# Explicit Block Binding

Explicit block binding uses ` ↳` at the end of a complete statement or operation to bind the following indented context to the entire preceding expression.

It is intended as an edge-case disambiguation tool when ordinary trailing `:` parenthood could appear to attach to, redefine, or extend the final token or symbolic reference in the expression rather than clearly scope children under the expression as a whole.

Explicit block binding is intentionally narrow. Most ArcGrav hierarchy should continue to use ordinary `:` parenthood and indentation. ` ↳` exists for expressions whose final token—particularly a symbolic reference—would otherwise make the ownership of a following child block unclear.

<a id="ag-purpose"></a>
### Purpose

- Bind child context to a complete preceding statement or operation
- Preserve a trailing symbolic reference as an invoked reference rather than making it appear to own the child block
- Resolve ambiguous parent-child scope without rewriting a compact expression
- Provide an explicit escape hatch for rare cases where normal `:` grouping is visually or semantically unclear

**Definition**

```text
=> Operation using [Context] ↳
  - Child instruction
```

The ` ↳` applies to the complete line before it. The indented child belongs to `Operation using [Context]` as a whole; it does not define, mutate, or append context to `[Context]`.

<a id="ag-edge-case"></a>
### Edge Case

Consider an operation that naturally ends with a symbolic reference but also needs child instructions. Adding ordinary `:` directly after the reference:

```text
=> Create implementation plan following [Constraint]:
  - Do not create new branch
```

can visually suggest that `[Constraint]` is being extended or made the parent of the nested instruction, even when the intended parent is the complete operation.

Use explicit block binding to remove that ambiguity while preserving the compact operation:

```text
=> Create implementation plan following [Constraint] ↳
  - Do not create new branch
```

Interpretation:

```text
(Create implementation plan following [Constraint])
  └─ Do not create new branch
```

The nested instruction qualifies the complete implementation-plan operation. `[Constraint]` remains an existing symbolic reference and is not redefined.

<a id="ag-rules"></a>
### Rules

- **Whole-Line Binding** — ` ↳` binds the following indented block to the complete preceding expression
- **Trailing Position** — place ` ↳` at the end of the parent expression
- **Indented Children** — add two spaces to child context, following normal ArcGrav grouping rules
- **Reference Preservation** — a symbolic reference immediately before ` ↳` remains an invocation of that reference and is not redefined or extended
- **Explicit Escape Hatch** — use ` ↳` when ordinary `:` grouping would create scope ambiguity
- **Nearest Parent Binding** — once ` ↳` establishes the parent, normal indentation rules apply within its child block

<a id="ag-constraints"></a>
### Constraints

- Do not use ` ↳` as a general replacement for `:`
- Do not use ` ↳` when normal section or item grouping is already unambiguous
- Do not place child context at the same indentation level as the explicitly bound parent
- Avoid using  ` ↳` merely for visual decoration; it must resolve an actual ownership or scope ambiguity

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-operation-ending-in-a-reference"></a>
### Operation Ending in a Reference

Bind a local instruction to the complete operation without making the trailing reference appear to own it.

```text
=> Create implementation plan following [Constraint] ↳
  - Do not create new branch
```

<a id="ag-nested-conditional-under-a-complete-operation"></a>
### Nested Conditional Under a Complete Operation

```text
=> Identify next eligible incomplete items in [Roadmap] ↳
  => If no eligible items:
    - Append "NO ELIGIBLE" to [Plan] and return
```

<a id="ag-prefer-normal-grouping-when-unambiguous"></a>
### Prefer Normal Grouping When Unambiguous

Do not introduce ` ↳` when ordinary parenthood already expresses the structure cleanly.

```text
Constraint:
- API:
  - Preserve response shape
```

Use explicit block binding only when it contributes information that `:` and indentation alone do not communicate clearly.
