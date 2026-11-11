<a id="paper-semantic-locality"></a>
<a id="locality"></a>
<a id="locality-semantic-locality"></a>
# Semantic Locality

## Abstract

Relevant instructions and facts can be present in a language model’s context without consistently influencing the operation that needs them. Semantic Locality characterizes how the placement and distribution of contextual representations relative to their points of use shape that influence. The paper defines sequence distance, normalized position, structural neighborhoods, and placement profiles that capture both single and multiple representations of a semantic object. It introduces position–response functions and controlled relocation comparisons to measure behavioral consistency while holding the task, intended meaning, total support, and layout constraints fixed. The framework also examines how positional effects vary with context length and interact with semantic history (Shadow) and represented support (Weight). Its central prediction is that changing placement or distribution can alter consistency even when represented content and declared support remain unchanged; the effect need not improve monotonically with proximity.

## Introduction

> **Context behavioral influence depends on its locality—the placement and distribution of its representations relative to their points of use**

This paper develops locality as the geometric dimension of contextual semantic influence. It defines sequence distance, normalized position, structural neighborhoods, and placement profiles, and specifies controlled relocation experiments that preserve intended meaning and total support. The proposed measurements characterize how placement and distribution relate to behavioral consistency across context lengths, including interactions with semantic history and represented support.

## Role Within the Context Triad

