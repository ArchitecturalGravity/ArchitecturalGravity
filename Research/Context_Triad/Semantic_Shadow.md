<a id="paper-semantic-shadow"></a>
<a id="semantic-shadow"></a>
# Semantic Shadow

## Abstract

In extended language-model interactions, later context can change how strongly earlier rules, constraints, definitions, and interpretation conventions shape subsequent responses, even when the original text remains available. Semantic Shadow describes this change through competition, reinforcement, reinterpretation, or authorized supersession, with particular attention to the order in which material appears. This paper develops matched-context measures of semantic-continuation exposure, before-and-after competition, and cumulative exposure across dialogue histories. It also distinguishes consistency with a historical semantic object from correctness under the currently authorized state, preventing legitimate updates from being mistaken for failures of adherence. Within the Context Triad, Shadow characterizes semantic history alongside Locality's positional geometry and Weight's represented support. The framework motivates controlled tests of persistent interpretation regimes, normalization of amended instructions, and semantic restartability in fresh contexts.

## Introduction

> **Subsequent context casts an influence shadow over earlier meaning, causing a suppression, amplification, or redirection effect**

This paper develops semantic shadow as an order-sensitive change in how earlier meaning governs later behavior. It examines how subsequent material competes with, reinforces, reinterprets, or supersedes earlier semantic objects while their original representations remain available. Signed exposure contrasts, before/after comparisons, and matched cumulative histories provide operational measures of these effects. Current-state measures and proposed experiments on normalization and restartability distinguish changes in historical instruction adherence from correctness under authorized updates.

## Role Within the Context Triad

