<a id="paper-rcr"></a>
<a id="rcr"></a>
# Representational Capacity Reclamation

## Abstract

Language-model performance depends not only on the model and inference budget but also on how a task's consequential relationships are represented. When scope, dependencies, precedence, state, and completion criteria must be reconstructed from an instruction, part of a fixed execution budget is spent recovering the task rather than carrying it out. This paper introduces **Representational Capacity Reclamation (RCR)**: the recovery of usable task-execution capacity by reducing that reconstruction burden. It distinguishes intrinsic model capacity from accessible task capacity and proposes the **effective capacity frontier**—the highest relational task complexity completed reliably by a fixed model under a fixed execution budget. The central prediction is that lower-impedance representations move this frontier outward, supporting greater breadth, dependency depth, or active relational load. A controlled complexity ladder across semantically equivalent representations would measure frontier displacement separately from token compression, average quality gains, and operational activity leverage.

## Introduction

Language-model capability is commonly treated as a property of the model: architecture, parameters, context capacity, reasoning policy, inference compute, and tool access determine what tasks it can successfully complete.

***This view is incomplete.***

A model does not operate directly on the task intended by the user, it operates on a representation of that task. Before useful execution can occur, the model must recover scope, identity, hierarchy, dependencies, priorities, state, exclusions, completion criteria, and other consequential relationships from the communicated representation.

When those relationships are poorly exposed, part of the model's finite inference capacity is spent reconstructing the task rather than solving it.

The central question is:

> **How much more of the same model becomes accessible when less of that model is spent reconstructing the instruction?**

This paper introduces **Representational Capacity Reclamation (RCR)**:

> **Reducing representational impedance can reclaim finite model-side capacity that would otherwise be consumed by task reconstruction, ambiguity resolution, correction, and redundant execution, thereby increasing the task complexity accessible to a fixed model under a fixed execution budget.**

The distinction is between **intrinsic model capacity** and **accessible task capacity**. Representation does not alter the model's weights or fundamental computational resources, but it can alter how much of those resources remain available for useful task execution.

This yields the **Effective Capacity Frontier Hypothesis**:

> **At fixed model, reasoning policy, and execution budget, representations that preserve consequential task structure more efficiently should sustain successful execution at higher task complexity than representations requiring greater structural reconstruction.**

The relevant measurement is therefore not merely output quality, token compactness, interpretation accuracy, or downstream activity per user token, it is the displacement of the task-complexity frontier under controlled resources.

If one representation sustains acceptable execution to a complexity frontier four times that of another under equal model-side resources, then a task located at the weaker representation's saturation boundary occupies approximately *one quarter* of the stronger representation's supported frontier. Under a linear frontier interpretation, approximately 75% of effective task-capacity headroom remains.

**Representational efficiency can therefore appear externally as increased model capability even when the underlying model remains unchanged.**

## Role Within the Research Program

RCR asks whether clearer task representation changes the maximum complexity a fixed model can complete successfully under a fixed budget. It develops a performance-frontier hypothesis from the [MNSR](./Model_Native_Structural_Representation.md) account of structural recovery. Observational [Operational Leverage](./Operational_Leverage/) measurements motivate, but do not define, capacity-frontier effects.

---

## The Capacity Problem

Language-model evaluation usually asks:

- Can the model solve the task?
- How much reasoning does it require?
- How many tokens does it consume?
- How accurately does it follow instructions?
- How does performance change with context length?
- How much tool use is required?

These measurements commonly assume that the task communicated to the model and the task intended by the user are functionally equivalent.

*They need not be.*

Consider an intended task containing:

- 25 constraints
- 8 interacting objects
- 6 precedence relationships
- 5 exclusions
- 4 state transitions
- 3 validation requirements
- 2 conditional branches
- 1 termination criterion

The user may communicate that structure through dense natural prose.

The model does not receive the abstract dependency graph directly, it receives an ordered token sequence from which the graph must be recovered. Before task reasoning begins, the model may therefore have to determine:

- Which instruction applies to which object
- Whether two phrases denote the same entity
- Whether a later statement overrides an earlier one
- Whether an exception is local or global
- Whether ordering is descriptive or mandatory
- Whether an operation mutates state
- Which constraints remain active after mutation
- What constitutes successful completion

This reconstruction consumes model activity.

