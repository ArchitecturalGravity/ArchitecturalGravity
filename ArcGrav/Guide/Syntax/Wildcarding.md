<a id="ag-wildcarding"></a>
# Wildcarding

Wildcarding uses `*` to represent any matching value within a named path, filename, pattern, or context set. A wildcard expands the target scope without requiring every matching item to be written explicitly.

Wildcarding compresses predictable sets into pattern-based targets, reducing enumeration while retaining explicit selection criteria.

<a id="ag-purpose"></a>
### Purpose

- Compactly select multiple related targets
- Express pattern-based scope
- Avoid enumerating predictable values
- Preserve flexibility as matching items change

**Definition**

```text
Scope:
- Data_*.txt
```

This refers to all matching files whose names begin with `Data_` and end with `.txt`.

**Path Wildcarding**

```text
Scope:
- Guide/Syntax/*.md
- src/*/index.ts
```

**Symbolic Composition**

```text
[Files]:
- Guide/Syntax/*.md

Task:
- Review [Files]
```

**Broad Context Wildcarding**

```text
Scope:
- All *_test.py files under tests/*
```

Natural-language qualifiers may be used when the wildcard alone cannot express recursion or another matching rule clearly.

<a id="ag-rules"></a>
### Rules

- **Asterisk Means Any Match** — `*` stands for any sequence of matching characters or values in the stated context
- **Pattern Preservation** — treat literal text surrounding `*` as required match criteria
- **Scoped Expansion** — resolve matches only within the enclosing section or explicitly named location
- **Explicit Recursion** — state recursive scope in words when directory depth is not unambiguous
- **Post-Expansion Consistency** — apply the same instruction to every resolved match unless exceptions are defined

<a id="ag-constraints"></a>
### Constraints

- Avoid an unqualified `*` when it could select an unsafe or excessively broad scope
- Do not assume shell-specific wildcard behavior unless the environment is named
- State exclusions explicitly
- Prefer symbolic references when the same wildcarded set is reused
- Use literal quote blocks when `*` is source text rather than a selector

---

<a id="ag-idiomatic-usage"></a>
## Idiomatic Usage

<a id="ag-wildcard-selection"></a>
### Wildcard Selection

Identify a family of matching resources compactly.

```text
Files:
- src/**/component.json
- tests/*Service.test.ts
```

<a id="ag-extension-family"></a>
### Extension Family

Select all resources sharing a file extension.

```text
Files:
- **/*.json
```

<a id="ag-name-pattern-family"></a>
### Name-Pattern Family

Select resources matching a naming convention.

```text
[Files]:
- AGENTS.route.*.md
- AGENTS.map.*.md
```

<a id="ag-bounded-wildcard"></a>
### Bounded Wildcard

Pair a wildcard with an explicit root or traversal boundary.

```text
Directory:
- src/services

Files:
- **/*.component.json
```

<a id="ag-wildcard-with-exclusions"></a>
### Wildcard with Exclusions

State exclusions when a broad wildcard could match unintended resources.

```text
Files:
- **/*.json

Exclude:
- node_modules/**
- generated/**
```
