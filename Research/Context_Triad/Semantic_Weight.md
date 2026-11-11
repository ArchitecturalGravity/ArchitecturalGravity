<a id="paper-semantic-weight"></a>
<a id="semantic-weight"></a>
# Semantic Weight

## Abstract

Large language model contexts can contain competing rules, interpretations, or state assertions receiving different amounts and forms of coherent support. This paper defines **Semantic Weight** as an object's share of that support relative to relevant competitors, separating represented support from both text volume and observed behavioral consistency. It introduces latent semantic mass and operational proxies using designated supporting-token spans or matched support units, then defines competitive shares, pairwise ratios, absolute support totals, and global support density. Conditional support–response functions measure consistency as the balance and scale of support vary. Proposed comparisons test reinforcement, dilution, proportional scaling, and restoration, with controls for placement and semantic history linking Weight to the other dimensions of the Context Triad. The framework tests whether changing support balance shifts consistency and whether equal ratios can produce different responses at different scales or arrangements.

## Introduction

> **Context behavioral influence varies based on its semantic weight—the volume and support represented by it relative to competing objects**

This paper develops semantic weight as the relative amount of coherent support represented for a semantic object, rather than raw text volume or behavioral influence itself. It defines semantic mass, operational support proxies, competitive shares and ratios, and support–response functions. Proposed experiments on reinforcement, proportional scaling, dilution, and restoration test how support balance, absolute support totals, and representation form relate to behavioral consistency. Placement and order controls connect these tests to the other dimensions of the Context Triad.

## Role within the Context Triad

