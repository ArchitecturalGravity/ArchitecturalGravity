<a id="paper-mnsr"></a>
<a id="mnsr"></a>
# Model-Native Structural Representation

## Abstract

Language-model tasks contain consequential relationships—scope, reference identity, precedence, dependencies, state, and termination—that must survive serialization into model input. This paper develops **Model-Native Structural Representation (MNSR)** as a theory of preserving task structure in forms a receiving model can readily recover through learned associations. It defines **representational impedance** as the mismatch between communicated and model-usable structure, including burdens from serialization and implicit relational reconstruction. MNSR predicts that representations exposing consequential relationships through familiar cues can improve structural recovery and downstream execution, particularly as relational complexity increases. ArcGrav is one text-based implementation hypothesis, not a prerequisite of the theory. The paper proposes testable hypotheses and experiments comparing semantically matched representations on recovery fidelity, execution reliability, and human–model cost.

## Introduction

Language-model prompting is often treated mainly as a problem of wording: state the task clearly and let the model infer the rest. However, before and during execution, the model must recover a usable representation of task structure: which content is data, which statements are instructions, what is in scope, which constraints take precedence, which references denote the same object, what depends on what, what state has changed, what should happen next, and what terminates execution.

These relationships are often non-sequential even though ordinary text-based language-model input is presented as an ordered token sequence. Transformer attention makes long-range relationships within that sequence computationally accessible; MNSR addresses the complementary question of ***how the input representation can make intended task relationships more directly recoverable***.

The central thesis is:

> **When consequential task structure is preserved in model-recoverable form, less representation-specific transformation and reconstruction should be required before and during execution**

Broadly trained language models learn recurring structural associations across natural language, source code, mathematics, markup, configuration formats, tables, and technical documentation. External representations can reuse those associations to expose hierarchy, identity, scope, precedence, dependency, state, and control structure without requiring a new private grammar.

MNSR calls the consequential mismatch between communicated structure and readily usable model structure **representational impedance**. Under serialized interfaces, two important contributors are:

- **Linearization Tax** — introduced when non-sequential structure must cross a sequential channel
- **Structural Reconstruction Tax** — introduced when consequential relationships remain insufficiently explicit and must be inferred

ArcGrav is one implementation hypothesis within this broader framework. ArcGrav remains a text-based representation, but aims to preserve more of the task's relational topology within a sequential input channel. MNSR is therefore a theory of representational alignment across the human–model communication boundary, not a theory of any particular prompt syntax.

The governing research question is:

> **What external representation and communication interface minimizes consequential transformation between intended task structures and model-usable task structures, subject to human authorability, interpretability, stability, model compatibility, and communication cost?**

## Role Within the Research Program

MNSR supplies the general structural-representation theory for this research program. It studies how task-relevant relationships survive communication and how reliably a model can recover them. [Instructional Representation](./Instructional_Representation.md) describes one category of model-facing representations; [ArcGrav Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md) and [Representational Capacity Reclamation](./Representational_Capacity_Reclamation.md) examine distinct proposed consequences.

---

<a id="mnsr-representation-problem"></a>
## The Representation Problem

A task is not the same thing as its prompt.

A task may contain:

- Objects
- Roles
- Scopes
- Constraints
- References
- Priorities
- Dependencies
- States
- Operations
- Evidence requirements
- Termination conditions

The ordinary prompt channel presents these through an ordered sequence of tokens; the task itself need not be sequential.

Consider:

```text
Review Alice's proposal using the revised budget. If the revised budget conflicts
with the original assumptions, the revised budget wins. Do not apply those changes
to the projections appendix.
```

The literal text is sequential, but its operative structure is closer to:

```text
[Alice Proposal] ── reviewed-under ──> [Revised Budget]
        │
        └── contains ──> [Projections Appendix]
                              │
                              └── excluded-from-change

[Revised Budget] ── overrides ──> [Original Assumptions]
```

The model must recover the consequential relationships before it can reliably execute the instruction -- ***this is the representation problem before the task problem***.

---

<a id="mnsr-relational-topology"></a>
## Task Structure as Relational Topology

For analysis, the consequential structure of a task can be treated as a typed graph:

```math
G=(V,E,\tau_V,\tau_E)
```

where \(V\) contains task-relevant entities, \(E\) contains consequential relationships, and the type functions identify their roles.

Nodes may represent:

- Instructions
- Sources
- Objects
- Constraints
- States
- Operations
- Evidence
- Outputs

Edges may represent:

- Scopes-over
- Refers-to
- Contains
- Overrides
- Depends-on
- Precedes
- Transforms
- Validates
- Excludes
- Terminates-when

For example:

```text
[Policy P]
    │
    ├── scopes-over ──> [Source A]
    └── scopes-over ──> [Source B]

[Policy Q]
    │
    └── overrides ──> [Policy P]

[Validation]
    │
    └── follows ──> [Transformation]
```

The task need not be externally represented as a graph. The useful criterion is whether consequential topology survives the communication path.

<a id="mnsr-topology-preservation"></a>
A representation has high **topology preservation** when the identities and relations required for execution remain readily recoverable after serialization.

