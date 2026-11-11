<a id="paper-interpretive-efficiency"></a>
<a id="interpretive"></a>
# ArcGrav & Interpretive Efficiency

## Abstract

A structured instruction can be short yet costly to use if a language model must first learn what its notation means. This paper examines **interpretive efficiency**: how much representation-specific explanation a model needs to recover the intended meaning of an instruction format reliably. It distinguishes that cost from the number of tokens used to express an instruction and from success on the underlying task. The ArcGrav hypothesis is that familiar structural cues can convey compositional relationships with less teaching than unfamiliar, privately defined mappings. The proposed evaluation compares ArcGrav with optimized familiar formats and randomized isomorphic encodings, measuring zero-specification interpretation, specification requirements, repair and reuse costs, remapping, and downstream execution. The aim is to identify the conditions under which reduced interpretation cost yields practical value, not to assume a universal advantage for one format.

## Introduction

Structured instructions encode relationships as well as words: a rule may govern several steps, a label may point to a reusable context, and the order of operations may matter. A notation can express those relationships in few tokens while leaving their meaning unclear to a model that has not seen its conventions. A separate grammar or legend can resolve the ambiguity, but that explanation is part of the cost of using the format.

This cost is especially visible when prompts are passed to a different model, introduced in a fresh conversation, or reused across multiple tasks. In one-shot use, even a short specification may outweigh serialization savings; in sustained use, the initial investment may be amortized, or repeated repairs may make the format more expensive than it first appears. Neither token counts for the instruction alone nor final task success reveals which case applies.

This paper asks how much format-specific teaching is needed before a model reliably recovers an instruction's intended structure. It defines interpretive efficiency, distinguishes recognition of familiar cues from acquisition of new mappings, and proposes measurements of zero-specification interpretation, specification requirements, and reuse and repair costs. ArcGrav provides a concrete test case: its headings, references, priority markers, and operation cues are intended to be understood without a separate formal grammar. The evaluation compares that hypothesis against familiar structured alternatives and randomized symbolic formats, while checking whether correct interpretation translates into correct task execution.

## Role Within the Research Program

This paper owns the definition and evaluation of interpretive efficiency: zero-specification interpretation, acquisition, specification-dose response, maintenance, repair, and lifecycle cost. [Model-Native Structural Representation](./Model_Native_Structural_Representation.md) develops the general hypothesis that model-familiar structural cues can support interpretation. [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md) evaluates serialization and tokenizer cost rather than teaching cost.

## The missing cost in structured prompting

The issue becomes visible in a compact private notation:

```text
^R
!0 preserve values
X(records)>validate
```

A model may need the following definitions before it can reliably recover the intended relationships:

```text
DSL:
- ^R introduces a rule set
- !0 means highest-priority constraint
- X(name)>operation means apply operation to the named context
- Parentheses identify contextual references
```

The compact notation has not eliminated semantic information; it has moved some of that information into a separate specification. This paper asks how much *representation-specific* instruction must be supplied to establish the intended meaning. Whether the notation itself saves tokens is a separate question addressed by [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md).

<a id="interpretive-interpretive-efficiency"></a>
## Interpretive efficiency and its boundaries

**In plain language:** Interpretive efficiency asks how much teaching a model needs before it reliably understands an instruction format.

**Interpretive efficiency** is the degree to which a structured representation's intended semantics can be recovered from the expression, nearby task context, and model-internalized associations without additional conversation-specific rules for interpreting the representation. High interpretive efficiency means little or no separate grammar, schema explanation, symbol table, or demonstration set is needed. Low interpretive efficiency means those additions are necessary to reach reliable interpretation.

The measured input is representation-specific information, not task-specific facts, source documents, or ordinary domain definitions. Interpretation accuracy is also distinct from successful task execution and compliance with a requested output format. Two formats may reach the same final accuracy but require different amounts of explanation to get there.

<a id="interpretive-representation-recognition"></a>
<a id="interpretive-representation-acquisition"></a>
### Recognition and acquisition

**Representation recognition** means recovering structural relationships primarily from familiar associations and local structure. **Representation acquisition** means establishing a new mapping from definitions, demonstrations, or grammar supplied in the current context. Acquisition here does not imply a persistent update to model parameters during inference.