The [Context Triad](./README.md#paper-context-triad) develops the shared thesis and conceptual interactions. Weight supplies its theory of **relative coherent support**. [Locality](./Semantic_Locality.md#paper-semantic-locality) defines placement; [Shadow](./Semantic_Shadow.md#paper-semantic-shadow) defines semantic-history contrasts and their order sensitivity.

This paper defines represented support, describes its behavioral effects and interactions, and presents ways to quantify them.

## Construct definition and boundaries

**In plain language.** Semantic Weight is how much coherent support one meaning receives compared with competing meanings; it is not simply the number of words used.

### Support is not its behavioral effect

A semantic object $A$ is an intended rule, constraint, definition, priority, or state assertion. Several contextual representations can support the same object through direct statements, repetition, paraphrase, examples, or elaboration.

Coherent support is defined independently of behavioral outcomes. Each representation is classified by the meaning it supports.

Irrelevant text, contradictory examples, or elaboration that changes the rule can increase length without adding support for the original object. “Return JSON” and “return a top-level JSON object with exactly three keys” specify different behavioral requirements. The shared requirement and the changed object remain distinct.

<a id="semantic-weight-semantic-mass"></a>
### Latent semantic mass

Support varies in form, specificity, redundancy, and semantic consistency. Its represented amount is distinct from the behavioral influence it produces.

**Quantification.** Let $M_A(C)$ denote the theoretical amount of coherent support represented for $A$ in context $C$. This latent construct is approximated through the declared proxies below. Comparisons across support families require an independently calibrated scale; family-specific quantities do not automatically form a common semantic-mass scale.

<a id="semantic-weight-operational-proxies"></a>
<a id="semantic-weight-size-proxy"></a>
### Declared operational proxies

Exact repetition, equivalent paraphrase, examples, rationale, and elaboration are separate representation families. Equal token or unit counts do not automatically imply equivalent support across families.

**Quantification.** Use $\widehat M_A^{(q)}(C)$ for a measurable approximation under procedure $q$. Two baseline procedures are:

```math
\widehat M_A^{token}(C)
=\text{number of tokens in predesignated spans supporting }A,
```

```math
\widehat M_A^{unit}(C)
=\text{number of preconstructed, approximately matched support units for }A.
```

The proxy depends on the span boundaries, tokenizer or serialization, support-unit definition, and semantic classification. Support is defined independently of behavioral outcomes.

For overlapping support, an expression may contribute to multiple objects, but each token is counted once within an object's token proxy. The competitive denominator compares the declared objects' support; it need not partition all prompt tokens. Ambiguous or mixed support requires an explicit counting convention.

<a id="semantic-weight-relative-semantic-weight"></a>
<a id="semantic-weight-ratio"></a>
### Competitive shares, ratios, and total support

Competitive weight describes support for an object relative to the objects relevant to the behavioral decision. Ratio and absolute support totals distinguish small and large balanced blocks. Adding a relevant object changes the competitive set.

**Quantification.** Let $G$ include $A$ and the objects relevant to the behavioral decision. For a positive total, define the theoretical share and its measured counterpart:

```math
W_A(C)=\frac{M_A(C)}{\sum_{j\in G}M_j(C)},
\qquad
\widehat W_A^{(q)}(C)
=\frac{\widehat M_A^{(q)}(C)}{\sum_{j\in G}\widehat M_j^{(q)}(C)}.
```

For pairwise competition with positive support on both sides:

```math
\widehat R_{A:B}^{(q)}
=\frac{\widehat M_A^{(q)}}{\widehat M_B^{(q)}},
\qquad
\widehat S^{(q)}=\widehat M_A^{(q)}+\widehat M_B^{(q)}.
```

Ratios with zero denominator are undefined; no-competitor conditions are separate cases. Log-ratios require positive support on both sides. Competitive shares sum to one for the declared $G$. $W_A$ measures support share; $E_A$ measures behavioral consistency.

<a id="semantic-weight-global-weight"></a>
### Global support density

Competitive weight is distinct from global support density. Unrelated filler can lower density without changing competitive support shares. Appending filler also changes context length and possibly placement.

**Quantification.** A global token-density measure is:

```math
D_A^{token}(C)=\frac{\widehat M_A^{token}(C)}{L(C)},
```

where numerator and denominator use the same tokenization and each supporting token is counted once for $A$. Other proxy families require an explicitly defined, commensurate denominator for global fractions. A density change alone does not isolate a behavioral effect from accompanying changes in length or placement.

## Behavioral effects

### Relation to prior work

Research on contradictory long-context information includes manipulations of repetition and position and motivates considering these dimensions together ([Kurfali & Östling, 2025](https://aclanthology.org/2025.emnlp-main.1742/)).

In-context-learning research provides related evidence that represented support magnitude and order both affect behavior. Zhao et al. (2021) identify majority-label and recency biases, Yu and Ananiadou (2024) study both effects within a common ICL setting, and Lu et al. (2022) show large performance differences across permutations of a fixed demonstration set. These results also motivate separating contextual support from learned priors.

Additional evidence comes from demonstration composition and scale: Hu et al. (2024) find that minority/majority demonstration proportions shift fairness–accuracy behavior; Zou et al. (2025) find that additional demonstrations help some task families but not others; and Zhang et al. (2025) report plateauing and eventual decline as many-shot demonstrations increase. These results motivate task- and family-specific support–response functions with possible saturation or non-monotonicity.

#### Quantification: shared behavioral measurement

Let $C$ include the complete active context and the task at the declared point of use. For response $Y$, define a score $s_A(Y)\in[0,1]$ that measures behavioral consistency with semantic object $A$. Define:

```math
E_A(C)=\mathbb{E}[s_A(Y)\mid C],
\qquad
\widehat E_A(C)=\frac{1}{n}\sum_{r=1}^{n}s_A(Y_r).
```

The expectation is conditional on the declared model version, task, and generation settings. The estimator averages $n$ runs of the same condition. Behavioral consistency is an outcome; attributing its change to a particular contextual property depends on the comparison being made. Consistency with object $A$ is distinct from correctness under the authorized current state.

<a id="semantic-weight-effective-influence"></a>
<a id="semantic-weight-influence-curve"></a>
<a id="semantic-weight-hypothesis"></a>
<a id="semantic-weight-dominance-hypothesis"></a>
### Support–response function

Increasing the $A:B$ support ratio may increase consistency with $A$, but non-monotonicity, reversal, or saturation limits a stronger monotonic-dominance account. A coherently larger competing section may change descriptive behavioral dominance even when the smaller instruction remains explicit and visible. Represented support does not determine which instruction has authority.

**Quantification.** Let $C(r;\xi,q)$ have declared support ratio $r$, construction procedure $q$, and remaining conditions $\xi$, including total support and geometry. Define:

```math
f_A^{wt}(r;\xi,q)=E_A(C(r;\xi,q)),
```

and:

```math
\Delta_A^{wt}(r_2,r_1;\xi,q)
=f_A^{wt}(r_2;\xi,q)-f_A^{wt}(r_1;\xi,q).
```

A positive contrast means greater consistency with $A$ at $r_2$ in the specified comparison. Where several support realizations have the same nominal ratio, a specified average over realizations defines the response function; the nominal ratio alone does not determine the realized content.

For scale comparisons, use $f_A^{wt}(r,S;\xi,q)$, where $S$ denotes total support. Ratio, total support, and both absolute masses are algebraically related rather than independent quantities. Response curves can describe monotonicity, thresholds, saturation, and asymmetry; a threshold is defined within the measured range only when the specified response level is crossed.

<a id="semantic-weight-reinforcement"></a>
<a id="semantic-weight-semantic-reinforcement"></a>
<a id="semantic-weight-dilution"></a>
<a id="semantic-weight-semantic-dilution"></a>
<a id="semantic-weight-reinforcement-hypothesis"></a>
### Reinforcement and dilution

Under a declared nonnegative proxy, increasing support for $A$ while holding competitor support fixed raises $A$'s measured competitive share. Increasing only competitor support lowers it. The associated behavioral change is distinct from this arithmetic change in share.

**Quantification.** For coherent and neutral expansions into the same fixed slot, define:

```math
\Delta_A^{coh}
=E_A(C_{coherent})-E_A(C_{neutral}).
```

This compares the declared coherent expansion against equal-length neutral text with the same task and remaining context. A positive value means greater consistency under the coherent expansion. An expansion after the original target also changes semantic history, so the contrast does not isolate support from all interactions.

<a id="semantic-weight-scale-invariance"></a>
<a id="semantic-weight-weight-preservation"></a>
<a id="semantic-weight-scale-invariance-hypothesis"></a>
<a id="semantic-weight-restoration-hypothesis"></a>
### Proportional scaling and restoration

Multiplying every relevant mass by the same positive factor preserves its normalized share. It does not, by definition, preserve behavioral consistency.

Restoring a ratio at a larger total changes absolute support and its placement profile. A return to the original support balance therefore need not restore the original behavior.

**Quantification.** The behavioral change at a fixed ratio $r$ is:

```math
\Delta_A^{scale}
=f_A^{wt}(r,S_2;\xi,q)-f_A^{wt}(r,S_1;\xi,q).
```

A zero contrast denotes equal expected consistency at the two scales; positive and negative values describe the direction of change. The remaining contextual envelope and layout conditions are fixed in this comparison.

For restoration, distances from the original baseline, such as $|E_A(C_{restored})-E_A(C_{baseline})|$ and $|E_A(C_{diluted})-E_A(C_{baseline})|$, quantify how close restored and diluted behavior are to the original behavior. Each context's absolute support totals, placement profile, and semantic history determine what that comparison includes.

## Interactions with the other dimensions

### Weight and Locality

Adding support changes the distribution of supporting representations even when outer slot boundaries remain fixed. Additional support may compensate for unfavorable placements, and distributed support may differ from one concentrated block at the same measured total.

**Quantification.** A placement-dependent support effect is:

```math
I_A^{wt\times loc}
=\Delta_A^{wt}(r_2,r_1;z_{near},q)
-\Delta_A^{wt}(r_2,r_1;z_{far},q).
```

The geometry includes competitor and support-span positions as well as the target placement. A positive value means the specified support contrast is greater at the nearer placement. [Placement profiles](./Semantic_Locality.md#locality-multiple-support) describe the supporting representations in each condition.

### Weight and Shadow

Support supplied after an earlier object changes semantic history as well as represented balance. The behavioral effect of a support ratio can depend on the order in which supporting and competing material occurs. Demonstration frequency, order, and recency can each shift outcomes in few-shot prompting (Zhao et al., 2021; Lu et al., 2022; Yu & Ananiadou, 2024).

**Quantification.** A history-dependent support effect compares the same ratio contrast across matched semantic-history conditions. Conversely, differences in [Shadow's order contrast](./Semantic_Shadow.md#semantic-shadow-order-sensitivity) at different support levels describe a support-dependent order effect.

These interactions measure conditional response differences on a declared scale, not independent internal mechanisms or an automatically additive decomposition.

## Scope and Evidence Status

Weight describes how represented support relates to behavioral consistency within active context. Support–response profiles are defined for the declared measurement procedure, representation family, model, task, and competitor set. This paper develops the theoretical and measurement framework and proposes experimental comparisons; it reports no new experiments.

## Conclusion

Semantic Weight describes coherent support relative to the objects relevant to a decision. Support proxies, competitive shares and ratios, and support–response measurements distinguish represented balance from behavioral consistency and quantify its interactions with placement and semantic history. The [README](./README.md#paper-context-triad) explains how these perspectives combine.

## Related Papers

- [Semantic Locality](./Semantic_Locality.md#paper-semantic-locality) — placement and distribution of contextual representations.
- [Semantic Shadow](./Semantic_Shadow.md#paper-semantic-shadow) — semantic history and order effects.

## References

- Hu, J., Liu, W., & Du, M. (2024). *Strategic Demonstration Selection for Improved Fairness in LLM In-Context Learning*. EMNLP 2024. https://aclanthology.org/2024.emnlp-main.425/
- Kurfali, M., & Östling, R. (2025). *Conflicting Needles in a Haystack: How LLMs behave when faced with contradictory information*. ACL Anthology. https://aclanthology.org/2025.emnlp-main.1742/
- Lu, Y., et al. (2022). *Fantastically Ordered Prompts and Where to Find Them: Overcoming Few-Shot Prompt Order Sensitivity*. ACL 2022. https://aclanthology.org/2022.acl-long.556/
- Yu, Z., & Ananiadou, S. (2024). *How do Large Language Models Learn In-Context? Query and Key Matrices of In-Context Heads are Two Towers for Metric Learning*. EMNLP 2024. https://aclanthology.org/2024.emnlp-main.192/
- Zhang, X., et al. (2025). *More is not always better? Enhancing Many-Shot In-Context Learning with Differentiated and Reweighting Objectives*. ACL 2025. https://aclanthology.org/2025.acl-long.1475/
- Zhao, Z., et al. (2021). *Calibrate Before Use: Improving Few-shot Performance of Language Models*. ICML 2021. https://proceedings.mlr.press/v139/zhao21c.html
- Zou, K., Khalifa, M., & Wang, L. (2025). *On Many-Shot In-Context Learning for Long-Context Evaluation*. ACL 2025. https://aclanthology.org/2025.acl-long.1245/