Treating relations as first-class representational objects has a close antecedent in relational-reasoning research: [Holyoak and Monti (2021)](https://doi.org/10.1162/jocn_a_01619) review work distinguishing representations of individual relations from the integration of multiple relations for higher-order inference. MNSR adopts the functional distinction without assuming shared mechanisms.

Related empirical work found that a computational model representing semantic relations as distributed patterns over abstract relations predicted neural similarity during human analogical reasoning ([Chiang et al., 2021](https://doi.org/10.1162/jocn_a_01620)). This supports the plausibility of distributed relational representation in humans without establishing analogous mechanisms in language models.

---

<a id="mnsr-representation-vs-serialization"></a>
## Representation Is Not Serialization

A central distinction follows:

> **The structure being represented and the channel used to serialize it are different objects**

A graph can be serialized as text. A tree can be serialized as text. Source code is stored as an ordered character or token sequence while representing abstract syntax trees, scopes, dependencies, object graphs, control-flow graphs, and call graphs.

The same distinction applies to prompting.

Let:

- Intended task structure be \(G\)
- Chosen external representation be \(R\)
- Serialized channel input be \(S\)
- Model activation state be \(Z\)
- Model-usable recovered task structure be \(\hat G\)
- Resulting action or output be \(A\)

The communication path can be sketched as:

```text
Intended Task
     G
     │
     │ representation design
     ▼
External Representation
     R
     │
     │ channel serialization
     ▼
Serialized Input
     S
     │
──── model boundary ────
     │
     ▼
Internal Model State
     Z
     │
     │ task recovery
     ▼
Usable Task Structure
     Ĝ
     │
     │ reasoning / execution
     ▼
Action or Output
     A
```

MNSR primarily concerns the path from \(G\) through \(R\), \(S\), and \(Z\) to \(\hat G\). It does not require that \(\hat G\) exist as one literal internal graph. The notation identifies functional structure that must be preserved well enough to support correct behavior.

<a id="mnsr-dimensionality"></a>
<a id="mnsr-channel-dimensionality"></a>
<a id="mnsr-relational-dimensionality"></a>
<a id="mnsr-latent-dimensionality"></a>
### Three meanings of dimensionality

Discussion of prompting can confuse three unrelated notions of dimensionality.

- ***Channel dimensionality*** describes how communication is physically presented; ordinary text input is presented as an ordered sequence.

- ***Relational dimensionality*** describes the topology carried by the representation; a text prompt can encode hierarchy, cross-reference, precedence, dependency, membership, state transitions, and arbitrary graph-like relations.

- ***Latent dimensionality*** describes the high-dimensional numerical representations used internally by the model.

These should not be conflated. A high-dimensional input object is not inherently meaningful:

```text
[0.17, -0.82, 0.04, ...]
```

This may contain thousands of dimensions but communicate little unless sender and receiver share a mapping for those values.

Conversely:

```text
A overrides B
```

This linear expression still communicates a clear relation because its semantics draw on learned conventions.

> **Dimensionality is not semantics. The relevant question is how reliably and efficiently the receiving model can recover the intended relationships**

---

## The MNSR Thesis

MNSR studies how consequential task structure can be preserved across the communication boundary in forms the receiving model can readily recover through learned associations.

> **Representations that expose task-relevant relationships through cues already supported by the model's learned associations can reduce unnecessary transformation and reconstruction before and during execution**

The thesis rests on four claims.

### Relationships are part of task information

The meaning of a statement depends partly on its relations. For example:

```text
Do not modify generated files.
```

changes operationally depending on whether it is global, local, temporary, overridden, or conditional. The words alone do not fully specify the executable instruction.

### Representations differ in topology preservation

Equivalent task semantics can be expressed as prose, Markdown, YAML, JSON, XML, code-like notation, tables, diagrams, schemas, or specialized instructional representations. These forms differ in how directly they expose consequential relations.

<a id="mnsr-learned-structural-priors"></a>
### Models possess learned structural priors

Broad training repeatedly associates familiar cues with recurring structural functions:

```text
headings      -> scope
indentation   -> hierarchy
lists         -> membership / order
labels        -> role / identity
arrows        -> direction / transformation
numbers       -> sequence / priority
quotes        -> attributed content
brackets      -> grouping / reference / index
```

These are learned associations, not universal parser rules.

<a id="mnsr-model-native-fit"></a>
### Model-native fit is relational

"Model-native" does not name a syntax. It describes the fit between an external representation and the structures the model can readily recover from it.

A representation is model-native to the extent that its relevant semantics can be recovered through learned associations without substantial representation-specific instruction.

The general proposition that performance depends on a match between representation and processing requirements has important antecedents in [Vessey (1991)](https://doi.org/10.1111/j.1540-5915.1991.tb00344.x) and in [Chandra & Krovi (1999)](https://doi.org/10.1016/S0167-9236(99)00014-7), which explicitly studies congruence between external information organization and  internal representation. **Model-native fit** and the related **prior-alignment** construct transfer that representational-fit question to learned model priors and model-recoverable structure.

---

## Why Model-Native Structure Matters

Explicit structure alone is not sufficient.

Consider:

```text
@Q3 !x R7 >% M2
```

This could encode a perfectly precise task, but if the model must *first* learn every symbol, precedence rule, binding rule, and operation, the representation creates acquisition burden *before* execution.

<a id="mnsr-prior-alignment"></a>
MNSR therefore requires **prior alignment**:

> **A model-native representation uses relational cues whose relevant functions are already recoverable from the model's prior learning**

Under contemporary text interfaces, useful candidates include:

- Descriptive labels
- Headings
- Indentation
- Lists
- Tables
- Ordinary imperative language
- References
- Priority markers
- Arrows
- Grouping
- Repeated schemas

<a id="mnsr-semantic-infrastructure"></a>
Model-internalized associations can act as **semantic infrastructure** -- the representation reuses them rather than defining a complete grammar from scratch.

The acquisition cost of novel representations is developed separately in [ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md). Instruction placement within context is developed in [Semantic Locality](./Context_Triad/Semantic_Locality.md), while the effect of newer context on earlier conversation-specific definitions is developed in [Semantic Shadow](./Context_Triad/Semantic_Shadow.md). Relative instruction magnitude is developed in [Semantic Weight](./Context_Triad/Semantic_Weight.md).

### Model-native is not latent proximity

"Model-native" should not be interpreted as geometric proximity to a particular hidden vector. MNSR does not require a symbol to map to one hidden coordinate, nor does it require different models to share latent coordinates.

Model nativeness is functional:

> **Model-native means readily recoverable through learned model associations, not physically close to a known latent coordinate**

Two models can support similar structural conventions while implementing them through different internal geometry.

---

<a id="mnsr-representation-recovery-before-reasoning"></a>
## Representation Recovery Before Reasoning

MNSR distinguishes three functional stages:

> **Recover Task → Reason Over Task  → Execute Task**

A structured representation does not enlarge the model, and it does not create new parameters, hidden dimensions, attention heads, or reasoning modules, instead it changes the representation upon which reasoning operates.

If the recovered task representation contains the correct identities, scopes, priorities, dependencies, and state, *downstream reasoning begins from a better-defined problem*.

<a id="mnsr-representation-conditioned-task-performance"></a>
MNSR therefore predicts **representation-conditioned task performance**:

> **Execution quality depends partly on the quality of the task representation produced before and during reasoning**

---

<a id="mnsr-representational-impedance"></a>
## Representational Impedance

**In plain language.** Representational impedance is the extra difficulty caused by the form in which a task is communicated, rather than by the underlying task alone.

The central MNSR construct is **representational impedance**:

> **The consequential mismatch between the structure in which a task is represented and the structure readily usable by the receiving model**

Representational impedance extends the external/internal representation mismatch studied by [Chandra & Krovi (1999)](https://doi.org/10.1016/S0167-9236(99)00014-7) to task recovery and execution at the human–model communication boundary.

Representational impedance depends on the task, its external representation, the receiving model, and the communication context. It can arise from six contributors:

<a id="mnsr-encoding-cost"></a>
<a id="mnsr-serialization-cost"></a>
<a id="mnsr-acquisition-cost"></a>
<a id="mnsr-reconstruction-cost"></a>
<a id="mnsr-coordination-cost"></a>
<a id="mnsr-representational-loss"></a>

- Encoding cost captures the cost of expressing the intended task in the representation
- Serialization cost captures burden imposed by the communication channel
- Acquisition cost captures representation-specific semantics that must be learned in context
- Reconstruction cost captures implicit relations that must be inferred
- Coordination cost captures burden of maintaining recovered structure during execution
- Representational loss \(L_R\) captures consequential differences between intended and recovered structure

These are analytical categories; they need not be independent, additive, or measured in common units.

<a id="mnsr-transformation-distance"></a>
### Transformation distance

**Transformation distance** is the functional transformation required before a representation yields a usable model-side representation of a task.

Transformation can include role inference, scope inference, reference resolution, priority resolution, state reconstruction, control reconstruction, grammar acquisition, and context recovery. The distance describes functional transformation rather than latent-space geometry.

MNSR predicts that structure aligned with learned model associations will reduce this transformation burden relative to a diffuse representation of the same task, provided the added structure does not introduce greater offsetting cost.

<a id="mnsr-linearization-tax"></a>
### Linearization tax

The **linearization tax** is the burden attributable to carrying non-sequential task structure through a sequential channel.

It is not token count. A linear serialization can preserve a graph well:

```text
A -> B
A -> C
C -> D
D overrides B
```

The problem is not serialization alone, but the loss or obscuration of consequential topology during serialization. Distinguishing the intended task, its external representation, and its serialized form makes this possible loss visible.

<a id="mnsr-structural-reconstruction-tax"></a>
### Structural reconstruction tax

The **structural reconstruction tax (SRT)** is the avoidable interpretive and coordination *reconstruction burden* incurred when task-relevant relationships remain insufficiently explicit.

Common reconstruction sources include:

- Scope
- Reference
- Content role
- Precedence
- Dependency
- State
- Control-flow
- Verification
- Termination

Reconstruction burden should depend on relational complexity and on how explicitly those relations are represented, not on raw length alone. A long flat passage may be unambiguous yet still require substantial structural reconstruction, while a short instruction with nested scope, mutable state, cross-references, and conflicting constraints may impose even greater reconstruction burden.

For example, consider a long procedural instruction:

```text
Review each submitted report in order. For every report, compare the reported figures against the approved budget, note
any discrepancy greater than five percent, and record the discrepancy before moving to the next report. Reports that contain
unresolved discrepancies should be held for secondary review. Reports without discrepancies may proceed directly to approval.
Once all reports have been processed, return to those held for secondary review, apply any subsequently issued budget corrections,
and approve only those whose discrepancies are resolved. Do not alter the original submitted figures.
```

The passage may be clear, but execution still requires the model to recover and maintain several relationships:

- Report identity
- Processing order
- Conditional branching
- State transitions between pending, held, and approved reports
- Scope of later budget corrections
- Prohibition against modifying source values

Much of that structure is expressed *narratively* rather than explicitly, requiring the model to reconstruct it into a usable task representation.

By contrast, consider a shorter instruction:

```text
Apply the current policy to all pending reports except Report C. If Policy B conflicts with Policy A, Policy B overrides it.
Reports already reviewed under Policy A must be rechecked only if Policy B changed the applicable requirement.
```

This instruction is much shorter, but its reconstruction burden is higher because several consequential relations interact densely: exclusion scope, policy precedence, persistent report state, conditional reprocessing, and reference identity across prior and current policy application.

Thus, length can contribute to reconstruction burden by distributing relationships across more context, but length alone is not the governing variable. Stronger predictors are the number, interaction, distance, and explicitness of the task-relevant relationships the model must recover and maintain.

SRT is treated as a corollary of prior work showing that external representations can change the **cost structure of inference** and reduce internal computation ([Kirsh, 2010](https://doi.org/10.1007/s00146-010-0272-8)), together with locality theories in which greater dependency distance carries integration and memory costs ([Gibson, 1998](https://doi.org/10.1016/S0010-0277(98)00034-1)). SRT narrows those ideas to avoidable reconstruction of task-relevant relationships at the language-model representation boundary.

<a id="mnsr-round-trip-fidelity"></a>
### Round-trip fidelity

Let \(\hat G\) be the task structure functionally recovered by the model. Define representational round-trip loss as:

```math
L_R=D(G,\hat G)
```

Here, \(D\) measures consequential structural differences such as wrong identity, lost scope, reversed precedence, missing dependency, stale state, incorrect sequence, premature termination, or misbound evidence. In experiments, these differences can be scored against a canonical task graph and reported by relation type.

The objective is not literal duplication of the author's mental state. It is preservation of the structure necessary for correct execution.

For tasks whose success depends on those relations, MNSR predicts that more faithful structural recovery will be associated with more reliable downstream execution.

---

<a id="mnsr-representational-offloading"></a>
## Structural Offloading and ArcGrav

MNSR can be understood as **representational offloading**: consequential relationships are made visible externally rather than left entirely to implicit reconstruction.

This mechanism has direct antecedents in research on **cognitive offloading**, where external action changes task information-processing requirements to reduce internal cognitive demand ([Risko & Gilbert, 2016](https://doi.org/10.1016/j.tics.2016.07.002)), and in work on external representations showing that they can reduce internal computation and change the inferential cost landscape ([Kirsh, 2010](https://doi.org/10.1007/s00146-010-0272-8)). MNSR applies the offloading idea to model-side structural reconstruction.

Examples include:

**Identity**

```text
[Policy]:
- Preserve exact values
- Report source paths

Task:
- Apply [Policy] to [SourceA]
- Apply [Policy] to [SourceB]
```

**Hierarchy**

```text
Project
  Source
    Primary
    Secondary
  Output
    Summary
```

**Precedence**

```text
P0: Safety Requirement
P1: User Preference
P2: Default Behavior
```

**State**

```text
[Pending]: A, B, C
[Completed]: D
[Failed]: none
```

**Control**

```text
1. Process [Pending]
2. Verify result
3. Retry once if verification fails
4. Stop when [Pending] is empty
```

**Verification**

```text
[Transform]:
=> update target

[Verify]:
=> compare output to requirement
=> confirm no excluded files changed
```

ArcGrav attempts to operationalize these principles through the current text-token interface, with relevant design properties:

- Structural explicitness for scope, hierarchy, identity, priority, operation, state, sequence, and verification
- Prior alignment through conventions common across natural language and technical corpora
- Compositional reuse through stable contextual identities
- Semantic locality through placing consequential control structure near the operations and expressions that depend on it

For example:

```text
[Source]: /repo/docs/

[Policy]:
P0. Preserve source meaning
P1. Remove redundant prose

[Exclude]:
- /generated/
- /archive/

Task:
1. Inspect [Source]
2. Apply [Policy]
3. Do not modify [Exclude]
4. Verify changed files
5. Stop when verification passes
```

The representation remains a token sequence, and its advantage comes from preserving more relational topology through that sequence.

> **ArcGrav increases relational explicitness, not physical channel dimensionality**

ArcGrav is therefore a channel-constrained implementation of MNSR, not its endpoint. A graph-native or learned interface could outperform ArcGrav while supporting the broader MNSR thesis.

The distinction between instruction structure and program structure is developed in [Instructional Representation & the Prose–Program Boundary](./Instructional_Representation.md).

---

## Mechanistic Plausibility

Several established properties of language models motivate MNSR's proposed mechanism. The comparative predictions remain subjects for empirical testing.

### Learned structural priors

Language models train over natural and technical corpora containing recurring relationships between textual forms and structural functions.

[Gonen et al. (2023)](https://aclanthology.org/2023.findings-emnlp.679/) found, across its evaluated tasks, associations between lower-perplexity prompt formulations and stronger performance. Familiar structures are therefore plausible carriers of lower-acquisition relational cues.

<a id="mnsr-task-recognition"></a>
### Task recognition

[Xie et al. (2022)](https://arxiv.org/abs/2111.02080) models in-context learning as inference over latent concepts. [Pan et al. (2023)](https://aclanthology.org/2023.findings-acl.527/) distinguishes task recognition from task learning. [Min et al. (2022)](https://aclanthology.org/2022.emnlp-main.759/) shows that example structure can carry useful operational information beyond literal label semantics in the studied settings. [von Oswald et al. (2022)](https://arxiv.org/abs/2212.07677) demonstrates learning-like in-context algorithms in controlled settings.

For MNSR, the relevant implication is that a representation may provide enough evidence for the model to recognize an already supported structural pattern.

<a id="mnsr-associative-retrieval"></a>
### Associative retrieval

[Ramsauer et al. (2020)](https://openreview.net/forum?id=tL89RnzIiCd) establishes a mathematical relationship between transformer attention and modern continuous Hopfield networks. Related work on associative memory and in-context denoising further supports retrieval-oriented interpretations in relevant settings.

MNSR requires only the narrower claim that familiar external structure can activate learned representational associations.

<a id="mnsr-internal-semantic-task-structure"></a>
### Internal semantic and task structure

[Park et al. (2024)](https://proceedings.mlr.press/v235/park24c.html) and [Jiang et al. (2024)](https://proceedings.mlr.press/v235/jiang24d.html) study structured semantic representations. [Todd et al. (2023)](https://arxiv.org/abs/2310.15213), [Hendel et al. (2023)](https://arxiv.org/abs/2310.15916), and [Liu et al. (2023)](https://arxiv.org/abs/2311.06668) provide evidence for compact internal representations associated with tasks or operations. [Elhage et al. (2022)](https://transformer-circuits.pub/2022/toy_model/index.html) demonstrates why useful internal features need not correspond to isolated coordinates.

<a id="mnsr-information-anchors-binding"></a>
### Information anchors and binding

[Wang et al. (2023)](https://aclanthology.org/2023.emnlp-main.609/) provides evidence that labeled positions can aggregate task-relevant information. [Olsson et al. (2022)](https://arxiv.org/abs/2209.11895) identifies attention mechanisms supporting repeated-pattern relationships such as:

```text
[A][B] ... [A] -> [B]
```

These findings provide a basis for investigating repeated labels, local schemas, named references, and explicit contextual binding.

<a id="mnsr-prompt-sensitivity"></a>
### Prompt sensitivity

Prompt ordering and lexical variation can materially affect model behavior. [Lu et al. (2022)](https://arxiv.org/abs/2104.08786), [Zhuo et al. (2024)](https://aclanthology.org/2024.findings-emnlp.108/), [Chatterjee et al. (2024)](https://aclanthology.org/2024.findings-emnlp.852/), and [Xie et al. (2026)](https://aclanthology.org/2026.findings-acl.2084/) provide behavioral motivation for treating representation choice as consequential.

[Liu et al. (2025)](https://arxiv.org/abs/2502.04295) provides additional evidence that prompt formatting can materially affect model performance and that format can be treated as an optimization variable.

MNSR makes the narrower structural prediction that part of this sensitivity can be reduced when consequential relationships are more recoverable.

<a id="mnsr-reduced-interpretive-branching"></a>
### Interpretive branching

An ambiguous instruction can support multiple relational interpretations while explicit role, identity, scope, and target boundaries can narrow that space.

MNSR calls this reduction in behaviorally plausible interpretations **reduced interpretive branching**. The model need not literally enumerate task graphs; the concept describes observable ambiguity in the mapping from representation to behavior.

---

<a id="mnsr-representation-frontier"></a>
## Conditional Fit and the Representation Frontier

Model-native fit depends on the representation, receiving model, task, and communication context. No notation is universally model-native.

A representation can have high model-native fit for one task and low fit for another. Consider a simple instruction:

```text
Translate "hello" into Spanish.
```

It needs little external structure; a large schema is likely worse. By contrast, tasks involving many files, ranked constraints, mutable state, dependency traversal, verification, retries, and explicit termination contain enough relational complexity for additional structure to become useful.

<a id="mnsr-optimal-structural-density"></a>
MNSR therefore predicts an **optimal structural density**, not maximal structure:

> **Externalize relationships whose implicit reconstruction is costly. Leave simple relations simple**

Representations trade among:

- Structural explicitness
- Prior alignment
- Human authorability
- Inspectability
- Serialization cost
- Compositional reuse
- Task fit
- Model fit

At the system level, representation choice must balance human authoring, comprehension, repair, and maintenance effort; model-side representational impedance; and consequential structural loss. These outcomes can be compared empirically without assuming that they form a single additive cost function.

The best human–model interface must serve both sides of the boundary.

<a id="mnsr-interface-continuum"></a>
### Interface continuum

MNSR extends beyond prompting:

```text
Natural Prose
     │
     ▼
Structured Documents
     │
     ▼
Instructional Representation
     │
     ▼
Schema / Graph Representation
     │
     ▼
Learned Model Interface
```

These layers are not a ranking:

- Natural prose offers high human familiarity with variable structural explicitness
- Structured documents expose more hierarchy and grouping while remaining ordinary language
- Instructional representations such as ArcGrav make roles, references, scope, priority, state, control, and verification explicit
- Schema- or graph-native interfaces could transmit relations as first-class objects
- Learned interfaces could map external structured state into model-compatible continuous representations

Every layer still faces the MNSR question: does the representation preserve the intended task, does the mapping preserve consequential relationships, can humans author or inspect it when necessary, and can the model recover it reliably?

---

## Where MNSR Should Matter and Where It Can Fail

MNSR predicts larger effects as relational complexity increases.

High-value conditions include:

- Long or multi-source context
- Nested scope
- Repeated references
- Ranked constraints
- Mutable state
- Multi-step tool use
- Dependency ordering
- Branching
- Recursive traversal
- Retries
- Verification requirements
- Separate modification and validation
- Termination conditions
- Long-running agentic workflows

For simple tasks, additional structure can be pure overhead.

MNSR representations can also fail through:

- False explicitness when notation appears precise to a human but remains ambiguous to the model
- Prior conflict when a familiar cue carries learned associations inconsistent with its local use
- Over-structuring when added syntax creates more context than useful structure
- Semantic fragmentation when information that should be jointly interpreted is separated excessively
- Representation mismatch when prose, code, a table, or another representation better fits the task
- Acquisition burden when a private grammar requires too much local explanation
- Topology loss when consequential relations are omitted or distorted
- Model variation when different models recover the same representation differently

MNSR is therefore model-native and potentially portable, not model-invariant.

[Huh et al. (2024)](https://proceedings.mlr.press/v235/huh24a.html) provides related evidence for partially aligned representational geometry across sufficiently capable models. Such alignment does not imply identical latent coordinates or identical prompt semantics.

---

## Research Hypotheses

The hypothesis set is intentionally compact. Each hypothesis targets a distinct part of the theory and maps to a separable experimental question

<a id="mnsr-structural-recovery-hypothesis"></a>
### H1 — Structural Recovery Hypothesis

> At matched task semantics, representations that expose consequential relationships more explicitly will reduce relational reconstruction errors in identity, scope, precedence, dependency, state, control, and verification

<a id="mnsr-complexity-scaling-hypothesis"></a>
### H2 — Complexity Scaling Hypothesis

> The advantage of topology-preserving representation will increase with relational complexity more strongly than with raw prompt length

<a id="mnsr-prior-alignment-hypothesis"></a>
### H3 — Prior-Alignment Hypothesis

> Among structurally equivalent representations, cues aligned with familiar learned conventions will require less representation-specific instruction than randomized isomorphic encodings

<a id="mnsr-round-trip-performance-hypothesis"></a>
### H4 — Round-Trip Performance Hypothesis

> More faithful recovery of consequential task topology will predict more reliable downstream execution and verification

<a id="mnsr-stateful-coordination-hypothesis"></a>
### H5 — Stateful Coordination Hypothesis

> In longitudinal and tool-using tasks, explicit state, control, and termination structure will reduce stale-state errors, repeated work, premature termination, and corrective human interaction

<a id="mnsr-representation-frontier-hypothesis"></a>
### H6 — Representation-Frontier Hypothesis

> No representation will dominate across all tasks; optimal representations will lie on a frontier balancing topology preservation, prior alignment, human cost, communication cost, task fit, and model fit.

<a id="mnsr-channel-substitution-hypothesis"></a>
### H7 — Channel-Substitution Hypothesis

> When consequential relations can be supplied through a model-supported structured channel rather than reconstructed from diffuse prose, relational errors will decrease; when two apparent interfaces reduce to equivalent model-visible input, interface appearance alone will provide no intrinsic advantage

<a id="mnsr-learned-interface-hypothesis"></a>
### H8 — Learned-Interface Hypothesis

> A learned mapping from external structured state to model-compatible representation can outperform hand-authored serialization when it preserves consequential task relations with lower total representational impedance

---

## Experimental Program

### Semantically isomorphic representation benchmark

Construct canonical tasks and express them as:

- Optimized prose
- Markdown
- ArcGrav
- YAML
- JSON
- XML
- Python-like instructional syntax
- Arbitrary expressive DSL
- Randomized isomorphic DSL

Hold task semantics constant and measure:

- Task success
- Reference accuracy
- Scope adherence
- Precedence accuracy
- State consistency
- Constraint violations
- Verification success
- Premature termination
- Corrective turns
- Human interventions

### Relational complexity ladder

Vary:

- Node count
- Edge count
- Edge type count
- Hierarchy depth
- Branching factor
- Reference distance
- Constraint interaction
- State variables
- Dependency depth
- Termination conditions

Hold domain difficulty approximately constant and test whether representation effects scale with graph complexity.

### Topology-preservation benchmark

Start from a canonical typed task graph and encode it into multiple representations. Ask the model to reconstruct the task structure, then compare the result with the canonical graph using predefined matching rules. Report missing, spurious, reversed, and mis-scoped relations by type, and test whether structural recovery predicts downstream execution reliability.

### Construct ablation and prior-alignment study

Remove individual structural cues and compare familiar notation against isomorphic randomized notation.

Candidate ablations include:

- Labels
- Section boundaries
- Indentation
- References
- Priority markers
- State markers
- Ordered procedures
- Verification phases
- Termination conditions

Measure both relation-specific degradation and the amount of specification required before randomized encodings converge.

### Stateful agent benchmark

Use long-running tool tasks requiring discovery, planning, state mutation, dependency tracking, retry, verification, and termination. Compare narrative instructions against explicit state-and-control representations.

Primary outcomes should include:

- Omissions
- Repeated work
- Stale-state errors
- Premature termination
- Tool retries
- Corrective turns
- Successful autonomous completion

### Open-model mechanistic study

For models with activation access, compare semantically matched representations using:

- Representational similarity
- Task-role probes
- Reference-identity probes
- Attention analysis
- Causal activation patching
- Task-vector methods
- Function-vector methods

The target is not a dedicated ArcGrav circuit, it's whether lower-impedance representations produce more stable or decodable task relations.

### Channel and serialization-equivalence study

Where supported, compare prose serialization, structured text, schema-native input, graph-native input, and learned structured interfaces while matching task semantics.

Include a control in which superficially different user interfaces produce the same model-visible input. If downstream behavior remains equivalent under that control, the result supports the distinction between interface appearance and the actual representational channel.

### Human–model cost study

Measure human-side and model-side costs jointly.

Human outcomes should include:

- Authoring time
- Editing time
- Error rate
- Comprehension
- Repair cost
- Review accuracy

Model outcomes should include structural recovery, execution reliability, correction burden, and communication cost. The optimal representation is the one that minimizes total system burden, not model burden alone.

---

## Relationship to the Other Research Layers

MNSR owns the general representational theory and is concerned with the representation entering the task. Surrounding research isolates narrower questions such as examining what that representation costs to establish and what downstream leverage it produces.

- **[Instructional Representation & the Prose–Program Boundary](./Instructional_Representation.md)** asks which relationships belong in instruction structure rather than program structure
- **[ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md)** studies representation acquisition, specification dose, maintenance, and repair cost
- **[Semantic Locality](./Context_Triad/Semantic_Locality.md)** studies instruction placement within context relative to surrounding information and points of use
- **[Semantic Shadow](./Context_Triad/Semantic_Shadow.md)** studies how newer context changes the influence and active status of earlier context
- **[Semantic Weight](./Context_Triad/Semantic_Weight.md)** studies influence associated with relative semantic mass among instruction structures
- **[ArcGrav Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md)** studies serialization cost and compositional reuse once semantics are established
- **[ArcGrav Operational Leverage](./Operational_Leverage/)** studies successful autonomous work relative to human specification effort
- **[ArcGrav Reasoning–Interaction Substitution](./ArcGrav_Reasoning_Interaction_Substitution.md)** studies when additional model reasoning reduces total completion cost by replacing human steering, reconstruction, and repeated interaction

---

## Scope, Evidence Status, and Falsification Criteria

**Evidence status.** MNSR is a theoretical framework with testable predictions. Its comparative and mechanistic claims are targets for the controlled studies in [Experimental Program](#experimental-program).

The hypotheses do not assume a specific internal circuit, reductions in transformer computation, or shared latent coordinates. They also do not presume ArcGrav superiority, token minimality, or gains from extra structure on every task.

Stronger forms of MNSR should be weakened if controlled experiments show that:

- Increased structural explicitness does not reduce relational errors as relational complexity rises
- Optimized prose matches explicit representations on high-complexity tasks without greater correction or coordination burden
- Familiar structural cues show no acquisition advantage over randomized isomorphic mappings
- Task-graph reconstruction fidelity does not predict downstream execution reliability
- Explicit state and control representations do not improve longitudinal task performance
- Topology-preserving representations show no advantage after semantic content and communication cost are controlled
- Apparent interface advantages persist even when model-visible representations are equivalent for reasons unrelated to the representation itself
- Human costs consistently outweigh model-side representational benefits in the target environment

---

## Practical Design Consequences

MNSR changes the central design question from:

```text
How should I word this prompt?
```

to:

```text
What relationships must cross the communication boundary?
```

Practical consequences follow:

- Make scope visible when scope errors matter
- Name reusable contexts when identity must persist
- Expose hierarchy when containment matters
- State priority when rules can conflict
- Externalize mutable state in longitudinal work
- Distinguish source material from operations
- Separate transformation from verification
- Represent dependencies when order is not merely rhetorical
- State stopping conditions when termination matters
- Use familiar cues when they already carry the intended relation
- Avoid notation that adds syntax without reducing impedance

<a id="mnsr-minimal-sufficient-structure"></a>
The target is:

> **Minimal sufficient structure**

---

## Conclusion

Language-model communication is usually serialized, but interpretation is not.

A prompt may be a sequence of tokens while representing a network of objects, scopes, identities, dependencies, constraints, states, transformations, evidence relationships, and control conditions. The central problem is therefore not the dimensionality of the prompt itself, but the fidelity with which relational structure survives the communication path.

As shown in **Representation Is Not Serialization**, the communication pathway runs from intended task structure through external representation and serialized input to model-side recovery and eventual action.

MNSR concerns preserving consequential structure across this path in forms the receiving model can readily recover through learned associations. **Representational impedance** describes the consequential mismatch that remains when that preservation is incomplete, costly, or unstable.

Under text-token interfaces, ArcGrav is one attempt to preserve more of that structure while reducing impedance through the existing channel. The broader research objective is independent of ArcGrav:

> **Identify representations that preserve consequential task structure while reducing total representational impedance across the human–model system**

Future interfaces may expose typed objects, persistent identities, dependency graphs, state stores, schemas, tool contracts, multimodal spatial relations, or learned continuous representations more directly. Direct machine representation is not automatically optimal because human communication remains part of the system.

This reframes prompt design as a special case of a larger problem:

> **What should the communication interface between humans and learned models be?**

## Related Papers

- [Instructional Representation](./Instructional_Representation.md)
- [Representational Capacity Reclamation](./Representational_Capacity_Reclamation.md)
- [ArcGrav Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md)
- [Context Triad](./Context_Triad/)

## References

- Chandra, A., & Krovi, R. (1999). *Representational congruence and information retrieval: Towards an extended model of cognitive fit*. Decision Support Systems. https://doi.org/10.1016/S0167-9236(99)00014-7
- Chatterjee, A., et al. (2024). *POSIX: A Prompt Sensitivity Index For Large Language Models*. Findings of EMNLP. https://aclanthology.org/2024.findings-emnlp.852/
- Chiang, J. N., et al. (2021). *Distributed Code for Semantic Relations Predicts Neural Similarity during Analogical Reasoning*. Journal of Cognitive Neuroscience. https://doi.org/10.1162/jocn_a_01620
- Elhage, N., et al. (2022). *Toy Models of Superposition*. Transformer Circuits. https://transformer-circuits.pub/2022/toy_model/index.html
- Gibson, E. (1998). *Linguistic complexity: locality of syntactic dependencies*. Cognition. https://doi.org/10.1016/S0010-0277(98)00034-1
- Gonen, H., et al. (2023). *Demystifying Prompts in Language Models via Perplexity Estimation*. Findings of EMNLP. https://aclanthology.org/2023.findings-emnlp.679/
- Hendel, R., et al. (2023). *In-Context Learning Creates Task Vectors*. Findings of EMNLP / arXiv. https://arxiv.org/abs/2310.15916
- Holyoak, K. J., & Monti, M. M. (2021). *Relational Integration in the Human Brain: A Review and Synthesis*. Journal of Cognitive Neuroscience. https://doi.org/10.1162/jocn_a_01619
- Huh, M., et al. (2024). *Position: The Platonic Representation Hypothesis*. ICML / PMLR. https://proceedings.mlr.press/v235/huh24a.html
- Jiang, Y., et al. (2024). *On the Origins of Linear Representations in Large Language Models*. ICML / PMLR. https://proceedings.mlr.press/v235/jiang24d.html
- Kirsh, D. (2010). *Thinking with external representations*. AI & Society. https://doi.org/10.1007/s00146-010-0272-8
- Liu, S., et al. (2023). *In-context Vectors: Making In Context Learning More Effective and Controllable Through Latent Space Steering*. arXiv preprint. https://arxiv.org/abs/2311.06668
- Liu, Y., et al. (2025). *Beyond Prompt Content: Enhancing LLM Performance via Content-Format Integrated Prompt Optimization*. arXiv preprint. https://arxiv.org/abs/2502.04295
- Lu, Y., et al. (2022). *Fantastically Ordered Prompts and Where to Find Them: Overcoming Few-Shot Prompt Order Sensitivity*. ACL / arXiv. https://arxiv.org/abs/2104.08786
- Min, S., et al. (2022). *Rethinking the Role of Demonstrations: What Makes In-Context Learning Work?*. EMNLP. https://aclanthology.org/2022.emnlp-main.759/
- Olsson, C., et al. (2022). *In-context Learning and Induction Heads*. arXiv preprint. https://arxiv.org/abs/2209.11895
- Pan, J., et al. (2023). *What In-Context Learning Learns In-Context: Disentangling Task Recognition and Task Learning*. Findings of ACL. https://aclanthology.org/2023.findings-acl.527/
- Park, K., et al. (2024). *The Linear Representation Hypothesis and the Geometry of Large Language Models*. ICML / PMLR. https://proceedings.mlr.press/v235/park24c.html
- Ramsauer, H., et al. (2020). *Hopfield Networks Is All You Need*. arXiv / OpenReview. https://openreview.net/forum?id=tL89RnzIiCd
- Risko, E. F., & Gilbert, S. J. (2016). *Cognitive Offloading*. Trends in Cognitive Sciences. https://doi.org/10.1016/j.tics.2016.07.002
- Todd, E., et al. (2023). *Function Vectors in Large Language Models*. arXiv preprint. https://arxiv.org/abs/2310.15213
- Vessey, I. (1991). *Cognitive Fit: A Theory-Based Analysis of the Graphs Versus Tables Literature*. Decision Sciences. https://doi.org/10.1111/j.1540-5915.1991.tb00344.x
- von Oswald, J., et al. (2022). *Transformers Learn In-Context by Gradient Descent*. arXiv preprint. https://arxiv.org/abs/2212.07677
- Wang, L., et al. (2023). *Label Words are Anchors: An Information Flow Perspective for Understanding In-Context Learning*. EMNLP. https://aclanthology.org/2023.emnlp-main.609/
- Xie, Q., et al. (2026). *Beyond Prompt Engineering: A Systematic Analysis of Prompt Lexical Sensitivity and Its Impacts on Quality*. Findings of ACL. https://aclanthology.org/2026.findings-acl.2084/
- Xie, S. M., et al. (2022). *An Explanation of In-context Learning as Implicit Bayesian Inference*. ICLR / arXiv. https://arxiv.org/abs/2111.02080
- Zhuo, J., et al. (2024). *ProSA: Assessing and Understanding the Prompt Sensitivity of LLMs*. Findings of EMNLP. https://aclanthology.org/2024.findings-emnlp.108/