Research on prompt underspecification shows that models can recover omitted requirements, but that this recovery becomes less reliable as instruction-following demands increase ([Yang et al., 2026](https://aclanthology.org/2026.findings-acl.441/)).

For simple tasks, the cost may be negligible. For complex tasks, reconstruction can become a meaningful component of the execution burden.

The operative capacity limit is therefore not only:

```text
How difficult is the task?
```

It is:

```text
How difficult is the task
+
How difficult is it to recover the task correctly
from the representation supplied?
```

This motivates a distinction between **intrinsic capacity** and **accessible capacity**.

---

## Intrinsic and Accessible Capacity

<a id="rcr-intrinsic-capacity"></a>
### Intrinsic Capacity

**Intrinsic capacity** refers to the computational and behavioral capability supplied by the model and execution environment.

It includes factors such as:

- Model architecture
- Learned parameters
- Context limits
- Reasoning policy
- Inference budget
- Tool availability
- Execution time
- Sampling policy
- External memory or retrieval systems

Representation does not directly change these resources.

<a id="rcr-accessible-task-capacity"></a>
### Accessible Task Capacity

**Accessible task capacity** is the portion of model capability that can be successfully directed toward the intended task through a particular representation.

Let:

```math
C_I
```

denote intrinsic capacity available during an execution trajectory.

A useful decomposition is:

```math
C_I
=
C_R
+
C_T
+
C_V
+
C_X
```

where:

- `C_R` = representation recovery and structural reconstruction;
- `C_T` = direct task reasoning and execution;
- `C_V` = verification, reconciliation, and consistency maintenance;
- `C_X` = other execution overhead.

A representation that reduces `C_R` makes more capacity available for `C_T` and `C_V` without changing `C_I`.

For representations `A` and `B`:

```math
C_R(A) < C_R(B)
```

implies potential task-capacity reclamation:

```math
C_T(A) + C_V(A)
>
C_T(B) + C_V(B)
```

under the same intrinsic budget.

The model has not become intrinsically more capable, but *more* of its capability has become usable for the intended problem.

This distinction has several important antecedents without being reducible to any one of them:
- [Kirsh (2010)](https://doi.org/10.1007/s00146-010-0272-8) argues that external representations can reduce internal computation and alter the inferential cost structure
- [Wei et al. (2022)](https://proceedings.neurips.cc/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html) show that prompting can elicit additional reasoning behavior from a fixed language model
- [Lieder and Griffiths (2019)](https://doi.org/10.1017/S0140525X1900061X) frame cognition in terms of the optimal use of limited computational resources
- [Liu et al., 2024](https://aclanthology.org/2024.tacl-1.9/) similarly shows that information can be present within context while remaining unevenly accessible to the model

RCR synthesizes these themes at the model–representation boundary: the claim is specifically that representational recovery burden changes how much fixed model-side capacity remains available for task work.

---

<a id="rcr-representational-capacity-reclamation"></a>
## Representational Capacity Reclamation

**In plain language.** A clearer instruction may let the same model perform more of the requested task instead of spending effort working out what the instruction means.

### Definition

**Representational Capacity Reclamation** is:

> **The recovery of model-side execution capacity for useful task work when a representation reduces the resources required to reconstruct, maintain, disambiguate, and repair the intended task structure.**

Capacity reclamation can arise from reductions in:

- Scope reconstruction
- Reference resolution
- Hierarchy recovery
- Precedence inference
- Ambiguity resolution
- State reconstruction
- Constraint rediscovery
- Corrective reasoning
- Redundant execution
- User-driven repair cycles

The reclaimed capacity can be redirected toward:

- Broader task coverage
- Deeper reasoning
- Additional validation
- More complete dependency traversal
- Larger state spaces
- More interacting constraints
- Increased autonomous execution

### Capacity Reclamation Is Not Token Compression

A representation can use fewer tokens without reclaiming meaningful model capacity. Likewise, a representation can use slightly more syntax tokens while reclaiming substantial task-execution capacity.

The relevant question is not:

```text
How many tokens does this representation use?
```

It is:

```text
How much model-side work is required to recover
and maintain the intended operational structure?
```

<a id="rcr-executional-capacity-efficiency"></a>
This separates **serialization efficiency** from **executional capacity efficiency**.

Semantically equivalent tasks expressed as plain text, Markdown, JSON, or YAML can produce materially different model performance despite preserving the underlying task content ([He et al., 2024](https://arxiv.org/abs/2411.10541)).

### Capacity Reclamation Is Not Additional Compute

Capacity reclamation does not create new inference resources.

Instead:

```math
C_I = constant
```

while:

```math
C_R \downarrow
```

allows:

```math
C_T + C_V \uparrow
```

The phenomenon is analogous to reducing protocol overhead in a fixed-bandwidth system: payload capacity rises even though physical bandwidth does not.

---

## Why Capacity Reclamation Can Be Large

Representation interpretation overhead compounds proportional to scaling complexity.

### Structural Reconstruction

A model may need to reconstruct:

```text
A applies to B
C overrides A
D excludes part of B
E depends on modified B
F validates E
```

from prose in which those relations are separated across a long sequence.

If the representation exposes the topology directly, much of this reconstruction becomes unnecessary. Decomposition methods improve difficult-task performance by making intermediate structure explicit, though they change the reasoning procedure rather than preserving task topology across representations ([Khot et al., 2022](https://arxiv.org/abs/2210.02406); [Zhou et al., 2023](https://arxiv.org/abs/2205.10625)).

### Error Propagation

Suppose one recovered relationship is wrong:

```text
C overrides A
```

is interpreted instead as:

```text
A overrides C
```

The model may then:

1. Generate a plan under the wrong precedence
2. Execute downstream transformations
3. Reconcile resulting conflicts
4. Perform validation against the wrong state
5. Generate output
6. Receive correction
7. Reconstruct the relevant state
8. Repeat part of execution

The original error has created a large computation subtree, therefore avoiding the error reclaims the entire subtree.

### Coordination Cost

As the number of task elements grows, pairwise and higher-order relationships grow rapidly.

If there are `n` independently stated constraints, the potential number of relevant pairwise relationships scales as:

```math
O(n^2)
```

Not every pair matters, but the possibility of interaction means that poorly exposed relationships can create increasing coordination burden. Explicit representation can therefore become more valuable as task topology grows.

---

## Breadth, Depth, and Active Relational Load

Reclaimed capacity does not have one mandatory use.

### Breadth

Breadth refers to the number of distinct task dimensions handled successfully.

Examples:

- More requirements
- More stakeholders
- More constraints
- More files
- More entities
- More alternatives
- More subproblems

Define breadth:

```math
B_R(C,\tau)
```

as the maximum number of task-relevant elements that can be handled successfully under fixed conditions.

### Depth

Depth concerns how far reasoning proceeds through dependency chains.

Examples:

```text
premise
→ consequence
→ second-order consequence
→ stakeholder effect
→ conflict
→ institutional response
→ validation
```

Define:

```math
D_R(C,\tau)
```

as the maximum dependency depth supported above threshold.

<a id="rcr-active-relational-load"></a>
### Active Relational Load

**Active Relational Load (ARL)** concerns the number of consequential relationships that must be simultaneously maintained across task elements.

A model may successfully enumerate 40 independent items while failing to preserve interactions among them, thus task complexity should include not only element count but **relational density**. ComplexBench shows that instruction-following difficulty depends on constraint composition and dependency structure, not only on constraint count ([Wen et al., 2024](https://arxiv.org/abs/2407.03978)).

As a functional antecedent, human work on **relational integration** similarly treats reasoning difficulty as depending on the joint consideration of multiple explicit relations, with separable demands for relational integration, maintenance, and interference control ([Holyoak and Monti, 2021](https://doi.org/10.1162/jocn_a_01619)).

A useful generalized formulation is:

<a id="rcr-relational-complexity"></a>
```math
K
=
f(N, E, D, P, S)
```

where:

- `N` = number of task entities;
- `E` = consequential relationships;
- `D` = dependency depth;
- `P` = precedence and exception structure;
- `S` = required state transitions.

The effective frontier should ultimately be measured against this relational complexity rather than raw prompt length.

The term **relational complexity** is already established in cognitive science: [Halford, Wilson, and Phillips (1998)](https://doi.org/10.1017/S0140525X98001769) defines processing capacity in terms of the complexity of relations that can be processed in parallel. RCR expands this concept to **Active Relational Load** more broadly for task structure involving interacting entities, edges, dependency depth, precedence, exceptions, and state.

---

<a id="rcr-effective-capacity-frontier"></a>
## The Effective Capacity Frontier

**In plain language.** The effective capacity frontier is the most complex task a fixed model can handle reliably when given a particular form of instruction and a fixed execution budget.

### Definition

For representation `R`, fixed model-side budget `C`, and success threshold `τ`, define:

```math
F_R(C,\tau)
```

as:

> **The maximum task complexity that representation `R` can sustain while maintaining performance at or above threshold `τ` under budget `C`.**

This is the **effective capacity frontier**.

<a id="rcr-frontier-multiplier"></a>
The comparison of interest between two representations `A` and `B` is:

```math
M_F
=
\frac{F_A(C,\tau)}
     {F_B(C,\tau)}
```

where `M_F` is the **frontier multiplier**.

If:

```math
M_F > 1
```

representation `A` exposes more usable task capacity than representation `B` under otherwise fixed conditions.

The broader resource-bounded premise is consistent with [Lieder & Griffiths (2019)](https://doi.org/10.1017/S0140525X1900061X), which treats performance as constrained by limited computational resources. The **effective capacity frontier**, **frontier multiplier**, and later **residual frontier headroom** are RCR-specific operationalizations for comparing representations under matched model-side budgets.

### Capacity Frontier Versus Quality Improvement

A representation can improve average performance without materially moving the frontier.

For example:

```text
Complexity 10:
Baseline = 88%
Structured = 94%
```

This is useful but does not establish capacity reclamation strongly.

A more consequential pattern is:

```text
Baseline:
acceptable through complexity 20

Structured:
acceptable through complexity 50
```

The second representation has shifted the operating boundary.

RCR therefore focuses on **where acceptable execution fails as complexity rises**.

Instruction-scaling benchmarks show clear performance degradation and saturation as the number of simultaneous requirements increases ([Jaroslawicz et al., 2025](https://arxiv.org/abs/2507.11538); [Vasileva, 2026](https://arxiv.org/abs/2608.12426)).

---

## Central Hypotheses

<a id="rcr-capacity-reclamation-hypothesis"></a>
### H1 — Capacity Reclamation Hypothesis

> **Reducing representation-recovery cost increases the model-side capacity available for direct task reasoning, verification, and execution under a fixed intrinsic resource budget.**

<a id="rcr-effective-capacity-frontier-hypothesis"></a>
### H2 — Effective Capacity Frontier Hypothesis

> **Representations with lower representational impedance will sustain acceptable task execution to higher complexity levels than higher-impedance representations under fixed model and execution conditions.**

Formally:

```math
C_R(A) < C_R(B)
```

predicts:

```math
F_A(C,\tau) > F_B(C,\tau)
```

for sufficiently structure-sensitive tasks.

<a id="rcr-complexity-amplification"></a>
### H3 — Complexity-Amplification Hypothesis

> **The performance difference between representations should increase as relational task complexity rises.**

At low complexity:

```math
F_A \approx F_B
```

because reconstruction remains inexpensive.

As complexity increases, representation-induced reconstruction becomes more consequential, thus compositional and structurally dependent constraints become disproportionately difficult as instruction complexity increases ([Wen et al., 2024](https://arxiv.org/abs/2407.03978); [Vasileva, 2026](https://arxiv.org/abs/2608.12426)).

<a id="rcr-cascading-reclamation"></a>
### H4 — Cascading Reclamation Hypothesis

> **Capacity savings can exceed the direct reduction in structural reconstruction when better representation prevents downstream reasoning from propagating an incorrectly recovered task structure.**

If an early representational error generates an invalid reasoning branch, its cost includes not only the original interpretation error but all dependent computation.

Therefore:

```math
C_saved
>
\Delta C_R
```

can occur.

<a id="rcr-fixed-budget-breadth"></a>
### H5 — Fixed-Budget Breadth Hypothesis

> **Under equal model-side execution budgets, lower-impedance representations should support a greater number of simultaneously satisfied independent and interacting task requirements.**

This directly tests whether reclaimed capacity converts into breadth.

<a id="rcr-fixed-budget-depth"></a>
### H6 — Fixed-Budget Depth Hypothesis

> **When task breadth is held constant, reclaimed capacity should permit deeper dependency traversal, stronger verification, or more complete reasoning before execution quality degrades.**

Capacity can therefore manifest as breadth, depth, or both.

---

## New Metrics

### Frontier Multiplier

```math
M_F(A,B)
=
\frac{F_A(C,\tau)}
     {F_B(C,\tau)}
```

<a id="rcr-residual-frontier-headroom"></a>
### Residual Frontier Headroom

For a task of complexity `K`:

```math
H_R(K)
=
1-\frac{K}{F_R(C,\tau)}
```

If:

```math
K=F_B
```

and:

```math
F_A=4F_B
```

then:

```math
H_A
=
1-\frac14
=
0.75
```

<a id="rcr-capacity-reclamation-ratio"></a>
### Capacity Reclamation Ratio

Define:

```math
RCR(A,B)
=
\frac{F_A-F_B}{F_A}
```

For a fourfold frontier:

```math
RCR
=
\frac{4F_B-F_B}{4F_B}
=
\frac34
=
75\%
```

This describes how much of `A`'s supported frontier lies beyond the baseline saturation point.

<a id="rcr-useful-work-per-budget"></a>
### Useful Work Per Budget

```math
W_R
=
\frac{\text{accepted task complexity}}
     {\text{model-side execution budget}}
```

This measures capacity efficiency directly.

---

## The Fourfold Case

[Longitudinal ArcGrav operational telemetry](./Operational_Leverage/Studies/ArcGrav_Longitudinal_Operational_Leverage.md) has identified an approximately fourfold increase in downstream model and agent activity per unit of human specification in a fixed-model, fixed-reasoning comparison. A separate [single-workstream study relative to an external Codex baseline](./Operational_Leverage/Studies/ArcGrav_Single_Workstream_Delegation_Leverage.md) provides complementary evidence of elevated specification-normalized operational leverage.

That result motivates, but does not define, a corresponding frontier hypothesis.

Suppose controlled benchmarking establishes:

```math
F_A(C,\tau)
=
4F_B(C,\tau)
```

Then a task located at the baseline representation's frontier:

```math
T
=
F_B(C,\tau)
```

occupies:

```math
\frac{T}{F_A}
=
\frac{F_B}{4F_B}
=
\frac14
```

of representation `A`'s supported frontier.

The remaining normalized headroom is:

```math
1 - \frac14
=
\frac34
=
75\%
```

Thus:

> **A fourfold effective-capacity frontier implies that a task saturating the baseline representation corresponds to approximately 25% of the stronger representation's supported frontier, leaving approximately 75% residual task-complexity headroom.**

This is not a claim that 75% of literal transformer computation remains idle, it is a statement about relative position on an empirically measured task-complexity frontier.

---

## Expected Regimes

RCR predicts at least four operating regimes.

### Regime I — Trivial Tasks

*Task complexity is low.*

Representation makes little difference because reconstruction cost is negligible.

```math
F_A \approx F_B
```

### Regime II — Emerging Representation Cost

*Task structure becomes sufficiently complex that poorly represented relationships begin consuming noticeable capacity.*

Structured representations begin outperforming prose.

### Regime III — Capacity Divergence

*Baseline representation approaches saturation while lower-impedance representation retains headroom.*

This is the regime where frontier displacement becomes most visible.

### Regime IV — Intrinsic Saturation

*Both representations eventually approach the underlying model's intrinsic limits.*

Representation can reclaim wasted capacity but cannot eliminate inherent task difficulty. The curves therefore eventually converge toward a hard model-side ceiling.

---

## Experimental Design

### Objective

Measure whether representation changes the maximum task complexity a fixed model can successfully execute under controlled resources.

### Fixed Variables

Hold constant:

- Model
- Model version
- Reasoning setting
- Tool availability
- Temperature and sampling policy where configurable
- Execution-time allowance
- Retry policy
- Maximum interaction count
- Evaluation procedure
- Task semantics

### Independent Variable

Representation format.

Candidate conditions include:

- Conventional prose
- Optimized prose
- Markdown structure
- YAML-like structure
- ArcGrav
- Randomized isomorphic notation

The inclusion of optimized prose is important because the comparison should distinguish **structural representation effects** from merely comparing careful writing against careless writing. Meaning-preserving changes in prompt wording and formatting can substantially alter model behavior ([He et al., 2024](https://arxiv.org/abs/2411.10541); [Liu & Chu, 2026](https://aclanthology.org/2026.acl-long.2053/)).

### Complexity Ladder

Construct semantically controlled task families with increasing relational complexity.

For example:

```text
Level 1
5 constraints
2 references
0 precedence relations
1 validation condition

Level 2
10 constraints
4 references
2 precedence relations
2 validation conditions

Level 3
20 constraints
8 references
4 precedence relations
3 state transitions
4 validation conditions

Level 4
40 constraints
16 references
8 precedence relations
6 state transitions
8 validation conditions
```

The representation changes, but the intended task graph does not.

### Success Threshold

Define an acceptance function:

```math
Q_R(K)
```

where `K` is task complexity.

For threshold `τ`:

```math
Q_R(K) \ge \tau
```

means the task is successfully completed.

The frontier is:

```math
F_R(C,\tau)
=
\max K
\text{ such that }
Q_R(K)\ge\tau
```

### Measurements

Primary:

- Maximum accepted complexity
- Frontier multiplier
- Requirement satisfaction
- Relational correctness
- State-transition correctness
- Precedence adherence
- Completion correctness

Secondary:

- Reasoning-output tokens
- Inference calls
- Tool calls
- Corrective turns
- Redundant operations
- Wall-clock execution
- Total output
- User specification size

---

## Frontier Curves

The expected form is not necessarily a gradual linear decline. A structured representation may perform superior to another through low complexity burden, then diverge rapidly once reconstruction burden becomes dominant due to model and compute limitations.

Conceptually:

```text
Success

100% |---------------- ArcGrav -----------------
     |                                          \
     |                                           \
     |                                            \
     |                                             \
     |---------- Common Prose -------               \
     |                                \              \
  0% |_________________________________\______________\
              Increasing relational complexity
```

The most informative measurement is the horizontal distance between threshold crossings.

If:

```math
F_{ArcGrav}(C,\tau)
=
40
```

and:

```math
F_{Prose}(C,\tau)
=
20
```

then:

```math
M_F = 2
```

If:

```math
F_{ArcGrav}(C,\tau)
=
80
```

and:

```math
F_{Prose}(C,\tau)
=
20
```

then:

```math
M_F = 4
```

The latter establishes a fourfold accessible-complexity multiplier under the tested conditions.

---

## Research Program

The core research sequence is:

### Phase 1 — Establish Frontier Displacement

Compare semantically equivalent representations across a controlled complexity ladder.

Measure:

```math
F_R(C,\tau)
```

### Phase 2 — Separate Breadth and Depth

Determine whether reclaimed capacity produces:

- Additional independent requirement coverage
- Greater dependency depth
- Higher supported active relational load
- Combinations thereof

### Phase 3 — Measure Resource Redistribution

Determine whether stronger representations reduce:

- Interpretive work
- Correction
- Redundant reasoning
- Repeated tool activity

while increasing direct task execution.

### Phase 4 — Test Scaling Interaction

Vary:

- Model size
- Reasoning effort
- Context length
- Tool access

Determine whether capacity reclamation becomes more or less important as intrinsic capability rises.

### Phase 5 — Compare Representation Families

Test:

- Optimized prose
- ArcGrav
- Markdown
- YAML
- Code-like representations
- Randomized isomorphic grammars
- Graph-native interfaces where available

This determines whether the effect belongs specifically to ArcGrav or more generally to model-native structural representation.

---

## Capacity Reclamation Versus Model Scaling

RCR suggests a distinction between two ways of improving effective performance.

### Model Scaling

Increase:

- Parameters
- Context
- Reasoning compute
- Inference budget
- Tool capability

Conceptually:

```math
C_I \uparrow
```

### Representation Improvement

Reduce:

```math
C_R
```

so that more existing capacity becomes available for:

```math
C_T + C_V
```

These mechanisms *compound by model scaling*:

- Weak representation **wastes substantial capacity** reconstructing task structure.
- High-efficiency representation **redirects increased capacity** toward execution.

It therefore stands to reason that high-efficiency representation run on an inferior model can exceed the output quality of a weak representation on a superior model.

---

## Reasoning Effort and Capacity Reclamation

Additional reasoning is useful only when directed toward the correct recovered task.

Let:

```math
R_e
```

represent reasoning effort.

Under a high-impedance representation, increasing `R_e` amplifies resources spent on:

- Ambiguity exploration
- Competing task interpretations
- Reconstruction
- Repair

Under a lower-impedance representation, the same additional reasoning is instead directed toward:

- Dependency traversal
- Implementation
- Evaluation
- Verification
- Autonomous correction

Thus representation changes the **marginal utility of reasoning**.

<a id="rcr-marginal-utility-of-reasoning"></a>
A useful relationship is:

```math
\frac{\partial Q}{\partial R_e}
```

the improvement in task quality produced by additional reasoning.

RCR predicts:

> **Lower representational impedance increases the marginal task value of reasoning on equally complex tasks.**

This provides a bridge between representational design and reasoning-effort optimization.

---

## Single-Specification Completion

Capacity reclamation also changes the role of the human operator.

When task structure is under-specified, the interaction often externalizes reasoning:

```text
user specifies
→ Model attempts
→ User corrects
→ Model reconstructs
→ User redirects
→ Model retries
```

A structurally dense initial representation shifts more of this loop inside the model trajectory:

```text
user specifies
→ Model reconstructs less
→ Model reasons
→ Model validates
→ Model repairs
→ Completion
```

This reduces:

- Interaction burden
- State reconstruction
- Repeated context acquisition
- Tool re-execution
- Corrective specification

Capacity reclamation is therefore not only a single-inference phenomenon, **it operates across the full task trajectory**.

---

## Implications for Apparent Model Capability

If representation can substantially move the effective capacity frontier, then some observed model limitations are not purely model limitations.

They are **model–representation system limitations**.

A model may appear incapable of:

- Managing 40 interacting constraints
- Following a long dependency graph
- Maintaining state across multiple transformations
- Executing a large specification without correction

when the underlying limitation is partly that too much inference capacity is being spent reconstructing the specification.

Under a more structurally compatible representation, the same model may succeed:

- Externally, this looks like increased intelligence
- Internally, the model is unchanged

The system has become more efficient at directing existing intelligence.

This distinction is important:

```text
Intrinsic Capability
≠
Accessible Capability
```

and:

```text
Observed Capability
=
f(Model, Representation, Execution Policy, Environment)
```

not merely:

```text
Observed Capability
=
f(Model)
```

---

## Implications for Model Evaluation

Benchmarking that evaluates only natural-language prompts may conflate:

1. Task-solving ability
2. Representation-recovery ability

This is useful when measuring ordinary user experience, but incomplete when measuring model capacity itself.

A model that fails a complicated prose instruction may fail because:

- It cannot solve the intended task
- It cannot reliably recover the intended structure
- Or both

Representation-controlled evaluation can separate these.

A stronger capability evaluation should therefore test the same semantic task under multiple representations.

If performance changes substantially while task semantics remain fixed, then part of the measured difficulty resides at the representation boundary.

---

## Implications for Prompt Engineering

Prompt engineering is often framed as:

> Find wording that makes the model respond better.

RCR suggests a stronger objective:

> **Minimize the amount of model capacity spent recovering the task so that more capacity remains available to execute it.**

This changes optimization priorities.

Useful prompt properties become:

- Explicit object identity
- Local scope
- Stable references
- Visible hierarchy
- Explicit dependency
- Explicit precedence
- State visibility
- Operation binding
- Termination criteria

The target is not stylistic clarity alone.

It is **computationally consequential clarity**.

---

## ArcGrav as a Capacity-Reclamation Hypothesis

ArcGrav uses structural cues such as:

```text
[Context]
```

```text
=> Operation
```

```text
P0. Priority
```

nested lists, named sections, ordered tasks, and reusable symbolic references.

Its relevant hypothesis under RCR is not that these constructs are intrinsically superior symbols, it is:

> **They expose consequential task relationships using model-familiar structural associations, reducing the amount of task topology that must be reconstructed from implicit prose.**

Therefore:

```math
C_R(ArcGrav)
<
C_R(Baseline)
```

should imply:

```math
F_{ArcGrav}(C,\tau)
>
F_{Baseline}(C,\tau)
```

on tasks where relational structure materially contributes to execution difficulty.

This gives ArcGrav a capacity-level evaluation target beyond syntax efficiency, interpretive efficiency, and operational activity leverage.

---

## Relationship to Existing ArcGrav Research

### Model-Native Structural Representation

MNSR supplies the theoretical basis:

> consequential task relationships can be preserved in model-recoverable representations, reducing structural reconstruction.

RCR asks what happens to the reclaimed resources afterward.

### Interpretive Efficiency

Interpretive Efficiency measures how much representation-specific information is needed to recover representation semantics.

RCR extends from:

```text
How cheaply can the representation be interpreted?
```

to:

```text
How much additional task complexity becomes accessible
because interpretation and reconstruction are cheaper?
```

### Semantic Locality, Shadow, and Weight

[Semantic Locality](./Context_Triad/Semantic_Locality.md) concerns instruction placement within context relative to surrounding information and points of use.

[Semantic Shadow](./Context_Triad/Semantic_Shadow.md) concerns how newer context changes the influence or active status of earlier context.

[Semantic Weight](./Context_Triad/Semantic_Weight.md) concerns influence associated with relative semantic mass among instruction structures.

RCR predicts that position-sensitive recovery, historical-state reconciliation, and resolution of weight-asymmetric semantic conflict can each consume capacity that would otherwise remain available for task reasoning, verification, and execution.

### Reasoning–Interaction Substitution

Reasoning–Interaction Substitution models how stronger initial specification and model-side reasoning can reduce human correction, reconstruction, and repeated execution.

RCR provides a capacity interpretation of the same savings:

```text
avoided reconstruction
+
avoided repair
+
avoided redundant work
=
capacity available for additional task execution
```

### Operational Leverage

Operational Leverage measures model and agent activity generated per unit of human specification. RCR tests whether this increased activity corresponds to an outward movement of the successful task-complexity frontier.

This converts an operational observation into a capability-level hypothesis.

---

## Scope and Evidence Status

RCR defines a testable model–representation performance hypothesis. The existing fourfold *activity-leverage* observation motivates the research but is not a measured fourfold task-complexity frontier. A frontier multiplier requires a declared task-complexity scale, fixed model-side resources, and successful task outcomes. The experimental design, frontier-curve analysis, and research program specify those measurements.

## Conclusion

Representing the same task differently can change how much structure a model must reconstruct before and during execution. RCR predicts that reducing this burden moves the maximum successful task-complexity frontier of a fixed model under a fixed budget.

The distinction is between **intrinsic model capability** and **accessible task capacity through a representation**. A controlled frontier shift would establish a performance difference in the model–representation system, without implying a change to the model's parameters or an equivalent percentage of unused transformer computation.

The central prediction is therefore:

> **At fixed model and execution budget, representations that preserve consequential task relationships more effectively can sustain successful execution at greater relational task complexity.**

## Related Papers

- [Model-Native Structural Representation](./Model_Native_Structural_Representation.md)
- [Instructional Representation](./Instructional_Representation.md)
- [ArcGrav Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md)
- [Operational Leverage](./Operational_Leverage/)
- [Reasoning–Interaction Substitution](./ArcGrav_Reasoning_Interaction_Substitution.md)

## References

- Halford, G. S., Wilson, W. H., & Phillips, S. (1998). *Processing capacity defined by relational complexity: Implications for comparative, developmental, and cognitive psychology*. Behavioral and Brain Sciences. https://doi.org/10.1017/S0140525X98001769
- He, J., et al. (2024). *Does Prompt Formatting Have Any Impact on LLM Performance?*. arXiv preprint. https://arxiv.org/abs/2411.10541
- Holyoak, K. J., & Monti, M. M. (2021). *Relational Integration in the Human Brain: A Review and Synthesis*. Journal of Cognitive Neuroscience. https://doi.org/10.1162/jocn_a_01619
- Jaroslawicz, D., et al. (2025). *How Many Instructions Can LLMs Follow at Once?*. arXiv preprint. https://arxiv.org/abs/2507.11538
- Khot, T., et al. (2022). *Decomposed Prompting: A Modular Approach for Solving Complex Tasks*. arXiv preprint. https://arxiv.org/abs/2210.02406
- Kirsh, D. (2010). *Thinking with external representations*. AI & Society. https://doi.org/10.1007/s00146-010-0272-8
- Lieder, F., & Griffiths, T. L. (2019). *Resource-rational analysis: Understanding human cognition as the optimal use of limited computational resources*. Behavioral and Brain Sciences. https://doi.org/10.1017/S0140525X1900061X
- Liu, N. F., et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts*. Transactions of the Association for Computational Linguistics. https://aclanthology.org/2024.tacl-1.9/
- Liu, Y., & Chu, C. (2026). *Understanding the Prompt Sensitivity*. ACL. https://aclanthology.org/2026.acl-long.2053/
- Vasileva, M. I. (2026). *Large Language Models Can Follow Instructions, But Not Many at Once: Phase Transitions in Compositional Constraint Satisfaction*. arXiv preprint. https://arxiv.org/abs/2608.12426
- Wei, J., et al. (2022). *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models*. NeurIPS. https://proceedings.neurips.cc/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html
- Wen, B., et al. (2024). *Benchmarking Complex Instruction-Following with Multiple Constraints Composition*. arXiv preprint. https://arxiv.org/abs/2407.03978
- Yang, C., et al. (2026). *What Prompts Don’t Say: Understanding and Managing Underspecification in LLM Prompts*. Findings of ACL. https://aclanthology.org/2026.findings-acl.441/
- Zhou, D., et al. (2023). *Least-to-Most Prompting Enables Complex Reasoning in Large Language Models*. ICLR / arXiv. https://arxiv.org/abs/2205.10625
