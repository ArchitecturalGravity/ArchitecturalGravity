<a id="ag-symbolic-referencing"></a>
# Symbolic Referencing

Symbolic referencing uses bracket-wrapped identifiers (`[Target]`, `[Files]`, `[Property]`) to anchor semantic context as stable, reusable references. Brackets mark a symbolic identity; its declaration (`[Name]:` or `AS [Name]`) establishes the anchor, and subsequent `[Name]` occurrences refer to that same identity rather than creating a new one.

Symbolic referencing anchors semantic context to stable, reusable identities, reducing repetition while preserving consistency and constraining interpretation across subsequent references.

<a id="ag-purpose"></a>
### Purpose

- Preserve semantic identity
- Eliminate repetition
- Preserve semantic consistency
- Reduce token usage
- Constrain interpretation
- Resolve exact member ownership

<a id="ag-clarified-declaration-and-mutation-contract"></a>
## Clarified declaration and mutation contract

The first occurring `[Name]:` outside a section or symbol body declares a symbolic identity. Identifiers require matching brackets, PascalCase, and no whitespace. Every declaration requires subsequent reference, and references before declaration are invalid. Plain `Name:` headers and occurrences inside literal blocks or quoted values do not declare identities.

Referencing back to the symbol is done by invoking its name without a colon like `[Name]` -- whether a particular occurrence reads or mutates the context is for the executing agent to infer. Body boundaries follow the same Sectioning and Grouping rules.

The sole exception to these rules are `AS [Alias]` which represents the creation of an in-line symabolic reference 'alias' that embodies the immediately preceding context. A declared alias otherwise follows the same symbolic reference rules, and may be referenced anywhere thereafter.

**Definition**

```text
[Symbol]:
- Definition or list of definitions
- Conditional consideration
```

Referenced as:

```text
Task:
- Evaluate [Symbol]
```

**Symbol Composition**

```text
[Files]:
- ALL component.json files

[Property]:
- `inspector`

[Target]:
- [Files] + [Property]
```

<a id="ag-qualified-member-referencing"></a>
### Qualified Member Referencing

Qualified member referencing uses a dotted path (`[Record].id`) to identify an exact structural member of a previously declared symbol. `[Record]` identifies the owning context; `.id` identifies its `id` member without backticks. Unlike an unqualified backticked name, the dotted form fixes member ownership.

**Definition**

```text
[Record]:
- `id`: "R-01"
- `status`: "active"

Task:
=> Return [Record].id
```

Each member in a dotted path must already be declared under its preceding context. Nested paths such as `[Order].customer.address.city` follow the same rule for every segment. Qualified access does not itself declare, read, or mutate a member; the surrounding operation determines how the reference is used.

*Caution*: An LLM does not guarantee deterministic state tracking. Qualified member references rely on inference and may resolve incorrectly. Prefer shallow member structures; nesting members beneath other members compounds the risk of reference-resolution errors.

<a id="ag-semantic-anchoring"></a>
### Semantic Anchoring

<a id="ag-explicit"></a>
#### Explicit

An explicitly referenced context MUST be symbolically anchored.

```text
[Source]: src/main.py

Task:
- Analyze [Source]
```

<a id="ag-implied"></a>
#### Implied

A context whose meaning is conveyed entirely through procedural placement and is not later referred to should remain unanchored as a plain section.

```text
Context: Preserve public behavior.

Task: Refactor the implementation.
```

In this example, `Context` governs the following `Task` procedurally -- nothing explicitly references it, so `[Context]` is unnecessary.

Typical procedural contexts that may remain unanchored include:

- Initial scope that only establishes the prompt boundary
- Final task that only initiates execution
- Simple context or constraints consumed implicitly by the immediately following task

Caution: procedural placement is an *implied instruction* carried forward, so its agentic adherence may be tenuous.

<a id="ag-rules"></a>
### Rules

- **Instantiation** — symbols initially require require to be both anchored by brackets and end in a colon like `[Name]:`
- **Naming** — symbol naming is PascalCase without whitespace
- **Reference Required** — only create a symbol if it will later be referenced
- **Declaration Order** — symbol referencing must FOLLOW instantiation, never before it  
- **Invocation** — reference identities using `[Name]` without the colon
- **Qualified Member Access** — use `[Name].member` for a member exposed by `[Name]`; chained paths must follow declared parent-child members
- **Single Responsibility** — one distinct concept per symbol
- **Stable Identity** — subsequent references retain the original identity
- **Cross-Section Reuse** — symbols and aliases remain accessible after instantiation
- **No Nested Declarations** — only `AS [Name]` may instantiate within a symbol body, as the one exception

<a id="ag-constraints"></a>
### Constraints

- Do not reuse an established symbolic name to represent an unrelated identity
- Prefer plain sections for context consumed procedurally without later symbolic reference
- Symbolic referencing alone does not execute, expand, or mutate the referenced context
- Do not use dotted access to imply an undeclared member or select one owned only by another symbol

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-semantic-referencing-vs-procedural-context"></a>
### Semantic Referencing vs Procedural Context

Explicit reference requires an anchor:

```text
[Constraint]: Preserve existing API behavior.

Task:
- Refactor under [Constraint]
```

Procedural placement can carry context without a symbol:

```text
Constraint: Preserve existing API behavior.

Task: Refactor the implementation.
```

The distinction is reference, not prompt complexity.

<a id="ag-symbolic-anchor"></a>
### Symbolic Anchor

Anchor one explicit context as a stable symbolic reference.

```text
[Files]:
- All user.json files
```

<a id="ag-symbol-composition"></a>
### Symbol Composition

Define one anchor through other anchors.

```text
[Target]:
- [Files]
- [Field]
```

<a id="ag-file-backed-reference"></a>
### File-Backed Reference

Represent an externally maintained component without copying it.

```text
[Validator]:
- references/validator.md
```

<a id="ag-inheritance-link"></a>
### Inheritance Link

State that narrower context receives broader context.

```text
[Application]:
- Inherits [Repository]
- Add application-specific constraints
```

<a id="ag-predicate-defined-set"></a>
### Predicate-Defined Set

Define a collection through a condition applied to another collection.

```text
[Affected]:
- [Files] where [Field] matches [Invalid]
```

<a id="ag-exemplar-transfer"></a>
### Exemplar Transfer

Use one named artifact or behavior as the reference shape for another.

```text
[Goal]:
- Modify [Target] to match [Reference]
```

<a id="ag-mutable-state"></a>
### Mutable State

Represent mutable or unresolved state explicitly.

```text
[Findings]: []
[Lookup]: {}
[Processed]: 0
[Selected]: unset
```

<a id="ag-whole-record-selection"></a>
### Whole-Record Selection

Retain the complete selected record rather than reconstructing its value.

```text
[Winner]:
- Select one complete record from [Candidates]
```

<a id="ag-canonical-and-derived-references"></a>
### Canonical and Derived References

Keep authoritative state separate from views generated from it.

```text
[Records]:
- Canonical records

[Summary]:
- Derived from [Records]
```

<a id="ag-adjunct-reference"></a>
### Adjunct Reference

Refer to an authoritative definition instead of embedding a partial copy.

```text
[SecurityStandard]:
- policies/security.md

[FeatureContext]:
- Apply [SecurityStandard]
- Add feature-specific constraints
```
