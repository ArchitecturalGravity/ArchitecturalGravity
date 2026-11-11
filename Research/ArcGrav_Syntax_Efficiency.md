<a id="paper-syntax-efficiency"></a>
<a id="syntax"></a>
# ArcGrav & Syntax Efficiency

## Abstract

Prompt syntax can be visually compact without being token-minimal, and local token cost does not capture savings from reusing shared context. This paper evaluates **ArcGrav's serialization and compositional efficiency** against Python-like compact syntax, YAML, Markdown, and XML using matched prompt content and multiple tokenizers. In one `o200k_base` comparison, ArcGrav requires 93 tokens versus 81 for Python-like syntax, 89 for YAML, 97 for Markdown, and 142 for XML. Construct-level comparisons and reference-amortization analysis identify compositional reuse as a potential source of efficiency in heterogeneous, multi-step instructions. ArcGrav is a compact instructional control representation, not a universally token-minimal format. Interpretive accuracy and downstream task performance are evaluated separately.

## Introduction

This document evaluates ArcGrav against four widely recognizable structured prompt conventions:

- Python-like compact syntax
- YAML
- Markdown
- XML

<a id="syntax-serialization-efficiency"></a>
<a id="syntax-compositional-efficiency"></a>
**In plain language.** Syntax efficiency concerns how much space an instruction takes to express and how much repeated information named references can avoid.

Its scope is two related representation costs:

1. **Serialization efficiency** — how many model tokens are consumed by the syntax once its semantics are assumed
2. **Compositional efficiency** — how much repetition can be avoided through reusable names, references, and structural composition

Interpretation-acquisition cost is treated in [ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md). System-level human specification and downstream autonomous work are treated in [ArcGrav Operational Leverage](./Operational_Leverage/).

The central conclusion is:

> **ArcGrav is near the compact end of human-readable instruction formats, but it is not universally token-minimal. Its principal syntax-efficiency advantage is compositional: lightweight role separation and reusable symbolic references can reduce repetition in heterogeneous, multi-step prompts.**

ArcGrav should therefore be treated primarily as a compact **control syntax**, not as a universal bulk-data serialization format.

## Role Within the Research Program

This paper measures the representation's token cost and savings from compositional reuse. It complements [Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md), which tests how much explanation models need to interpret the notation, and [Operational Leverage](./Operational_Leverage/), which measures downstream agent activity.

<a id="syntax-token-minimality"></a>
## Character Minimality Is Not Token Minimality

Language models consume tokenizer units rather than characters. Byte-pair and related tokenizers merge common punctuation patterns, code fragments, quotation marks, delimiters, and words according to their vocabularies.

Consequently:

- Python-like assignment and array syntax can receive favorable token merges
- A two-character marker can still require multiple tokens
- A longer natural-language word can occasionally be represented by one token
- Visually compact notation is not necessarily tokenizer-compact
- Results differ across tokenizers and model families

Under the tested OpenAI-compatible encodings, representative ArcGrav prefixes had the following costs:

| Construct | `o200k_base` | `cl100k_base` | `p50k_base` |
| --- | ---: | ---: | ---: |
| `Scope:` followed by a newline | 2 | 2 | 3 |
| `- ` | 2 | 2 | 2 |
| `1. ` | 3 | 3 | 3 |
| `P0. ` | 4 | 4 | 4 |
| `[Focus]` | 3 | 3 | 3 |
| `=> ` | 2 | 2 | 2 |
| `AS ` | 2 | 2 | 2 |
| `"""` | 1 | 1 | 1 |
| `## Scope` followed by a newline | 3 | 3 | 3 |
| `<Scope>` and `</Scope>` together | 6 | 6 | 6 |

## Controlled Syntax Comparison

The benchmark serialized the same conceptual prompt in five formats:

- Python-like compact syntax
- YAML
- ArcGrav
- Markdown
- XML

The payload contained five named sections, two scope values, two focus values, three behavioral rules, three prioritized constraints, three ordered operations, and repeated references to named sections. Wording was held as constant as each format reasonably allowed. Counts exclude chat-protocol wrapper tokens.

| Format | Characters | `o200k_base` | `cl100k_base` | `p50k_base` | Relative to ArcGrav (`o200k`) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python-like compact | 377 | **81** | **82** | **101** | -12.9% |
| YAML | 369 | 89 | 90 | 104 | -4.3% |
| **ArcGrav** | 378 | **93** | **94** | 112 | baseline |
| Markdown | 386 | 97 | 98 | 110 | +4.3% |
| XML | 528 | 142 | 143 | 163 | +52.7% |

### Interpretation

For the tested prompt:

