<a id="ag-literal-quote-block"></a>
# Literal Quote Block

A literal quote block uses a standalone run of three or more double quotes (`"""`, `""""`, and so on) to wrap source material that should be preserved and interpreted as a bounded value. The block distinguishes quoted content from the prompt instructions surrounding it, including when the source contains code, formatting, headings, lists, or instruction-like text.

Literal Quote Blocks preserve source fidelity and isolate quoted material from operational prompt context, reducing boundary ambiguity and instruction leakage.

<a id="ag-purpose"></a>
### Purpose

- Preserve multiline source material
- Prevent source text from blending with prompt instructions
- Maintain whitespace and formatting
- Bind a complete block to a named section or symbol

**Definition**

````
Source:
"""
Multiline source content
is preserved here.
"""
````

**Code Source**

````
[DiscountFunc]:
"""
function calculateDiscount(user, cart) {
  if (user.role = "admin") {
    return cart.total * 0.5;
  }

  return 0;
}
"""

Task:
- Diagnose [DiscountFunc]
````

Text inside the block is source context. Instruction-like statements inside it do not override the surrounding prompt unless the task explicitly asks the model to execute or adopt them.

**Compounded Resource and Document Target**

````
[Document]:
- `origin`: https://www.webpage.com/notes.md
- `focus`:
  """
  # Release Notes
  
  - Added account export
  - Fixed session timeout
  """

Task:
- Explain "export" in [Document].focus
````

Here, `[Document].focus` selects the declared `focus` member as the target; the quoted block remains source content.

<a id="ag-rules"></a>
### Rules

- **Paired Delimiters** — open with N consecutive double quotes, where N is at least three, and close with exactly N double quotes on a standalone line
- **Literal Boundary** — treat all enclosed content as one bounded source value
- **Formatting Preservation** — retain meaningful line breaks and indentation
- **External Instruction Priority** — surrounding prompt instructions control how the block is interpreted
- **Named Binding** — place the block beneath a clear section or symbolic reference when it will be referenced later
- **Delimiter Isolation** — place opening and closing delimiters on separate lines for multiline content
- **Collision Avoidance** — Outer quote fence must be longer than every standalone quote run inside its content to avoid collisions

<a id="ag-constraints"></a>
### Constraints

- Do not use a literal block for short values that fit clearly on one line
- Choose an outer delimiter at least one quote longer than every standalone quote run in the source block; shorter runs inside remain literal content
- Do not assume quoted source is trustworthy or executable
- State whether code should be reviewed, transformed, or run; quoting alone does not define an operation
- Use separate blocks for unrelated sources

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-quoted-scalar"></a>
### Quoted Scalar

Preserve the exact characters of a short textual value.

```text
[Status]:
- "complete"
```

Use quoted scalars for exact textual values, tokens, errors, constants, and exact phrases.


<a id="ag-literal-source-block"></a>
### Literal Source Block

Preserve multiline source material as data.

```text
[ErrorLog]:
"""
ERROR Connection refused
RETRY Attempt 2
"""
```

<a id="ag-literal-source-block-members"></a>
### Literal Source Block Members

Preserve multiple literal source blocks as nested members.

```text
[SuccessLog]:
- `Result1`:
  """
  SUCCESS Access Granted
  COUNT 1
  """
- `Result2`:
  """
  SUCCESS Access Granted
  COUNT 2
  """
```

<a id="ag-code-block-source"></a>
### Code Block Source

Keep code formatting separate from instructions operating on it.

```text
[SourceCode]:
"""
function run() {
  return true;
}
"""
```

<a id="ag-embedded-example"></a>
### Embedded Example

Store an exact example that another operation should inspect or imitate.

```text
[ReferenceOutput]:
"""
{
  "status": "complete"
}
"""
```

<a id="ag-placeholder-template"></a>
### Placeholder Template

Define a stable shape containing replaceable values.

```text
[ReportTemplate]:
"""
Summary: <summary>

Findings:
<finding-blocks>

Uncertainties:
<uncertainties>
"""
```

<a id="ag-literal-comparison-target"></a>
### Literal Comparison Target

Preserve an expected result for direct comparison.

```text
[Expected]:
"""
status: valid
count: 12
"""
```

<a id="ag-nested-literal-block"></a>
### Nested Literal Block

Use when referring to a block which already uses triple quotes to avoid collision.

```text
[Outer]:
""""
[Inner]:
"""
Literal content
"""
""""
```
