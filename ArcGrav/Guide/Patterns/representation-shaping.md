<a id="ag-representation-shaping"></a>
# Representation Shaping

Defines how information is encoded, organized, compressed, structured, rendered, etc. for reliable use by the model or consumer. It includes schemas, canonical models, intermediate representations, templates, views, serialization, ordering, formatting, etc. while preserving declared semantic invariants.

<a id="ag-schemas-explicit-shape-contract"></a>
## Schemas — Explicit Shape Contract

Define required fields, types, optionality, and allowed values before producing records.

```text
[ResultSchema]:
- `name`: string
- `category`: enum
- `evidence`: list
- `confidence`: float from 0 to 1
```

<a id="ag-structural-identifiers-exact-name-representation"></a>
## Structural Identifiers — Exact Name Representation

Render an exact variable, property, field, key, schema member, model member, column, parameter, or equivalent structural name with backticks wherever that identifier appears as context.

Use the same representation when the identifier is declared, referenced, projected, compared, transformed, or mutated.

```text
[RecordSchema]:
- `accountId`: string
- `status`: string

Task:
=> Group [Records] by `accountId`
=> Set `status` to "complete"
```

When a name identifies an exact member of an external or modeled structure, preserve it with backticks everywhere it appears as that identifier. Backticks identify structure; double quotes identify text.

This is a representation convention, not an ArcGrav operator or syntax primitive. A stable representation preserves the identifier's semantic identity across declarations and later operations.

<a id="ag-data-modeling-relationship-first-model"></a>
## Data Modeling — Relationship-First Model

Represent entities and their relationships explicitly when flat lists hide dependencies.

```text
[Model]:
- Pattern belongs to Category
- Pattern may reference Pattern
- Evidence supports Pattern
```

<a id="ag-canonical-models-one-authoritative-representation"></a>
## Canonical Models — One Authoritative Representation

Normalize equivalent inputs into a single model used by later stages.

```text
[CanonicalPattern]:
- `name`
- `intent`
- `inputs`
- `procedure`
- `invariants`
- `mechanics`
- `example`
- `cautions`
- `outputs`
- `failureModes`
```

<a id="ag-scoped-inheritance-broad-to-narrow-context-model"></a>
## Scoped Inheritance — Broad-to-Narrow Context Model

Represent general and specialized context through explicit parent-child inheritance while placing each rule at the narrowest scope where it remains fully valid.

```text
[RepositoryContext]:
- All changes require validation

[ApplicationContext]:
- [RepositoryContext]
- Application changes require integration tests

[EndpointContext]:
- [ApplicationContext]
- Endpoint changes must preserve response shape
```

<a id="ag-canonical-referencing-reference-over-embedded-copy"></a>
## Canonical Referencing — Reference over Embedded Copy

Reference an authoritative policy, schema, model, operation, or instruction set instead of maintaining a partial duplicate in local context.

```text
[SecurityPolicy]:
- policies/security.md

[FeatureContext]:
1. [SecurityPolicy]
2. Feature-specific constraints only
```

<a id="ag-context-composition-composite-context-interface"></a>
## Context Composition — Composite Context Interface

Expose a coherent collection of related policies, models, constraints, or operations through one stable higher-level anchor.

```text
[PublicationStandard]:
- [PatternSchema]
- [FormattingRules]
- [ValidationRules]
- [ProvenanceRules]

Task:
- Apply [PublicationStandard]
```

<a id="ag-intermediate-representations-staged-reasoning-artifact"></a>
## Intermediate Representations — Staged Reasoning Artifact

Create a temporary representation between raw input and final output.

```text
[ParsedItems]:
=> Parse [RawText]
=> Emit one record per semantic unit

[GroupedItems]:
=> Group [ParsedItems] by `category`
```

<a id="ag-model-variants-purpose-specific-variant"></a>
## Model Variants — Purpose-Specific Variant

Derive variants from a canonical model rather than maintaining independent copies.

```text
[CompactView]:
=> Project `name`, `intent`, and `invariants` from [CanonicalPattern]
```

<a id="ag-derived-views-reversible-projection"></a>
## Derived Views — Reversible Projection

Produce filtered or aggregated views while retaining a reference to the canonical source.

```text
[CategoryIndex]:
=> Group [CanonicalPatterns] by `category`
=> Sort each group by `name`
```

<a id="ag-output-shaping-consumer-driven-projection"></a>
## Output Shaping — Consumer-Driven Projection

Select the minimum fields required by the audience.

```text
[PublishedView]:
=> Project [CanonicalPatterns] for guide readers
=> Include `intent`, `mechanics`, `example`, and `cautions`
=> Exclude extraction notes
```

<a id="ag-templating-stable-document-template"></a>
## Templating — Stable Document Template

Use a templated structure to make a document's output consistent.

````text
[Template]:
"""
# <category name>

## <pattern name>

**Intent:** <intent context>

**Use when:** <usage conditions>

```text
<example usage>
```

# Invariant:
[InvariantCondition]
"""
````

<a id="ag-formatting-and-rendering-render-last"></a>
## Formatting and Rendering — Render Last

Apply layout only after semantic content is complete.

```text
[Rendered]:
=> Render [PublishedView] as Markdown
=> Use one H1 per file
=> Use fenced blocks for prompt notation
```

<a id="ag-serialization-declared-encoding"></a>
## Serialization — Declared Encoding

Specify serialization rules when output will be consumed by tools or stored as data.

```text
[Serialization]:
- UTF-8
- Markdown
- LF line endings
- Repository-relative links
```

<a id="ag-composite-pattern-canonicalize-project-render"></a>
## Composite Pattern — Canonicalize, Project, Render

Separates meaning from presentation, reducing drift between files and making alternate views cheap to generate.

```text
[Canonical]:
=> Normalize [Source] into [Schema]

[View]:
=> Derive reader-facing fields from [Canonical]

[Output]:
=> Render [View] using [Template]
=> Serialize by [Serialization]
```