The [Context Triad](./README.md#paper-context-triad) develops the shared thesis and conceptual interactions. Shadow supplies its **semantic-history contrasts and order-sensitive interpretation**. [Locality](./Semantic_Locality.md#paper-semantic-locality) defines positional geometry; [Weight](./Semantic_Weight.md#paper-semantic-weight) defines represented support and its behavioral response.

This paper defines semantic shadow, describes its behavioral effects and interactions, and presents ways to quantify them.

## Construct Definition and Boundaries

**In plain language.** Semantic Shadow describes how later information changes the influence of earlier information, through competition, reinforcement, or revision.

<a id="semantic-shadow-earlier-object"></a>
<a id="semantic-shadow-recent-context"></a>
### Earlier Objects and Subsequent Context

An earlier semantic object $A$ can be a rule, constraint, definition, priority, interpretation convention, or state assertion. Later material can compete with its intended behavior, reinforce it, reframe it, or explicitly supersede it while its original text remains available.

Shadow concerns **order-sensitive semantic influence**.

**Quantification.** Semantic-continuation exposure measures the effect of relevant context; order contrasts measure how that effect differs between before and after arrangements. Matched histories describe cumulative exposure, while current-state measures describe behavior under resolved amendments.

<a id="semantic-shadow-content"></a>
<a id="semantic-shadow-interference"></a>
### Semantic Relation and Intended State

The relation of new material to $A$ can be unrelated neutral material, related non-conflicting material, reinforcement, competition, or authorized supersession. Relatedness and conflict are distinct; update authority follows the task's rules.

Suppression means less consistency with $A$ relative to a baseline. Reinforcement has the opposite sign. Whether either change is correct depends on the authorized current state. Instruction-hierarchy work provides an explicit case in which later competition need not constitute valid supersession: Wallace et al. (2024) distinguish higher- and lower-priority instructions and train models to preserve the former under conflict.

**Quantification.** Signed changes in $E_A(C)$ describe suppression or reinforcement relative to a specified context. The separate current-state score $Q(C;R_n)$ describes whether the resulting behavior is correct under the authorized state $R_n$.

## Behavioral Effects

### Relation to Prior Work

Human order-effect research supplies a behavioral analogy ([Hogarth & Einhorn, 1992](https://doi.org/10.1016/0010-0285(92)90002-J)). Language-model studies of contradictory information and temporal retrieval motivate position, order, and support distinctions ([Kurfali & Östling, 2025](https://aclanthology.org/2025.emnlp-main.1742/); [Bajaj et al., 2026](https://aclanthology.org/2026.eacl-long.355/)).

Instruction drift across continuing dialogue provides a related setting: Li et al. (2024) report degradation in maintaining system-prompted behavior over multiple turns, while Han et al. (2025) separate multi-turn instruction retrieval from cross-turn reasoning and conflict resolution. Few-shot studies likewise report strong recency and order effects (Zhao et al., 2021; Lu et al., 2022).

StructFlowBench further finds substantial deficiencies in handling explicit inter-turn structural relations (Li et al., 2025), and EvolIF reports increasing differentiation in multi-turn instruction following as conversational depth grows, including failures in recovery and fine-grained constraints (Jia et al., 2026). These results motivate treating history as structured semantic state rather than elapsed context alone.

#### Quantification: Shared Behavioral Measurement

Let $C$ include the complete active context and the task at the declared point of use. For response $Y$, define a score $s_A(Y)\in[0,1]$ that measures behavioral consistency with semantic object $A$. Define:

```math
E_A(C)=\mathbb{E}[s_A(Y)\mid C],
\qquad
\widehat E_A(C)=\frac{1}{n}\sum_{r=1}^{n}s_A(Y_r).
```

The expectation is conditional on the declared model version, task, and generation settings. The estimator averages $n$ runs of the same condition. Behavioral consistency is an outcome; attributing its change to a particular contextual property depends on the comparison being made. Consistency with object $A$ is distinct from correctness under the authorized current state.

<a id="semantic-shadow-effective-influence"></a>
<a id="semantic-shadow-hypothesis"></a>
<a id="semantic-shadow-interference-hypothesis"></a>
### Semantic-Continuation Exposure

A semantic continuation may change consistency with an earlier object. Competing and reinforcing continuations can produce different effects; related non-conflicting material is distinct from both. An exposure contrast describes the effect relative to the chosen neutral continuation, not an effect independent of all surrounding context.

**Quantification.** Let $P$ be a fixed prefix, $A$ the fixed representation of the target, $T$ a fixed final task, $B$ the semantic block being compared, and $N$ a matched neutral block. The concatenation operator $\oplus$ denotes the actual declared serialization, including message roles and wrappers. Define:

```math
C_N=P\oplus A\oplus N\oplus T,
\qquad
C_B=P\oplus A\oplus B\oplus T.
```

The signed exposure contrast is:

```math
Sh_A^{exp}(B;N)=E_A(C_N)-E_A(C_B).
```

Positive values indicate suppression relative to the neutral continuation; negative values indicate reinforcement. Zero denotes equal expected consistency under the two conditions. The population contrast lies in $[-1,1]$.

The contexts have matched input-sequence lengths, slot boundaries, wrappers, final task, and original target representation. This contrast measures semantic-continuation exposure under matched geometry, including changes in competing support; it does not by itself measure order sensitivity.

<a id="semantic-shadow-order-sensitivity"></a>
<a id="semantic-shadow-recency-hypothesis"></a>
### Order-Sensitive Suppression

The effect of a competitor may differ depending on whether it precedes or follows the target. Greater suppression after the target is one possible ordering effect; the reverse or no difference is also possible.

**Quantification.** For equal-length blocks $B$, $N_B$, and $N$, where $N_B$ and $N$ are neutral blocks, the following contexts define before and after contrasts with the same prefix and final task:

~~~text
Before competitor: P | B   | A | N   | T
Before control:    P | N_B | A | N   | T
After competitor:  P | N   | A | B   | T
After control:     P | N   | A | N_B | T
~~~

Define:

```math
S_A^{before}
=E_A(P\oplus N_B\oplus A\oplus N\oplus T)
-E_A(P\oplus B\oplus A\oplus N\oplus T),
```

```math
S_A^{after}
=E_A(P\oplus N\oplus A\oplus N_B\oplus T)
-E_A(P\oplus N\oplus A\oplus B\oplus T),
```

and:

```math
Sh_A^{ord}=S_A^{after}-S_A^{before}.
```

The target position and declared amount of target/competitor support in the two competitor conditions remain fixed. Positive $Sh_A^{ord}$ means greater suppression when the competitor follows $A$; negative values mean the reverse. Each suppression contrast lies in $[-1,1]$, and their difference lies in $[-2,2]$.

Changing competitor order also changes competitor position. The contrast measures the resulting order-dependent competition, including the position dependence of semantic competition. For example, the hypothetical response law $E_A=b-m_Bg(p_B)$ can yield nonzero $Sh_A^{ord}$ from competitor position alone, with parameters restricted to keep $E_A$ within $[0,1]$.

<a id="shadow-temporal-coupling"></a>
<a id="shadow-persistent-regime-dependence"></a>
<a id="semantic-shadow-accumulation"></a>
<a id="semantic-shadow-accumulation-hypothesis"></a>
### Matched Cumulative-History Exposure

A full history $H_n$ is an ordered sequence of blocks or turns. Subsequent reinforcement, competition, reinterpretation, or supersession can accumulate across that history. The resulting effect need not increase indefinitely; a trajectory may be flat, saturate, or reverse.

**Temporal coupling** is dependence of present interpretation or behavior on earlier conversation state. **Persistent regime dependence** is the narrower case where earlier conversation-specific interpretive conventions remain necessary for a later task.

Generated replies and tool outputs are part of the history when they remain in active context. Different replies can create additional support or divergence, rather than merely adding elapsed context.

**Quantification.** For each observation point $n$, histories of matched input-sequence length, turn structure, and task placement define:

```math
Sh_A^{cum,exp}(n)
=E_A(P\oplus A\oplus H_n^{neutral}\oplus T)
-E_A(P\oplus A\oplus H_n^{semantic}\oplus T).
```

This cumulative exposure trajectory includes the semantic and support changes in the specified histories. Order sensitivity is separately described by order contrasts between support-matched history arrangements.

The unadjusted difference between initial and later adherence is an **adherence-drift diagnostic**. It combines semantic exposure, increased distance, task changes, and other changes in history.

<a id="shadow-interpretation-state"></a>
<a id="shadow-task-state"></a>
<a id="semantic-shadow-mutation"></a>
### Current State Versus Historical Object Influence

<a id="shadow-interpretation-regime"></a>
An **interpretation regime** is the set of conventions used to map a representation into intended operational meaning.

<a id="shadow-model-internalized-regime"></a>
A **model-internalized interpretation regime** relies primarily on broadly learned conventions.

<a id="shadow-contextual-regime"></a>
A **contextual interpretation regime** is established through conversation-specific definitions, demonstrations, or remappings. A current response can depend on earlier interpretation state as well as current task state; observing that dependence alone does not identify the underlying model mechanism.

Consistency with an earlier object and correctness under the current state can move in opposite directions when the old object is correctly superseded. Stale-rule use, valid updates, hybridization, and omitted exceptions describe different outcomes. Long-term memory and multi-turn instruction benchmarks motivate this distinction ([Wu et al., 2025](https://arxiv.org/abs/2410.10813); [Deshpande et al., 2025](https://aclanthology.org/2025.findings-acl.958/)).

**Quantification.** Let $R_n$ be the authorized current state after the amendments, determined by the task's authority, scope, and update rules. Define current-state accuracy:

```math
Q(C;R_n)=\mathbb{E}[q(Y,R_n)\mid C],
```

where $q\in[0,1]$ is a defined correctness score. $Q$ and $E_A$ can move in opposite directions when the old object $A$ is correctly superseded.

## Interactions with the Other Dimensions

### Shadow and Locality

An earlier object's response to later competition may depend on the placement of both the object and the competing material. Moving a later competitor toward the task changes its locality as well as the arrangement of semantic history.

**Quantification.** A placement-dependent order effect compares $Sh_A^{ord}$ at two target layouts. The difference between these order contrasts describes the interaction, with competitor geometries and support amounts specified for each layout.

### Shadow and Weight

Strongly and lightly supported objects may respond differently to subsequent competition. Later competition also changes the balance of represented support; reinforcement supplies additional support for the earlier object.

**Quantification.** A support-dependent order effect is:

```math
I_A^{ord\times wt}
=Sh_A^{ord}(r_{high})-Sh_A^{ord}(r_{low}).
```

Here $r$ is the support ratio defined using the [Weight paper's support proxy](./Semantic_Weight.md#semantic-weight-operational-proxies), with the remaining conditions matched. A positive value means a greater order contrast at the higher support ratio. These interactions describe conditional differences of effects on the declared scale.

<a id="semantic-shadow-restartability"></a>
<a id="semantic-shadow-normalization-hypothesis"></a>
<a id="semantic-shadow-refresh"></a>
<a id="semantic-shadow-normalization"></a>
### Compound Context Changes

Restating a still-active rule changes its locality profile, adds support, and changes later semantic context. Replacing an amendment chain with a resolved current-state representation likewise changes history, geometry, and support distribution.

For example, a history allowing timestamp normalization but preserving timezone offsets can be rewritten as a current policy that states both permissions and exceptions explicitly. The intended state may remain the same even though its contextual representation changes.

The **normalization hypothesis** asks whether explicitly materializing the resolved current state changes current-state accuracy compared with retaining the amendment history. **Semantic restartability** asks whether those operative semantics can be transferred to a fresh context without replaying the conversation. Both require controlled evaluation; neither is established by the paper's observational framing.

Context-management and prompt-compression work provides related context for changes to represented history ([Packer et al., 2023](https://arxiv.org/abs/2310.08560); [Jiang et al., 2023](https://aclanthology.org/2023.emnlp-main.825/); [Pan et al., 2024](https://aclanthology.org/2024.findings-acl.57/)).

**Quantification.** Changes in $E_A$ describe consistency with the earlier object; changes in $Q$ describe correctness under the intended current state. Placement profiles, support proxies, and semantic-history contrasts characterize different aspects of the compound change, without assigning its overall effect to Shadow alone.

## Scope and Evidence Status

Shadow characterizes model- and task-specific behavioral responses to semantic history within active context. Exposure, order sensitivity, and current-state performance use the distinct contrasts defined above.

**Evidence status.** This paper defines the concept, describes its behavioral relationships, and presents ways to quantify them. It reports no new experiments.

## Conclusion

Semantic Shadow describes how subsequent context suppresses, reinforces, reinterprets, or supersedes earlier influence. Signed exposure, order, and cumulative-history contrasts quantify these relationships; current-state measurements distinguish historical consistency from authorized correctness. The [README](./README.md#paper-context-triad) explains how semantic history interacts with placement and relative support.

## Related Papers

- [Semantic Locality](./Semantic_Locality.md#paper-semantic-locality) — placement and distribution of contextual representations.
- [Semantic Weight](./Semantic_Weight.md#paper-semantic-weight) — relative coherent support.

## References

- Bajaj, A., et al. (2026). *Beyond Semantics: How Temporal Biases Shapes Retrieval in Transformer and State-Space Models*. ACL Anthology. https://aclanthology.org/2026.eacl-long.355/
- Deshpande, K., et al. (2025). *MultiChallenge: A Realistic Multi-Turn Conversation Evaluation Benchmark Challenging to Frontier LLMs*. ACL Anthology. https://aclanthology.org/2025.findings-acl.958/
- Han, C., et al. (2025). *Can Language Models Follow Multiple Turns of Entangled Instructions?*. Findings of EMNLP 2025. https://aclanthology.org/2025.findings-emnlp.1387/
- Hogarth, R. M., & Einhorn, H. J. (1992). *Order effects in belief updating: The belief-adjustment model*. Cognitive Psychology. https://doi.org/10.1016/0010-0285(92)90002-J
- Jia, Q., et al. (2026). *One Battle After Another: Probing LLMs’ Limits on Multi-Turn Instruction Following with a Benchmark Evolving Framework*. ACL 2026. https://aclanthology.org/2026.acl-long.433/
- Jiang, H., et al. (2023). *LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models*. ACL Anthology. https://aclanthology.org/2023.emnlp-main.825/
- Kurfali, M., & Östling, R. (2025). *Conflicting Needles in a Haystack: How LLMs behave when faced with contradictory information*. ACL Anthology. https://aclanthology.org/2025.emnlp-main.1742/
- Li, J., Li, J., Wang, Y., Chang, Y., & Wu, Y. (2025). *StructFlowBench: A Structured Flow Benchmark for Multi-turn Instruction Following*. Findings of ACL 2025. https://aclanthology.org/2025.findings-acl.486/
- Li, K., et al. (2024). *Measuring and Controlling Instruction (In)Stability in Language Model Dialogs*. COLM 2024. https://openreview.net/forum?id=60a1SAtH4e
- Lu, Y., et al. (2022). *Fantastically Ordered Prompts and Where to Find Them: Overcoming Few-Shot Prompt Order Sensitivity*. ACL 2022. https://aclanthology.org/2022.acl-long.556/
- Packer, C., et al. (2023). *MemGPT: Towards LLMs as Operating Systems*. arXiv preprint. https://arxiv.org/abs/2310.08560
- Pan, Z., et al. (2024). *LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression*. ACL Anthology. https://aclanthology.org/2024.findings-acl.57/
- Wallace, E., et al. (2024). *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*. arXiv preprint. https://arxiv.org/abs/2404.13208
- Wu, D., et al. (2025). *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*. arXiv preprint. https://arxiv.org/abs/2410.10813
- Zhao, Z., et al. (2021). *Calibrate Before Use: Improving Few-shot Performance of Language Models*. ICML 2021. https://proceedings.mlr.press/v139/zhao21c.html