This behavioral distinction corresponds to the task-recognition versus task-learning distinction developed in [Model-Native Structural Representation](./Model_Native_Structural_Representation.md). Related work includes [Pan et al. (2023)](https://aclanthology.org/2023.findings-acl.527/) on in-context task recognition and learning and [Honovich et al. (2022)](https://arxiv.org/abs/2205.10782) on instruction induction. The interpretive-efficiency prediction is that recognizing a familiar representation generally requires less local specification than acquiring a private mapping.

<a id="interpretive-zero-specification-interpretability"></a>
### Zero-specification interpretability

**Zero-specification interpretability** is the ability to infer a representation's intended structural relationships without a representation-specific grammar, syntax manual, symbol definition, or prior demonstration teaching those relationships in the current context. The task may still depend on ordinary facts, examples, or source material.

This is the most direct cold-start test of interpretive efficiency, but it is not a complete measure: one format may need a small explanation and another a large one to reach the same reliability. The full comparison therefore measures how interpretation changes as useful specification is added.

<a id="interpretive-acquisition-maintenance-repair"></a>
## Interpretation cost over a representation's lifecycle

A format can impose costs when first introduced, while reused, and when errors must be corrected. These costs should be measured separately from errors in the underlying task.

<a id="interpretive-acquisition-cost"></a>
<a id="interpretive-maintenance-cost"></a>
<a id="interpretive-repair-cost"></a>
| Cost | What it measures |
| --- | --- |
| Acquisition (`T_acquisition`) | Tokens used to establish representation-specific semantics |
| Maintenance (`T_maintenance(t)`) | Tokens used to restate, refresh, or normalize those semantics over conversational time `t` |
| Repair (`T_repair`) | Tokens spent correcting failures attributable to representation interpretation |
| Per-use syntax (`T_syntax,i`) | Tokens needed to express each use of the representation, included to assess the complete lifecycle |

For `N` uses over horizon `t`, `T_representation(N,t)` is the sum of acquisition, the syntax tokens across all uses, maintenance, and repair. Average cost per use, `T_average(N,t)`, is that total divided by `N`. Thus the original lifecycle accounting is retained without requiring a separate derivation. Tokenizer-level comparisons remain the responsibility of [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md).

Interpretation errors, retries, repair turns, and cross-context transfer failures should also be reported as separate outcomes rather than folded into a single token score. [Semantic Shadow](./Context_Triad/Semantic_Shadow.md) addresses the broader temporal dependencies that may create maintenance cost.

<a id="interpretive-cold-start"></a>
<a id="interpretive-lifecycle-amortization"></a>
### Cold start and amortized reuse

A **cold start** occurs before the representation has been defined in the current context. **Amortized reuse** occurs after its semantics have been established and reused over multiple instructions.

For example, a DSL that needs 300 grammar tokens but saves 20 tokens on each later use breaks even on serialization after approximately 15 uses, ignoring maintenance and repair. Consequently, studies should report total and per-use costs across increasing numbers of uses, not just one-shot totals.

A low-acquisition-cost format should be particularly valuable for one-off prompts, ephemeral agents, frequent context restarts, cross-agent delegation, context reconstruction, and model switching. The difference may narrow when a DSL grammar remains in a stable system prompt, the representation is reused extensively, the model has been fine-tuned for the DSL, or a parser or runtime handles interpretation.

The relevant outcome is a cost-performance frontier across lifecycle lengths, not a universal ranking by token count.

<a id="interpretive-arcgrav-design-hypothesis"></a>
## The ArcGrav design hypothesis

ArcGrav uses model-interpreted conventions—headings, lists, indentation, bracketed references, priorities, arrows, and explicit task order—to express compositional instructions without requiring a parser-enforced grammar:

```text
Scope:
- repository files

[Policy]:
P0. Preserve public API
P1. Minimize changes

[Normalized]:
=> Normalize [Records]

Task:
1. Apply [Policy]
2. Validate [Normalized]
3. Report results
```

The wider account of associative retrieval, task recognition, binding, and structural cues belongs to [Model-Native Structural Representation](./Model_Native_Structural_Representation.md). The specific proposal here is that ArcGrav can offer DSL-like compositional structure while imposing relatively little teaching cost.

Two tests follow. **Recoverability** asks whether models can identify the intended relationships without an ArcGrav specification. **Operational sufficiency** asks whether those inferred relationships support accurate execution, not merely plausible descriptions of the notation.

## Research hypotheses

<a id="interpretive-representation-cost-hypothesis"></a>
**H1 — Representation-cost hypothesis.** Semantically isomorphic structured representations can require different amounts of context-specific information to reach the same interpretation accuracy.

<a id="interpretive-prior-alignment-hypothesis"></a>
**H2 — Prior-alignment hypothesis.** Structural cues whose relevant associations are already model-internalized and mutually compatible in context will, on average, require less local specification than randomized isomorphic encodings.

<a id="interpretive-interpretation-cost-frontier"></a>
**H3 — ArcGrav-specific hypothesis.** At matched semantic expressiveness, ArcGrav will occupy a favorable position on the interpretation-cost/performance frontier compared with both unfamiliar isomorphic representations and strong familiar structured baselines.

<a id="interpretive-operational-value-hypothesis"></a>
**H4 — Operational-value hypothesis.** Reduced teaching cost matters only if the recovered semantics are accurate enough to preserve or improve downstream task execution.

These claims are tested at two levels: whether a model recovers the representation's intended meaning and whether that understanding improves work done with the representation.

## Zero-specification probes

Small, directly scorable examples can isolate individual constructs before testing full tasks.

### Named contexts and operations

```text
[Alpha]:
- red
- blue

[Beta]:
=> Count [Alpha]
```

Ask what `[Beta]` operates on, what role `=>` plays, and whether `[Alpha]` names a context containing two items.

### Priority

```text
Rules:
P0. Return A
P1. Return B
```

Ask which rule takes precedence. Do not treat priority markers as guaranteed operators merely because they resemble familiar conventions.

### Hierarchy and scope

```text
Files:
- src/
  - Include:
    - *.py
  - Exclude:
    - tests/*
```

Ask which inclusion and exclusion rules belong to `src/`, and how indentation determines parent-child binding.

### References and policy application

```text
[Policy]:
- Preserve exact values

[Source]:
- A
- B

Task:
=> Apply [Policy] to [Source]
```

Ask what `[Policy]` refers to, what `[Source]` contains, and which operation connects them.

These probes should be scored for intended relationships rather than merely whether the model produces an acceptable-looking answer. Downstream task success may occur without applying the intended prompt semantics, as cautioned by [Webson and Pavlick (2022)](https://aclanthology.org/2022.naacl-main.167/). Prompt-sensitivity measurements can also reflect evaluation artifacts rather than semantic differences; [Hua et al. (2025)](https://aclanthology.org/2025.emnlp-main.1006/) provides relevant methodological context. [Liu et al. (2025)](https://arxiv.org/abs/2502.04295) motivates treating format as an experimental factor alongside content.

## Comparison representations

The comparison must distinguish the advantage of having *any* structure from the possible advantage of using familiar structural cues. Strong familiar baselines are as important as unfamiliar encodings.

### Familiar baselines and the pseudocode boundary

Cold-start conditions should include optimized natural-language prose, Markdown without special local conventions, YAML with ordinary familiar structure, Python-like pseudocode, ArcGrav without prior explanation, randomized isomorphic DSLs with and without grammar, and format-optimized variants where appropriate. A fully specified formal task-specific DSL may also be included.

Pseudocode is a particularly strong comparator. [Mishra et al. (2023)](https://aclanthology.org/2023.emnlp-main.939/) reports advantages for pseudocode-like prompting in some evaluated tasks and model families, with structural cues contributing in ablations. Pseudocode can already express variables, references, order, hierarchy, and composition. The test should also check whether code-like notation induces unintended assumptions about assignment, mutation, return values, types, or side effects. [Instructional Representation & the Prose–Program Boundary](./Instructional_Representation.md) treats that boundary in detail.

<a id="interpretive-randomized-isomorphic-representations"></a>
### Randomized isomorphic representations

An isomorphic comparison preserves the same semantic graph while replacing its cues.

**ArcGrav condition**

```text
[Policy]:
P0. Preserve values

Task:
=> Apply [Policy]
```

**Arbitrary condition**

```text
~Policy~
Q7 Preserve values

Task:
%! ~Policy~
```

Both express one named policy, a highest-priority constraint, and an operation applying the policy. One arbitrary notation is insufficient: punctuation, whitespace, identifiers, tokenization, corpus frequency, and accidental associations may influence outcomes. Use multiple randomized encoding families.

| Condition | Representation | Local specification |
| --- | --- | --- |
| A | ArcGrav | None |
| B | Randomized isomorphic encoding | None |
| C | The same arbitrary encoding | Supplied |
| D | Strong familiar structured baseline | No special local grammar |

If A exceeds B but C closes the gap, the result favors an acquisition-cost explanation rather than a generic benefit from structure. If D matches or exceeds A, the ArcGrav-specific advantage weakens, even if the broader prior-alignment hypothesis remains viable.

Arbitrary mappings are learnable; [Wei et al. (2023), *Symbol tuning*](https://aclanthology.org/2023.emnlp-main.61/) and [Wei et al. (2023), *Larger language models do in-context learning differently*](https://arxiv.org/abs/2303.03846) provide relevant counterpoints. The prediction concerns the amount of context-specific evidence needed, not an inability to learn unfamiliar symbols.

<a id="interpretive-specification-requirement"></a>
## Operational measurement

Interpretive efficiency is measured by how accuracy changes when representation-specific explanation is added. In compact notation, `A_R(s)` is interpretation accuracy for representation `R` after `s` specification tokens. The **specification requirement** `S_τ(R)` is the minimum `s` for which `A_R(s) >= τ`, where `τ` is a preregistered target accuracy. This preserves the distinction between final accuracy and the information needed to reach it, consistent with the methodological motivation in [Voita and Titov (2020)](https://aclanthology.org/2020.emnlp-main.14/).

Useful measures are:

- **`I0 = A_R(0)`:** interpretation accuracy with no representation-specific specification.
- **`S_0.90` and `S_0.95`:** minimum specification budgets reaching 90% and 95% interpretation accuracy.
- **Area under the accuracy-versus-specification curve:** performance over increasing teaching budgets.
- **Specification tokens per correctly interpreted construct:** teaching cost relative to recovered structure.

Targets should be selected before outcomes are observed, and the experiment should report tested budgets and thresholds not reached.

<a id="interpretive-specification-dose"></a>
### Specification-dose design

Give each representation successively more informative definitions, drawn from one canonical semantic specification, at controlled budgets such as 0, 8, 16, 32, 64, 128, and 256 tokens. Increasing the budget must add relevant semantic information rather than padding. Record `A_R(s)` at each dose and estimate the preregistered thresholds and specification-response curve.

Explicit grammar is a legitimate experimental condition, not an inherently undesirable input. [Wang et al. (2023)](https://proceedings.neurips.cc/paper_files/paper/2023/hash/cd40d0d65bfebb894ccc9ea822b47fa8-Abstract-Conference.html) provides evidence that grammar prompting can improve generation on structured DSL tasks in its evaluated settings.

### Outcomes and scoring boundaries

For every condition, record specification tokens; `I0`; `S_0.90` and `S_0.95`; construct-level interpretation accuracy; reference resolution; precedence; hierarchy; operation roles; downstream task accuracy; repair turns; retry rate; and total cost per successful completion. Include syntax cost only using measurements consistent with [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md).

Report **representation-semantic correctness**, **downstream task correctness**, and **surface-format compliance** separately. A model may produce the right output for the wrong representational reason or follow a format while misreading a reference.

## Ablations and remapping

<a id="interpretive-specification-ablation"></a>
### Does explaining ArcGrav help?

Compare ArcGrav without a grammar:

```text
[Files]:
- *.json

Task:
=> Find "inspector" in [Files]
```

With the same prompt preceded by:

```text
ArcGrav syntax:
- bracketed names denote stable contextual references
- => denotes an operation or transformation
- indentation denotes parent-child binding
- numbered items denote execution order
- P0 outranks P1, which outranks P2
```

No material improvement suggests that the supplied grammar is redundant for the tested constructs and model. Improvement limited to unusual constructs indicates construct-specific teaching costs. A large improvement weakens the broad zero-specification claim. Worse performance after specification indicates extra context cost without demonstrated benefit and should be replicated before drawing a mechanistic conclusion. Evaluate this across specification doses, not at a single grammar length.

<a id="interpretive-semantic-cue-ablation"></a>
### Which cues earn their interpretive cost?

Replace one structural convention at a time while holding task information and the intended relationships fixed:

- Bracketed identity versus plain or arbitrary naming.
- `=>` versus natural-language transformation labels or arbitrary operators.
- `P0.`/`P1.` versus explicit priority prose, ordinary numbering, or arbitrary markers.
- `AS` versus assignment-like or natural-language aliasing.
- Indentation versus flat labels, parent identifiers, XML nesting, or YAML nesting.
- Triple quotes versus Markdown fences, YAML block scalars, XML elements, or arbitrary literal delimiters.

[Jeoung et al. (2026)](https://aclanthology.org/2026.findings-eacl.61/) offers precedent for controlled prompt variations at functional, semantic, and syntactic levels. [Wallace et al. (2024)](https://arxiv.org/abs/2404.13208) reinforces the need to test instruction precedence empirically rather than treating a marker as intrinsically authoritative.

<a id="interpretive-prior-conflict-remapping"></a>
<a id="interpretive-semantic-remappability"></a>
### Prior conflict and semantic remappability

Familiar cues can be inexpensive to recognize but harder to redefine. Test locally specified meanings that deliberately conflict with familiar associations:

```text
Definitions:
- P3 is the highest priority
- P0 is the lowest priority
```

```text
Definitions:
- => Means retain the value without executing an operation
```

| Condition | Cue | Intended meaning |
| --- | --- | --- |
| Familiar aligned | `P0` | Highest priority |
| Familiar inverted | `P0` | Lowest priority |
| Arbitrary specified | `70` | Highest priority |
| Arbitrary unspecified | `70` | Unknown locally |

Measure zero-specification accuracy, the specification needed to override the prior, persistence of error after repeated demonstrations, and recovery when returning to the conventional meaning. This isolates the tradeoff between **zero-specification recoverability** and **semantic remappability**.

## Controls for fair comparison

The comparison should preserve the same underlying task information, source evidence, semantic relationships, priority structure, operation sequence, examples, and output requirements. Hold model and model version, system instructions, decoding parameters, and available tools constant within each comparison. Use clean conversations, repeated trials when outputs are variable, and deterministic or blinded evaluation where possible.

**Feature matching.** Give each baseline its reasonable equivalent of contextual references, explicit priorities, and other features needed to express the canonical task graph. Do not compare an ArcGrav reference to a weakened prose baseline forced to repeat content unnecessarily.

**Authoring parity.** Allow independently written strong baselines, format-specific prompt optimization, generation from a shared canonical task graph, and review by practitioners familiar with each format.

**Randomization and analysis.** Sample many arbitrary mappings across items. Mixed-effects or hierarchical analyses may account for model, task, construct, representation family, mapping, and specification budget. Report effect sizes and confidence intervals instead of only aggregate rankings.

**Evaluation separation.** Score interpretation, task execution, and output formatting independently. Otherwise a representation may appear better because one metric conceals weaknesses in another.

## Benchmark program

A complete evaluation spans basic interpretation through deployment-like reuse:

- **Representation-semantic probes:** mechanically gradable tests of identity, hierarchy, precedence, sequence, transformation, aliasing, scope, and literal boundaries.
- **Zero-specification comparisons:** ArcGrav, strong familiar formats, and randomized isomorphic encodings with no local grammar.
- **Specification-dose curves:** measure `A_R(s)`, `S_0.90`, `S_0.95`, and area under the response curve.
- **Randomized isomorphs:** repeat the same semantic graphs under many private mappings.
- **Prior-conflict remapping:** aligned, inverted, arbitrary specified, and arbitrary unspecified conditions.
- **Cue ablations:** isolate individual ArcGrav conventions while matching wording, order, information, and task graph.
- **Operational tasks:** information extraction, conditional reasoning, entity-state tracking, document transformation, repository analysis, constraint-heavy generation, conflicting-priority resolution, planning, tool orchestration, and multi-step agents.
- **Lifecycle amortization:** increase use count `N` and measure acquisition break-even, maintenance, retries, and repair.
- <a id="interpretive-cross-model-portability"></a> **Cross-model generalization:** Compare interpretation accuracy and specification requirements across different model families and tokenizers.

Instruction distance and positional effects belong to [Semantic Locality](./Context_Triad/Semantic_Locality.md). Context transfer, compression, interference, mutation, and historical-state stress tests belong to [Semantic Shadow](./Context_Triad/Semantic_Shadow.md).

## Falsification conditions

**General interpretive-efficiency theory is weakened** if controlled tests repeatedly find essentially identical specification requirements for semantically isomorphic representations or no meaningful differences in acquisition curves.

**Prior alignment is weakened** if randomized arbitrary encodings match familiar, prior-aligned cues at zero specification across models and constructs, or familiar cues do not reduce `S_0.90` or `S_0.95`.

**ArcGrav-specific advantage is weakened** if an explicit ArcGrav grammar substantially improves interpretation of ordinary constructs; strong familiar formats match or exceed ArcGrav without more teaching; the apparent advantage disappears with feature matching; zero-specification interpretation fails to transfer across model families; or interpretation remains high while operational task performance consistently degrades.

Falsification specific to persistent context and historical-state behavior is treated in [Semantic Shadow](./Context_Triad/Semantic_Shadow.md).

## Implications for DSL comparison and design

A parser-backed DSL can be the better tool when deterministic execution, static validation, type safety, schema enforcement, formal compositional semantics, or reproducible machine interpretation is required. ArcGrav addresses the different problem of representing structured intent so that a language model can recover relationships with minimal format-specific teaching. A system can combine this kind of instruction representation with formal tools, schemas, APIs, queries, executable code, or typed state transitions.

The practical design principle is to **avoid introducing a new representational convention when a compact, familiar one already expresses the required relationship**, unless the new convention earns its acquisition and maintenance cost through greater semantic precision or compositional value. Each ArcGrav operator should be evaluated on those terms.

## Scope and Evidence Status

This paper states testable hypotheses and an experimental program, not a completed comparative demonstration. ArcGrav is model-interpreted; its conventions do not supply the guarantees of a parser, grammar validator, type system, or runtime. Interpretation can vary by model family, tokenizer, and construct, and black-box results do not identify which training stage established a useful association. Strong priors can increase remapping cost, while capable or specialized models can acquire arbitrary mappings; YAML, Python-like syntax, or specialized encodings may also be more compact on some tasks. If a DSL's semantics are already embedded in fine-tuning, system infrastructure, a compiler, or persistent tooling, its teaching cost in the current conversation is no longer directly comparable. The proposed measurements concern direct model instruction when representation semantics would otherwise have to be established through the prompt or conversation.

## Conclusion

Interpretive efficiency adds a measurement missing from prompt-length and task-accuracy comparisons: the representation-specific information needed to make structured instructions reliably understandable. The ArcGrav hypothesis is that familiar, compositional cues lower that cost without sacrificing execution. Its evaluation depends on matched semantic tasks, strong familiar baselines, randomized isomorphs, controlled specification doses, and reuse and repair measurements. The decisive question is not which notation looks most compact but **how much teaching each representation needs before its intended meaning can be used reliably**.

## Related Papers

- [ArcGrav Research](./README.md)
- [Model-Native Structural Representation](./Model_Native_Structural_Representation.md)
- [Instructional Representation & the Prose–Program Boundary](./Instructional_Representation.md)
- [ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md)
- [Semantic Locality](./Context_Triad/Semantic_Locality.md)
- [Semantic Shadow](./Context_Triad/Semantic_Shadow.md)
- [Semantic Weight](./Context_Triad/Semantic_Weight.md)

## References

- Honovich, O., et al. (2022). *Instruction Induction: From Few Examples to Natural Language Task Descriptions*. arXiv preprint. https://arxiv.org/abs/2205.10782
- Hua, A., et al. (2025). *Flaw or Artifact? Rethinking Prompt Sensitivity in Evaluating LLMs*. EMNLP. https://aclanthology.org/2025.emnlp-main.1006/
- Jeoung, S., et al. (2026). *PromptPrism: A Linguistically-Inspired Taxonomy for Prompts*. Findings of EACL. https://aclanthology.org/2026.findings-eacl.61/
- Liu, Y., et al. (2025). *Beyond Prompt Content: Enhancing LLM Performance via Content-Format Integrated Prompt Optimization*. arXiv preprint. https://arxiv.org/abs/2502.04295
- Mishra, M., et al. (2023). *Prompting with Pseudo-Code Instructions*. EMNLP. https://aclanthology.org/2023.emnlp-main.939/
- Pan, J., et al. (2023). *What In-Context Learning Learns In-Context: Disentangling Task Recognition and Task Learning*. Findings of ACL. https://aclanthology.org/2023.findings-acl.527/
- Voita, E., & Titov, I. (2020). *Information-Theoretic Probing with Minimum Description Length*. EMNLP. https://aclanthology.org/2020.emnlp-main.14/
- Wallace, E., et al. (2024). *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*. arXiv preprint. https://arxiv.org/abs/2404.13208
- Wang, B., et al. (2023). *Grammar Prompting for Domain-Specific Language Generation with Large Language Models*. NeurIPS. https://proceedings.neurips.cc/paper_files/paper/2023/hash/cd40d0d65bfebb894ccc9ea822b47fa8-Abstract-Conference.html
- Webson, A., & Pavlick, E. (2022). *Do Prompt-Based Models Really Understand the Meaning of Their Prompts?*. NAACL. https://aclanthology.org/2022.naacl-main.167/
- Wei, J., et al. (2023). *Larger language models do in-context learning differently*. arXiv preprint. https://arxiv.org/abs/2303.03846
- Wei, J., et al. (2023). *Symbol tuning improves in-context learning in language models*. EMNLP. https://aclanthology.org/2023.emnlp-main.61/