The [Context Triad](./README.md#paper-context-triad) develops the shared thesis that semantic presence is insufficient to explain behavioral influence. Locality supplies its account of **placement relative to use**. [Shadow](./Semantic_Shadow.md#paper-semantic-shadow) supplies semantic-history contrasts; [Weight](./Semantic_Weight.md#paper-semantic-weight) supplies support measures and support–response theory.

This paper defines positional geometry, describes its behavioral effects and interactions, and presents ways to quantify them.

## Construct Definition and Boundaries

**In plain language.** Locality concerns where an instruction or relevant fact appears in the context relative to the operation that needs it.

<a id="locality-semantic-object"></a>
<a id="locality-point-of-use"></a>
### Objects, Representations, and Points of Use

A **semantic object** $A$ is an intended instruction, constraint, definition, priority, or state assertion. A representation $a_i$ is one contextual expression of that object. A **point of use** $u_k$ is the operation at which $A$ must affect behavior. The same object can have several representations and several points of use.

Locality relates representations to an operation. A statement near one operation can be remote from a later one. A nearby reference may still require a remote definition to be recovered.

<a id="locality-frame-distance"></a>
<a id="locality-physical-distance"></a>
### Input-Sequence Geometry

Sequence distance describes the gap between a represented span and its point of use. Distance starts at the **end** of the represented span; span length remains a separate property.

**Quantification.** Choose a unit for measuring positions in the input sequence, preferably model-token boundaries when available. For representation $a_i$, let $(b_i,e_i)$ be its start and end boundaries. For a use at boundary $u_k\ge e_i$, define:

```math
D(a_i,u_k)=u_k-e_i.
```

For a single representation, write $p_A=e_i$ and $D_A=u-p_A$. The use boundary can be the start of a requested response. Later within generated output, earlier generated text changes the context and use position.

<a id="locality-relative-locality"></a>
<a id="locality-relative-position-hypothesis"></a>
### Normalized Coordinates and Context Length

Absolute and normalized coordinates describe different comparisons across context lengths. The same absolute distance can occupy different fractions of the active context.

**Quantification.** Let $L_u$ be the length of the active input sequence at use. Define:

```math
D_A^{rel}=\frac{u-p_A}{L_u},
\qquad
z_A=P_A^{rel}=\frac{p_A}{L_u}.
```

With an origin at the start of active context and terminal use $u=L_u$, $D_A^{rel}=1-z_A$. These deterministically related coordinates are not independent effects. Tokenization, message boundaries, and wrappers are part of the input-sequence geometry.

<a id="locality-multiple-support"></a>
<a id="locality-profile-hypothesis"></a>
### Placement Profiles

Several representations of the same object can be clustered or distributed while preserving total support. The nearest representation, centroid, or mean distance summarizes different aspects of that arrangement; no single summary preserves the full layout.

**Quantification.** For several representations, define the profile:

```math
\mathcal P_A(u)=\{(b_i,e_i,\tau_i):a_i\text{ represents }A\},
```

where $\tau_i$ records the declared representation type, such as full statement, paraphrase, or reference. Distances follow from these coordinates. Analogous profiles describe competitors and relevant supporting spans.

<a id="locality-neighborhood"></a>
### Structural Neighborhood and Semantic Content

Structural surroundings, such as a heading or message wrapper, are distinct from the meaning of nearby text. Moving an object with its fixed wrapper changes global placement while approximately preserving local structure. Changing nearby support or competition is a separate semantic change.

Irrelevant context can itself degrade reasoning performance ([Shi et al., 2023](https://proceedings.mlr.press/v202/shi23a.html)), so surrounding content is not behaviorally inert merely because it does not support the object.

**Quantification.** For a radius $r$, a descriptive neighborhood is:

```math
N_r(a_i)=C[\max(0,b_i-r):\min(L_u,e_i+r)].
```

This identifies the surrounding span; it does not reduce the meaning of that span to distance alone.

## Behavioral Effects

<a id="locality-position-hypothesis"></a>
<a id="locality-middle-hypothesis"></a>
### Positional Sensitivity and Related Evidence

Position sensitivity in long-context tasks motivates this construct. *Lost in the Middle* studies the use of information at different input positions; *RULER* evaluates long-context capabilities beyond a single retrieval probe; and *Found in the Middle* studies positional attention bias ([Liu et al., 2024](https://aclanthology.org/2024.tacl-1.9/); [Hsieh et al., 2024](https://arxiv.org/abs/2404.06654); [Hsieh et al., 2024b](https://arxiv.org/abs/2406.16008)).

Instruction-placement experiments likewise report improved instruction following when task instructions are moved after long inputs (Y. Liu et al., 2024), while LongPiBench finds that spacing among multiple relevant information pieces can itself bias long-context performance (Tian et al., 2025), motivating placement profiles over multiple representations.

Dependency-distance and retrieval accounts in psycholinguistics provide terminological antecedents ([Gibson, 1998](https://doi.org/10.1016/S0010-0277(98)00034-1); [Lewis & Vasishth, 2005](https://doi.org/10.1207/s15516709cog0000_25)).

NoLiMa shows stronger long-context degradation when relevant information must be recovered through latent semantic association rather than direct lexical matching ([Modarressi et al., 2025](https://proceedings.mlr.press/v267/modarressi25a.html)), motivating representation type as a condition on positional sensitivity. Zhang et al. (2024) further show that exact location cues can mitigate position bias, distinguishing guidance about where information occurs from relocation of the information itself.

Beginning/middle/end asymmetry is one possible position profile. Locality does not imply that behavioral consistency increases monotonically as distance to use decreases.

#### Quantification: Shared Behavioral Measurement

Let $C$ include the complete active context and the task at the declared point of use. For response $Y$, define a score $s_A(Y)\in[0,1]$ that measures behavioral consistency with semantic object $A$. Define:

```math
E_A(C)=\mathbb{E}[s_A(Y)\mid C],
\qquad
\widehat E_A(C)=\frac{1}{n}\sum_{r=1}^{n}s_A(Y_r).
```

The expectation is conditional on the declared model version, task, and generation settings. The estimator averages $n$ runs of the same condition. Behavioral consistency is an outcome; attributing its change to a particular contextual property depends on the comparison being made. Consistency with object $A$ is distinct from correctness under the authorized current state.

<a id="locality-position"></a>
#### Quantification: Position–Response Function

Let $C(z;\xi)$ be a context family in which $z$ specifies placement and $\xi$ records the preserved task, represented content, total support, layout constraints, and other declared conditions. Define:

```math
f_A^{loc}(z;\xi)=E_A(C(z;\xi)).
```

For two placements:

```math
\Delta_A^{loc}(z_2,z_1;\xi)
=
f_A^{loc}(z_2;\xi)-f_A^{loc}(z_1;\xi).
```

A positive contrast means greater consistency with $A$ at $z_2$ in the comparison.

<a id="locality-relocation"></a>
A relocation contrast can compare one fixed representation in two equal-capacity layouts:

~~~text
Condition 1: [A] [neutral] [neutral] [fixed task]
Condition 2: [neutral] [neutral] [A] [fixed task]
~~~

The content multiset, total support, input-sequence length, task, wrappers, and authority remain fixed. Crossing a competitor also changes order, so such a contrast includes the relationship described by Shadow.

For a specified grid $Z$, summarize the population response range as:

```math
V_A^{loc}(Z;\xi)
=
\max_{z\in Z} f_A^{loc}(z;\xi)
-
\min_{z\in Z} f_A^{loc}(z;\xi).
```

Empirical maxima and minima are noise-sensitive; an observed range is not an unbiased estimate of the population range.

### Profile and Length Comparisons

At equal declared support, changing the placement profile may change behavioral consistency. Context length also changes the relationship between absolute distance and normalized position.

**Quantification.** Two placement profiles with identical declared support units can be compared using the same response-score difference. The conditional response surface $f_A^{loc}(z,L_u;\xi)$ describes position and length together. Matched absolute distances and matched normalized coordinates describe different cross-length comparisons.

## Interactions with the Other Dimensions

<a id="locality-refresh-hypothesis"></a>
<a id="h5--local-representation-benefit-as-a-compound-prediction"></a>
### Locality and Weight: Refresh and Distribution

Additional support may compensate for unfavorable placements, and distributed support may differ from one concentrated block at the same measured total.

A refresh adds a representation, changing both the placement profile and represented support. A local reference adds a pointer whose semantic body may remain remote. Agrawal et al. (2024) improve long-document QA by periodically reintroducing instructions, and Epstein et al. (2024) improve multi-turn instruction following by appending accumulated instructions near the final task, providing direct examples of local refresh interventions.

**Quantification.** At support ratio $r$, a response-scale interaction is:

```math
I_A^{loc\times wt}
=
\Delta_A^{loc}(z_2,z_1;r_{high})
-
\Delta_A^{loc}(z_2,z_1;r_{low}).
```

Support levels use the [Weight paper's support procedure](./Semantic_Weight.md#semantic-weight-operational-proxies). Remaining conditions, including competitor geometry, define the matched comparison. A positive value means the specified locality contrast is greater at the higher support ratio.

### Locality and Shadow: Placement and Semantic History

An earlier rule's response to later competition may depend on where the rule and competitor occur. Changing competitor order also changes competitor position. A refresh changes later semantic context as well as placement and support.

**Quantification.** Compare $\Delta_A^{loc}(z_2,z_1)$ under neutral and competing histories, with the history specified in each condition. The difference between these locality contrasts measures a history-dependent locality effect. Conversely, differences in [Shadow's order contrast](./Semantic_Shadow.md#semantic-shadow-order-sensitivity) at different target layouts describe a placement-dependent order effect.

These interactions are differences of conditional effects on a declared scale. An interaction on a consistency-probability scale need not match a log-odds interaction coefficient.

## Scope and Evidence Status

Locality describes model- and task-specific behavioral relationships within active context. Its geometry and response profiles are defined under the declared serialization and contextual layout.

**Evidence status.** This paper defines the concept, describes its behavioral relationships, and presents ways to quantify them. It reports no new experiments.

## Conclusion

Semantic Locality supplies the geometry and position–response measurements needed to characterize contextual placement. Placement, distribution, and structural surroundings describe where representations are available for use; response contrasts describe their behavioral effects and interactions with semantic history and relative support. The [README](./README.md#paper-context-triad) explains how these perspectives combine.

## Related Papers

- [Semantic Shadow](./Semantic_Shadow.md#paper-semantic-shadow) — semantic history and ordering.
- [Semantic Weight](./Semantic_Weight.md#paper-semantic-weight) — competing coherent support.

## References

- Agrawal, D., Gao, S., & Gajek, M. (2024). *Can’t Remember Details in Long Documents? You Need Some R&R*. Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.742/
- Epstein, E. L., et al. (2024). *MMMT-IF: A Challenging Multimodal Multi-Turn Instruction Following Benchmark*. arXiv preprint. https://arxiv.org/abs/2409.18216
- Gibson, E. (1998). *Linguistic complexity: locality of syntactic dependencies*. Cognition. https://doi.org/10.1016/S0010-0277(98)00034-1
- Hsieh, C.-P., et al. (2024). *RULER: What's the Real Context Size of Your Long-Context Language Models?*. arXiv preprint. https://arxiv.org/abs/2404.06654
- Hsieh, C.-Y., et al. (2024b). *Found in the Middle: Calibrating Positional Attention Bias Improves Long Context Utilization*. arXiv preprint. https://arxiv.org/abs/2406.16008
- Lewis, R. L., & Vasishth, S. (2005). *An activation-based model of sentence processing as skilled memory retrieval*. Cognitive Science. https://doi.org/10.1207/s15516709cog0000_25
- Liu, N. F., et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts*. TACL. https://aclanthology.org/2024.tacl-1.9/
- Liu, Y., Zeng, X., Shao, C., Meng, F., & Zhou, J. (2024). *Instruction Position Matters in Sequence Generation with Large Language Models*. Findings of ACL 2024. https://aclanthology.org/2024.findings-acl.693/
- Modarressi, A., et al. (2025). *NoLiMa: Long-Context Evaluation Beyond Literal Matching*. ICML 2025. https://proceedings.mlr.press/v267/modarressi25a.html
- Shi, F., et al. (2023). *Large Language Models Can Be Easily Distracted by Irrelevant Context*. ICML 2023. https://proceedings.mlr.press/v202/shi23a.html
- Tian, R., et al. (2025). *Distance between Relevant Information Pieces Causes Bias in Long-Context LLMs*. Findings of ACL 2025. https://aclanthology.org/2025.findings-acl.28/
- Zhang, M., Meng, Z., & Collier, N. (2024). *Can We Instruct LLMs to Compensate for Position Bias?*. Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.732/
