<a id="ag-grammatical-reduction"></a>
# Grammatical Reduction

Linguistic overhead can be reduced by **omitting or simplifying grammatical material** when its contribution is recoverable from the remaining wording, explicit symbolic references, and governing context. This is **contextual grammatical reduction**, not indiscriminate deletion of frequent words.

The goal is the shortest **sufficiently unambiguous** expression that preserves the intended operation and its requirements. A shorter expression is not necessarily equivalent, easier to interpret, or cheaper for a model to process.

Grammatical reduction is authoring guidance, **not** a new ArcGrav syntax primitive, a set of reserved words, or a guarantee of token savings or model performance. Structural notation, exact values, and explicit contracts take precedence over grammatical abbreviation.

---

<a id="ag-purpose"></a>
## Purpose

- Remove linguistic scaffolding that contributes no necessary distinction in a particular context
- Preserve the operation, participants, relationships, scope, conditions, and required outcome
- Use ArcGrav's explicit structure to make otherwise implicit referents recoverable
- Keep reductions inspectable, portable, and reversible when ambiguity appears

**Omissibility belongs to a word in context, not to its grammatical category.** An article can be dispensable before an explicit symbol yet essential when distinguishing a particular item from any item.

---

<a id="ag-linguistic-basis"></a>
## Linguistic Basis

**Function words** primarily express grammatical relationships and distinctions. They include articles, determiners, prepositions, conjunctions, auxiliaries, and other relatively closed grammatical classes. They are not necessarily semantically empty: `not`, `only`, `must`, `if`, and `into` can materially affect an instruction.

**Ellipsis** is the omission of material recoverable from the linguistic or situational context. **Telegraphic style** uses abbreviated constructions, often omitting articles or copulas. These phenomena help explain why compact instructions can remain understandable, but neither establishes a universal rule for safe omission.

**Stop words** are a task-dependent category used in information retrieval and NLP. Membership in a stop-word list is not a semantic-preservation test; deleting stop words from instructions can remove conditions, negation, modality, or participant relationships.

Grammatical reduction may leave an expression conventional English, or produce a compact instruction style accepted by the intended model. Neither grammaticality nor apparent readability is sufficient proof that the intended task has been preserved.

---

<a id="ag-contextual-omissibility"></a>
## Contextual Omissibility

A grammatical element is a candidate for omission only when its contribution is already determined by the remaining expression or by explicit, authoritative context.

Consider:

```text
[Report]:
- Approved report artifact

Task:
=> Return the [Report]
```

A compact form is:

```text
Task:
=> Return [Report]
```

The declared symbol identifies the artifact; the article is not needed to select it in this context. The shortened task still depends on the declaration of `[Report]`.

Contrast `Review a contract` with `Review the contract`. The latter normally points to an identifiable contract; the former permits an unspecified one. Removing or exchanging their articles can change the target unless the relevant contract is independently and unambiguously established.

**Interpretive principle:** Remove a word only when its semantic contribution is recoverable, not merely because the word is common or grammatical.

---

<a id="ag-reduction-mechanisms"></a>
## Reduction Mechanisms

The following are candidate techniques, not interchangeable rules.

| Mechanism | Expanded form | Candidate reduction | Necessary condition |
| --- | --- | --- | --- |
| Article omission | `Return the [Report]` | `Return [Report]` | The reference identifies the intended artifact |
| Determiner-phrase simplification | `Inspect each of the files in [Scope]` | `Inspect each file in [Scope]` | `each` and the scope remain intact |
| Optional complementizer omission | `Confirm that [Report] includes sources` | `Confirm [Report] includes sources` | The clause boundary remains unambiguous |
| Purpose-phrase shortening | `Review the files in order to find conflicts` | `Review the files to find conflicts` | `in order to` expresses purpose, not another constraint |
| Structural substitution | `Status is pending` | `Status: pending` | A label-value statement is intended; no tense or assertion is lost |

**Structural substitution is a rewrite, not word deletion.** It is appropriate only when ArcGrav notation conveys the same relationship. Omission of a copula or auxiliary without an alternative structure can distort time, status, obligation, or voice.

Some reductions save little or no tokens under a particular tokenizer. Removing words and introducing replacement punctuation should be evaluated together.

---

<a id="ag-function-word-categories"></a>
## Function-Word Categories and Their Limits

| Category | Examples | Reduction consideration |
| --- | --- | --- |
| Articles and determiners | `the`, `a`, `an`, `those` | Potentially omit where an explicit reference or fixed scope preserves identification |
| Complementizers | `that` | Sometimes optional where a following clause remains unambiguous |
| Auxiliary and copular verbs | `is`, `are`, `be`, `have` | Often encode tense, aspect, voice, or obligation; omit only in an appropriate abbreviated construction |
| Prepositions | `of`, `to`, `from`, `into`, `against` | Some are removable inside longer constructions; others establish indispensable direction or standards |
| Conjunctions and conditionals | `and`, `or`, `if`, `unless` | Usually necessary to preserve logical relationships; do not treat them as disposable glue |
| Modals and quantifiers | `must`, `may`, `all`, `each`, `only` | Preserve when they establish obligation, permission, quantity, or scope |

The same spelling can serve different grammatical or semantic roles. Do not maintain an unconditional allowlist of deletable words.

---

<a id="ag-semantic-preservation"></a>
## Semantic Preservation Boundary

**The grammatical reduction boundary is reached when removing more wording changes an intended distinction or makes model interpretation unacceptably unreliable.** It is task- and model-dependent, not a fixed percentage of words.

Preserve the following whenever material:

