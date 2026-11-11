<a id="ag-inline-representation"></a>
# Inline Representation

Inline representation applies local interpretive forcing by imposing constraints on how an agent may infer the semantic role of marked content, fixing its exact identity.

Interpretive forcing is a constraint on inference: the marked representation narrows which semantic roles the agent may assign to the enclosed content without altering how the surrounding language is otherwise interpreted. The effect remains local to the marked span, reducing the range of admissible interpretations for that content while leaving surrounding language to be interpreted normally rather than as literal, executable, or otherwise operational.

- Bare content is interpreted according to surrounding context
- Backticks (`` `name` ``) identify exact structural names
- Double quotes (`"text"`) identify exact textual values

Inline Representation leaves semantic interpretation to surrounding context while allowing exact structural and textual identity to be preserved where required.

<a id="ag-purpose"></a>
### Purpose

- Distinguish interpreted content from exact representation
- Preserve exact field, key, property, parameter, and member names
- Preserve exact textual values and phrases
- Reduce ambiguity between semantic interpretation and exact identity
- Maintain stable representation across declarations and later references

**Definition**

```text
[RecordSchema]:
- `accountId`: string
- `status`: string

Task:
=> Group [Records] by `accountId`
=> Set `status` to "complete"
```

Here, the surrounding instruction is interpreted by the agent. `accountId` and `status` identify exact structural names. `"complete"` identifies an exact textual value.

**Bare Content**

```text
Task:
- Identify matching records
- Return the most relevant result
```

Bare content is interpreted semantically according to its grammatical role and surrounding context.

It does not by itself assert exact structural or textual identity.

Other ArcGrav syntax may assign specific meaning to otherwise bare forms such as symbols, operations, aliases, scalar values, paths, or keywords.

**Structural Name**

```text
[RecordSchema]:
- `sourceId`: string
- `displayName`: string

Task:
=> Compare `sourceId` across [Records]
=> Project `displayName`
```

Use backticks for exact variables, properties, fields, keys, schema members, model members, columns, parameters, or equivalent structural names.

Backticked names do not contain whitespace.

A qualified reference such as `[RecordSchema].sourceId` identifies an exact structural member of a symbolic context; the member follows the dot without backticks.

**Textual Value**

```text
[Status]:
- "complete"

Task:
=> Return "No matching record"
```

Use double quotes for exact textual values, tokens, labels, messages, errors, constants, and phrases.

**Same Characters, Different Role**

```text
status
`status`
"status"
```

The first is interpreted from surrounding context.

The second identifies the exact structural name `status`.

The third represents the exact textual value `"status"`.

Representation follows semantic role rather than the characters alone.

<a id="ag-rules"></a>
### Rules

- **Bare Content Is Interpreted** — unmarked content is interpreted according to surrounding context
- **Backticks Identify Structure** — use backticks for unqualified exact structural names
- **Qualified Structural Access** — use `[Name].member` to identify an exact member owned by `[Name]`, without backticks around the dotted segment
- **Double Quotes Identify Text** — use double quotes for exact textual values and phrases
- **Local Exactitude** — marked forms constrain their represented content while surrounding bare content remains interpreted
- **No Bare Exactness** — bare content does not become structurally or textually exact solely because it resembles a known identifier or value
- **No Backtick Whitespace** — a backticked structural name MUST NOT contain whitespace
- **Exact Structural Form** — preserve the exact structural identifier rather than converting a human-readable label into a backticked phrase
- **Stable Representation** — preserve exact structural identifiers when declared, referenced, projected, compared, transformed, or mutated, using qualified syntax where ownership must be explicit
- **Role Determines Representation** — use representation according to whether content is interpreted, structural, or textual
- **Other Syntax Applies** — representation does not override meaning established by another ArcGrav syntax construct
- **No Implied Operation** — bare content, backticks, and double quotes do not by themselves read, resolve, execute, mutate, or transform anything

<a id="ag-constraints"></a>
### Constraints

- Do not use backticks as general emphasis or prose quotation
- Do not place whitespace inside a backticked structural name
- Do not use double quotes for an exact structural name
- Do not use backticks for an exact textual value
- Do not assume bare content is an exact identifier or exact textual value
- Do not substitute a human-readable phrase for the actual structural identifier
- Prefer a defined whitespace-free identifier such as `displayName` or `display_name` over an invalid form such as `` `Display Name` ``
- Use a Literal Quote Block rather than inline double quotes for multiline source material
- Preserve the distinction when interpreted content, structural names, and textual values appear in the same expression

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-interpreted-instruction"></a>
#### Interpreted Instruction

Use bare content when surrounding context is sufficient to determine meaning.

```text
Task:
- Identify matching records
- Summarize the result
```

<a id="ag-field-assignment"></a>
#### Field Assignment

Distinguish the interpreted operation from the exact field and textual value.

```text
=> Set `status` to "complete"
```

<a id="ag-partial-exactitude"></a>
#### Partial Exactitude

Constrain only the portion that requires exact identity.

```text
=> Set `status` to the resolved value
```

Here, `status` is exact structure. The resolved value is interpreted from context.

<a id="ag-structural-projection"></a>
#### Structural Projection

Name exact members of a structure.

```text
=> Project `name`, `category`, and `confidence` from [Results]
```

<a id="ag-structural-comparison"></a>
#### Structural Comparison

Refer consistently to exact structural members.

```text
=> Compare `sourceId` with `targetId`
```

<a id="ag-textual-comparison"></a>
#### Textual Comparison

Preserve an exact text value for comparison.

```text
=> Select records where `status` equals "pending review"
```

<a id="ag-textual-label"></a>
#### Textual Label

Represent a human-readable phrase as text rather than structure.

```text
[Label]:
- "Display Name"
```

Do not represent the phrase as:

```text
`Display Name`
```

If the corresponding structural field is named `displayName`, reference that exact identifier instead.

```text
=> Set `displayName` to "Primary Account"
```

<a id="ag-same-lexeme-in-different-roles"></a>
#### Same Lexeme in Different Roles

Use representation to distinguish identical characters serving different roles.

```text
status
`status`
"status"
```

The bare form is interpreted from context. The backticked form is exact structure. The quoted form is exact text.

<a id="ag-mixed-interpretation-and-exactitude"></a>
#### Mixed Interpretation and Exactitude

Preserve exact identities within an otherwise interpreted instruction.

```text
=> Find records associated with `accountId` and return "No matching record" when none exist
```

<a id="ag-quoted-scalar-vs-literal-source"></a>
#### Quoted Scalar vs Literal Source

Use double quotes for a short inline textual value.

```text
[Expected]:
- "Connection refused"
```

Use Literal Quote Blocks and backticked members for multiline source material.

```text
[ErrorLog]:
- `error1`:
  """
  ERROR Connection refused
  RETRY Attempt 1
  """
- `error2`:
  """
  ERROR Connection refused
  RETRY Attempt 2
  """
```