1. Python-like compact syntax used the fewest tokens
2. YAML was slightly more token-efficient than ArcGrav
3. ArcGrav was modestly more compact than conventional Markdown
4. ArcGrav was substantially more compact than paired-tag XML
5. The difference between ArcGrav and the three compact human-readable alternatives was relatively small

The benchmark shows that visible minimalism does not guarantee token minimalism. ArcGrav's syntax-efficiency case cannot rest on punctuation count alone.

## Comparative Format Profiles

### Python-Like Compact Syntax

**Strengths**

- Lowest token count in the controlled benchmark
- Compact arrays, variables, references, and operation-like expressions
- Well suited to algorithmic, state-based, or code-adjacent material

**Costs**

- Can imply execution, mutation, typing, or runtime semantics
- Quotes and escaping may be required for natural-language values
- Dense syntax can reduce human readability

**Best fit:** algorithms, state transitions, conditional logic, code work, and compact structured instructions.

### YAML

**Strengths**

- Human-readable hierarchy
- Compact section labels
- Natural-language values require relatively little punctuation
- Slightly lower token count than ArcGrav in the controlled benchmark

**Costs**

- Whitespace sensitivity
- Repeated list-marker overhead
- Anchors and aliases add their own syntax

**Best fit:** human-edited configuration, shallow or moderate hierarchy, and named settings.

### ArcGrav

**Strengths**

- Compact section labels
- Natural-language payloads require little escaping
- Lightweight symbolic references
- Compact priority, sequence, and operation markers
- References can substantially reduce repeated definitions
- More compact than conventional Markdown and XML in the controlled benchmark

**Costs**

- Bullets and priority markers are not tokenizer-minimal
- Slightly more expensive than Python-like compact syntax and YAML in the tested prompt
- References increase token cost when used only once

**Best fit:** reusable, heterogeneous, multi-step instruction graphs.

### Markdown

**Strengths**

- High corpus familiarity
- Excellent human readability
- Useful headings, lists, code blocks, emphasis, and explanatory prose

**Costs**

- Headings and presentation syntax add overhead
- References and transformations require additional conventions

**Best fit:** human-facing prompts, explanatory documents, reports, and mixed prose-instruction content.

### XML

**Strengths**

- Explicit opening and closing boundaries
- Clear nesting
- Attributes can encode relationships
- External parser and schema support

**Costs**

- High repeated-tag overhead
- Most expensive format in the controlled benchmark
- Verbose for lists and shallow instructions

**Best fit:** environments requiring XML compatibility, explicit closing boundaries, external parsing, or schema validation where token cost is secondary.

## Construct-Level Trade-offs

### Section Headers

ArcGrav uses:

```text
Scope:
```

This is similar in cost and appearance to YAML:

```text
Scope:
```

It is usually cheaper than a Markdown heading:

```text
## Scope
```

and substantially cheaper than paired XML tags:

```text
<Scope>
...
</Scope>
```

Python-like syntax may use assignment:

```text
scope = [...]
```

**Assessment:** ArcGrav section headers have low serialization overhead. Their direct token advantage over YAML is limited.

### Unordered Lists

ArcGrav, Markdown, and YAML commonly use:

```text
- Value
```

Python-like arrays can represent homogeneous collections more compactly:

```text
values = ["a", "b", "c"]
```

XML typically requires repeated element structure.

**Assessment:** ArcGrav bullets are appropriate for short, heterogeneous instruction lists. Large homogeneous collections are better represented with compact arrays or specialized data formats.

### Ordered Lists

ArcGrav uses explicit numbering:

```text
1. First operation
2. Second operation
```

Explicit numbering costs more than a simple bullet or compact array item, but it carries sequence information and provides stable references for later discussion.

**Assessment:** Use numbering when order is operationally meaningful, not merely for presentation.

### Priority Markers

ArcGrav uses:

```text
P0. Critical constraint
P1. Secondary constraint
```

`P0. ` is not token-minimal. It encodes precedence compactly using an engineering convention.

Comparable structures can be represented in Python-like assignments, YAML priority keys, Markdown labels, or XML attributes.

For critical conflicts, state the override explicitly as well as marking its priority:

```text
P0. Preserve the public API: This overrides all lower priorities
```

**Assessment:** Priority markers are semantically dense rather than token-minimal and should be used only when genuine precedence exists.

<a id="syntax-symbolic-reference"></a>
### Symbolic References

ArcGrav uses bracketed names:

```text
[Policy]:
- Preserve exact values

Task:
- Apply [Policy]
```

The brackets impose an immediate token cost. Their compositional value appears through reuse: later occurrences denote the same defined context without repeating its full definition.