| Information | Examples | Why it matters |
| --- | --- | --- |
| Participant identities | `[Source]`, `[Target]`, exact IDs | Selects the correct objects |
| Direction and standards | `from`, `into`, `against` | Distinguishes sources, destinations, and comparison criteria |
| Negation and exceptions | `not`, `never`, `except`, `unless` | Can reverse or restrict behavior |
| Quantification and scope | `all`, `each`, `only`, `exactly` | Determines coverage and selection |
| Ordering and dependencies | `before`, `after`, `until` | Determines when actions may occur |
| Modality and authorization | `must`, `may`, `should` | Distinguishes requirements, permission, and recommendation |
| State, uncertainty, and failure | `pending`, `invalid`, `unresolved` | Prevents false claims of success |
| Exact syntax and literals | `[Reference]`, `=>`, `` `fieldName` ``, `"the request failed"` | Preserves symbols, structural keys, and literal content |

A grammatical word can be essential even when it looks like scaffolding. For example:

```text
=> Merge [Patch] into [Baseline]
```

Removing `into` obscures the presented direction. Similarly, `=> Validate [Records] against [Schema]` must retain the standard-setting relationship. Grammatical reduction does **not** override [Symbolic Referencing](../Syntax/Symbolic_Referencing.md), [Context Operation](../Syntax/Context_Operation.md), or [Inline Representation](../Syntax/Inline_Representation.md).

Exact quoted text, external field names, keys, paths, and contractually fixed output must not be rewritten merely to improve compactness.

---

<a id="ag-arcgrav-applications"></a>
## ArcGrav Applications

Explicit references often make articles redundant because the symbol already identifies the relevant context.

```text
[Records]:
- Imported record set

[Schema]:
- Required record fields

[ValidationResult]:
=> Validate all of the records in [Records] against the [Schema]

Task:
=> Return the [ValidationResult]
```

Candidate reduction:

```text
[Records]:
- Imported record set

[Schema]:
- Required record fields

[ValidationResult]:
=> Validate all records in [Records] against [Schema]

Task:
=> Return [ValidationResult]
```

The revision removes `of the` and two articles while preserving `all`, `in`, `against`, the symbolic identities, and the operations. It does **not** assert that validation passed or that the records comply with the schema.

Do not remove a section label, symbolic declaration, operation marker, operand, or explicit contract on the assumption that a model will infer it from the surrounding wording.

---

<a id="ag-safe-and-unsafe-examples"></a>
## Safe and Unsafe Reduction Examples

| Expanded expression | Shortened expression | Assessment |
| --- | --- | --- |
| `Return the [Report]` | `Return [Report]` | Reasonable when `[Report]` is declared and unique |
| `Summarize each of the files in [Documents]` | `Summarize each file in [Documents]` | Preserves per-file scope |
| `Confirm that [Report] includes citations` | `Confirm [Report] includes citations` | Usually preserves the clause and requirement |
| `Merge [Patch] into [Baseline]` | `Merge [Patch] [Baseline]` | **Unsafe:** loses destination direction |
| `Do not publish [Draft]` | `Publish [Draft]` | **Unsafe:** reverses the prohibition |
| `Inspect only failing records` | `Inspect failing records` | **Unsafe:** expands the permitted scope |
| `Review each file` | `Review files` | **Unsafe when per-file processing matters:** removes the distributive requirement |
| `Return the approved report` | `Return report` | **Unsafe without an independent reference:** may lose identity and approval restriction |

An omission can be acceptable for one task and unsafe for another. Contextual interpretation, not the grammatical category, governs the decision.

---

<a id="ag-reduction-guidance"></a>
## Reduction Guidance

1. **Identify the intended contract.** Record the operation, participants, relationships, scope, modality, constraints, and expected output
2. **Find recoverable scaffolding.** Look for articles, optional complementizers, or longer grammatical constructions already resolved by explicit context
3. **Reduce locally.** Remove the smallest candidate span; prefer a clear short phrase over a cryptic or reordered one
4. **Recheck the contract.** Confirm that no participant, direction, quantity, condition, permission, state, or exact value changed
5. **Restore ambiguity.** Reintroduce necessary words if multiple plausible readings appear or if examples produce divergent behavior
6. **Measure and test.** Compare actual token counts and model behavior on representative inputs before adopting a recurring reduction pattern

This is an authoring procedure, not required prompt boilerplate.

---

<a id="ag-evaluation-and-limitations"></a>
## Evaluation and Limitations

Assess reduction along **two independent dimensions**:

- **Semantic reliability:** Does the shortened form preserve intended behavior and constraints across typical, ambiguous, and failure cases?
- **Token economy:** Does the target tokenizer actually represent the shortened text with fewer tokens?

A useful evaluation compares the original and reduced instructions on the same inputs and checks output selection, omissions, condition handling, side effects, and failure reporting. Token reductions alone are not evidence of behavioral equivalence. A reduction that introduces ambiguity or a material regression should be reversed even when it saves tokens.

The safety of an abbreviated expression may vary with model, language, domain, context window, and surrounding examples. No global omission list or guaranteed compression ratio follows from the linguistic categories above.

---

<a id="ag-relationship-to-other-principles"></a>
## Relationship to Other Principles

- **[Lexical Representation](./Lexical_Representation.md)** increases meaning carried by names and familiar procedural operators.
- **Grammatical Reduction** reduces recoverable linguistic overhead without changing the intended operator or its contract.
- **[Symbolic Referencing](../Syntax/Symbolic_Referencing.md)** avoids repeating established context through reusable identities.
- **[Sectioning](../Syntax/Sectioning.md)** and **[Context Operation](../Syntax/Context_Operation.md)** provide explicit roles and operations that can make some grammatical material redundant.

These mechanisms can be combined, but none authorizes omission of required information. **Reduction principle:** Remove wording only when the remaining representation preserves intended operational meaning with acceptable reliability.