Python-like syntax has variables; YAML has anchors and aliases; XML can use IDs and references; Markdown has no standard lightweight semantic-reference system for instruction graphs.

**Assessment:** Symbolic references are ArcGrav's strongest source of compositional token savings. They are most useful when a context is reused, operationally important, or referred to from multiple sections.

### Context Operations

ArcGrav marks operations with:

```text
=> Transform [Source]
```

Python-like syntax can use a function-shaped expression; YAML can use an operation key; Markdown can use an action label; XML can encode an operation element.

**Assessment:** `=>` has low direct syntax overhead and provides a compact operation marker. Its interpretation is evaluated separately from its tokenizer cost.

### Inline Aliasing

ArcGrav uses:

```text
[Source] AS [Derived]
```

Python-like syntax can use assignment, YAML can use named mappings, and XML can use attributes or nested elements.

**Assessment:** `AS` is compact; its comparative interpretability belongs to construct-level interpretive-efficiency testing.

### Literal Blocks

ArcGrav uses triple quotes:

```text
"""
source material
"""
```

Python uses the same delimiter for multiline strings, YAML supports block scalars, Markdown uses fenced blocks, and XML can use elements or CDATA.

**Assessment:** Triple quotes have very low syntax overhead. They are delimiters, not security boundaries.

### Wildcards

ArcGrav uses `*` as a wildcard where context establishes that meaning.

The symbol is extremely compact but semantically overloaded across programming, YAML, Markdown, regular expressions, mathematics, and ordinary technical notation.

**Assessment:** Wildcards are token-efficient but should be defined locally when ambiguity is possible.

<a id="syntax-reference-amortization"></a>
## Reference Amortization

Let:

- `D` be the token cost of repeating a definition
- `R` be the token cost of its symbolic reference
- `H` be the one-time declaration overhead
- `n` be the number of uses

Repeating the full definition costs:

```text
C_expanded = nD
```

Declaring and reusing a reference costs:

```text
C_reference = H + nR
```

A reference is token-beneficial when:

```text
n > H / (D - R)
```

A representative `o200k_base` test used:

```text
[Policy]:
- Do not modify files
- Preserve exact values
- Report source paths
```

and compared reuse through `[Policy]` with restating the policy for every target:

| Uses | ArcGrav reference | Fully expanded | Net saving |
| ---: | ---: | ---: | ---: |
| 1 | 31 | 26 | -5 |
| 2 | 42 | 53 | 11 |
| 3 | 53 | 80 | 27 |
| 5 | 75 | 134 | 59 |
| 10 | 130 | 269 | **139** |

In this example, the reference paid for itself on its second use.

The exact break-even point depends on definition length, reference-name tokenization, declaration syntax, surrounding prompt structure, and target tokenizer.

The same principle applies to variables in Python-like syntax, anchors in YAML, locally defined references in Markdown, and IDs or references in XML. A reference mechanism is token-efficient only when saved repetition exceeds declaration and reuse overhead.

## Scaling for Homogeneous Collections

A format efficient for instructions may be inefficient for bulk data.

ArcGrav, YAML, and Markdown commonly represent collections with one bullet prefix per item:

```text
- alpha
- beta
- gamma
```

Python-like compact syntax can encode the same collection as:

```text
values = ["alpha", "beta", "gamma"]
```

This generally scales better for large homogeneous collections because separators can be cheaper than repeated line prefixes. XML usually has the highest marginal overhead when every value requires opening and closing elements.

### Practical Rule

Use ArcGrav lists for:

- Constraints
- Ordered steps
- Behavioral rules
- Heterogeneous contextual items
- Small collections requiring human inspection

Use a specialized embedded representation for:

- Hundreds of IDs or filenames
- Flat records
- Matrices or tabular observations
- Nested machine-generated data
- Large repeated schemas

Suitable embedded representations include compact arrays, CSV, TSV, JSON, source code, and literal text blocks.

The control syntax and data syntax do not need to be the same format.

<a id="syntax-control-plane-data-plane"></a>
## Recommended Hybrid Architecture

ArcGrav is most syntax-efficient when used as a **control plane**, while the most suitable domain representation is used as a **data plane**.

```text
Scope:
- Repository files

[Policy]:
- Do not modify files
- Preserve exact values
- Report source paths

Data:
"""
{"records":[...]}
"""

Task:
1. Apply [Policy] to [Data]
2. Group matches by path
3. Return compact structured output
```

Use ArcGrav for retrieval scope, constraints, priorities, named references, execution order, and transformations. Embed another representation for bulk records, tables, source code, deeply nested data, or exact machine schemas.

> **Do not force one syntax to perform both control and bulk-data serialization when different representations are better suited to those roles.**

## Syntax Optimization Rules

1. **Do not create a symbol for a trivial one-use value**
2. **Prefer short symbol names that tokenize consistently**
3. **Use section labels instead of paired tags unless explicit closing boundaries are required**
4. **Use bullets for heterogeneous instructions, not bulk atomic data**
5. **Use numbering only when order is operationally meaningful**
6. **Use priorities only when precedence must be resolved**
7. **Use `=>` only for transformations; use static list items for static context**
8. **Define overloaded symbols such as `*` locally when ambiguity is possible**
9. **Embed compact arrays, JSON, CSV, TSV, or code when those representations match the data**
10. **Measure tokens with the target model's tokenizer**
11. **Avoid Python-like syntax when executable semantics would be misleading**
12. **Avoid deeply nested YAML when indentation errors would be costly**
13. **Avoid Markdown emphasis as the sole mechanism for operational priority**
14. **Avoid XML unless explicit boundaries, schemas, or downstream compatibility justify its overhead**

## Scope and Evidence Status

This paper reports controlled token counts and reference-amortization comparisons. It does not infer interpretive accuracy or task-level performance from serialization length.

This paper measures syntax cost once semantics are assumed. It does not establish that the cheapest serialization is the easiest representation for a model to interpret or the representation that produces the most useful autonomous work.

[Liu et al. (2025)](https://arxiv.org/abs/2502.04295) further demonstrates that formatting can affect model performance, reinforcing the distinction between tokenizer efficiency and behavioral effectiveness.

Those questions are evaluated separately:

- [ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md) measures representation-specific explanation required for correct interpretation.
- [Semantic Locality](./Context_Triad/Semantic_Locality.md) measures instruction position relative to surrounding context and point of use.
- [Semantic Shadow](./Context_Triad/Semantic_Shadow.md) measures how newer context changes the influence of earlier context.
- [Semantic Weight](./Context_Triad/Semantic_Weight.md) measures the influence associated with relative semantic mass.
- [ArcGrav Operational Leverage](./Operational_Leverage/) measures human specification burden against downstream agent activity and, in future controlled work, successful autonomous output.

Syntax comparisons should nevertheless be feature-matched. ArcGrav references should be compared with reference mechanisms available to other formats, priorities with equivalent priority mechanisms, operations with equivalent operation representations, and literal blocks with comparable delimiters. Otherwise an apparent format advantage may reflect differences in supplied structure rather than syntax cost.

## Conclusion

Within the five-format comparison:

- Python-like compact syntax used the fewest tokens
- YAML was slightly cheaper than ArcGrav
- ArcGrav was slightly cheaper than Markdown
- XML was substantially more expensive than all four alternatives

ArcGrav's distinctive syntax efficiency comes from composition rather than punctuation alone. References can amortize long definitions, while lightweight section, operation, priority, and sequence markers carry instruction structure with relatively little syntax.

> **ArcGrav provides a low-overhead, human-readable control syntax whose reusable references can produce substantial token savings when definitions are reused. In the tested comparison, it is more compact than Markdown and XML but less compact than Python-like syntax and YAML.**

ArcGrav should be combined with specialized data formats where bulk serialization is required.

## Related Papers

- [ArcGrav Research](./README.md)
- [ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md)
- [Semantic Locality](./Context_Triad/Semantic_Locality.md)
- [Semantic Shadow](./Context_Triad/Semantic_Shadow.md)
- [Semantic Weight](./Context_Triad/Semantic_Weight.md)
- [ArcGrav Operational Leverage](./Operational_Leverage/)

## References

- He, J., et al. (2024). *Does Prompt Formatting Have Any Impact on LLM Performance?*. arXiv preprint. https://arxiv.org/abs/2411.10541
- Liu, Y., et al. (2025). *Beyond Prompt Content: Enhancing LLM Performance via Content-Format Integrated Prompt Optimization*. arXiv preprint. https://arxiv.org/abs/2502.04295
- Mishra, M., et al. (2023). *Prompting with Pseudo-Code Instructions*. EMNLP. https://aclanthology.org/2023.emnlp-main.939/
- Puerto, H., et al. (2024). *Code Prompting Elicits Conditional Reasoning Abilities in Text+Code LLMs*. EMNLP. https://aclanthology.org/2024.emnlp-main.629/
- Tam, Z. R., et al. (2024). *Let Me Speak Freely? A Study On The Impact Of Format Restrictions On Large Language Model Performance*. EMNLP Industry. https://aclanthology.org/2024.emnlp-industry.91/
