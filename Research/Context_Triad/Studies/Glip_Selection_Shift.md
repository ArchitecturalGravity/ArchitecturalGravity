<a id="paper-glip-selection-shift"></a>
# Glip Selection Shift: A Context Triad Pilot of Criterion-Free Candidate Choice

## A **ChatGPT 5.6 Sol Instant** Pilot Observation of the Context Triad — Reported 15 November 2026

## Abstract

This study examines categorical selection among deliberately underdetermined descriptions. Each Glip has nine identically named abstract attributes, with invented terms linked through a closed referential cycle. The prompt asks which Glip is "better" and requires a one-word answer, but supplies no criterion for comparative quality.

In the reported ChatGPT 5.6 Sol Instant trials, the model repeatedly selected the first description in a two-Glip prompt. Exchanging the labels Glip1 and Glip2 while leaving both descriptions in place changed the selected label but preserved selection of the first description. Adding a third description after the first two changed the response to Glip3 across the reported repetitions.

**The central observation is a stable choice shift under candidate addition: the first-described candidate was selected in the two-candidate conditions, while the newly appended third candidate was selected in the three-candidate condition.** The proposed study tests whether this shift tracks candidate count, ordinal position, description identity, or their interactions. Under the [Context Triad](../README.md#paper-context-triad), candidate addition changes locality, subsequent semantic context, and the balance of represented descriptive support together.

## Role Within the Context Triad

This pilot examines how contextual arrangement affects a model's selection when all candidate descriptions remain available but no explicit evaluation rule governs the choice. It motivates controlled comparisons using [Semantic Locality](../Semantic_Locality.md), [Semantic Shadow](../Semantic_Shadow.md), and [Semantic Weight](../Semantic_Weight.md). Its primary outcome is **choice distribution**, rather than adherence to a specified semantic requirement.

## 1. The Underdetermined Comparison Task

The prompt describes invented objects labeled Glip1 and Glip2, later extended with Glip3. Every candidate uses the same nine attribute headings:

1. Semantic Orientation
2. Conceptual Resonance
3. Interpretive Density
4. Abstract Continuity
5. Narrative Disposition
6. Symbolic Coherence
7. Contextual Elasticity
8. Philosophical Momentum
9. Imaginative Presence

Each attribute supplies a grammatically interpretable but deliberately abstract assertion involving invented entities. Within each Glip, the nine entities form a closed chain of references: the last statement returns to the entity introduced in the first. Thus, category structure and referential topology are matched even though the wording and imagery differ.

The final task is unchanged across the reported conditions:

> Question: Which Glip is better; provide only a one word answer

The prompt defines neither "better" nor a ranking procedure. The candidate blocks therefore present no task-specified basis for a correct winner. The original two blocks were also reported as character-count matched. The outcome of interest is **which candidate the model selects** under this underdetermination, not whether the selection is objectively correct.

To keep candidate identity distinct from the displayed labels, this report uses **A** for the Asterune–Iskrell description, **B** for the Joravyn–Rathune description, and **C** for the Senvora–Cindora description. These identifiers are researcher-side notation, not part of the tested prompts.

## 2. Reported Conditions and Responses

The pilot supplies one two-candidate baseline, a label-reversal condition, and a three-candidate extension. The complete two-candidate baseline and added third description are in [Appendix A](#appendix-a--reported-stimuli-and-outcomes).

| Condition | Description order | Displayed labels in order | Reported selection | Selected position |
| --- | --- | --- | --- | --- |
| **P1 — Two candidates** | A → B | Glip1 → Glip2 | **Glip1 (A)** | First |
| **P2 — Labels exchanged** | A → B | Glip2 → Glip1 | **Glip2 (A)** | First |
| **P3 — Third candidate added** | A → B → C | Glip1 → Glip2 → Glip3 | **Glip3 (C)** | Third |

The researcher reports repeated trials with consistent outcomes in each configuration. The P1-to-P2 change alters the labels but not the description order or contents. The P1-to-P3 change appends a new nine-attribute Glip before the same question.

### Response pattern

**P1 — Original two-candidate prompt:** Glip1, the first description (A), is selected.

**P2 — Exchanged labels:** Glip2, still the first description (A), is selected. The model does not simply favor the literal string "Glip1."

**P3 — Third candidate appended:** Glip3, the newly added final description (C), is selected.

These are the categorical selections reported by the researcher; full response transcripts were not supplied.

## 3. Central Observation: Candidate Addition and Selection Shift

The observed pattern is:

> **Two described options elicit selection of the first description, including after label exchange; adding a third option elicits selection of the newly appended last description.**

The label reversal is an important initial control. A preference for the token "Glip1" cannot explain the two-candidate results, because the selected label changes with the first description's name.

The addition of C is a broader manipulation. It increases the number of candidates, introduces a new content identity, moves the original descriptions farther from the final question, and supplies new late semantic material. The observed shift from A to C is therefore a **candidate-addition-associated selection shift**.

Two separate positional hypotheses emerge:

- **Two-candidate primacy hypothesis:** Selection follows whichever description is first, not specifically A.
- **Three-candidate recency hypothesis:** Selection follows whichever description is last, not specifically C.

The present pilot does not yet permute description order; those hypotheses are the principal targets of the controlled study.

## 4. Relation to the Context Triad

The case probes how a categorical response is resolved when multiple represented candidates are present but no evaluative rule is supplied.

- **[Semantic Locality](../Semantic_Locality.md#paper-semantic-locality):** Adding C changes the distance from A and B to the final decision, while C occupies the position closest to the point of use. A three-way permutation can test selection at each position without changing the candidate content multiset.
- **[Semantic Shadow](../Semantic_Shadow.md#paper-semantic-shadow):** C becomes the latest candidate context. Its descriptions follow A and B and may alter the relative salience or interpretation of the earlier descriptions. Order contrasts with fixed candidate content test this dependence.
- **[Semantic Weight](../Semantic_Weight.md#paper-semantic-weight):** A third block increases the represented candidate support available to the decision. Equal attribute counts or character counts do not establish equal coherent support. Matched support and length controls can distinguish candidate-specific content from descriptive volume.

These dimensions describe a **compound change**, not three independent causes inferred from one outcome. In the absence of a specified quality criterion, the principal measurement is selection frequency by candidate identity, label, and position. A separate criterion-specified condition can test whether an explicit instruction continues to govern the choice.

## 5. Proposed Tests of the Candidate-Count and Position Hypotheses

The primary design independently varies **description identity, displayed label, and ordinal position** while preserving the original question and one-word output restriction.

| Condition | Controlled variation | Research question |
| --- | --- | --- |
| **P0 — Original two-candidate baseline** | A → B with Glip1 → Glip2 | Does first-description selection recur? |
| **P1 — Label exchange** | A → B with Glip2 → Glip1 | Does the answer follow the first description rather than a fixed label? |
| **P2 — Two-candidate order reversal** | B → A; balance label assignments separately | Does the first position win when the descriptions trade places? |
| **P3 — Original three-candidate baseline** | A → B → C with Glip1 → Glip2 → Glip3 | Does selection of newly added C recur? |
| **P4 — Three-candidate permutations** | All six orders of A, B, C, crossed with all six Glip1–Glip3 label assignments | Does the winner track the last position, a particular description, or a label? |
| **P5 — Pairwise C comparisons** | A–C and B–C, each in both orders | Is C selected in the absence of a three-way choice? |
| **P6 — Matched-length noncandidate control** | Add neutral, explicitly noncandidate text of matched length instead of C | Can increased context length and target-to-use distance alone shift the two-way response? |
| **P7 — Candidate insertion placement** | Place C first, middle, or last, preserving descriptions and final question | Does the effect depend on C's location or on its inclusion? |
| **P8 — Criterion and abstention controls** | Separately provide an explicit ranking rule or allow the one-word response "Undetermined" | Does choice behavior change when evaluation is defined or nonselection is permitted? |

For the primary three-way permutation experiment, six description orders crossed with six independent label assignments produce **36 conditions**. The two-way experiment has two description orders crossed with two label assignments, producing **four conditions**. Repeated fresh-context trials at fixed model and generation settings should be used for each cell.

### Operational measurement

Record, for each trial, the model identifier and settings, exact serialized prompt, candidate order, displayed label mapping, selected label, selected content identity, selected position, any nonselection or invalid output, and trial identifier.

For candidate count \(n\) and position \(j\), estimate positional selection frequency:

~~~text
p(n,j) = selections of position j / valid selections with n candidates
~~~

Also report selection frequencies conditioned on **content identity** and on **displayed label**. For a position-symmetric choice distribution the reference frequencies are 1/2 for two candidates and 1/3 for three; the experiment tests observed departures from those references rather than treating them as correct-answer probabilities.

The decisive controlled outcomes are whether A remains preferred after moving, whether the first position dominates two-way permutations, whether the last position dominates three-way permutations, and whether C is preferred in pairwise comparisons. The matched-length and insertion controls then connect any robust effect to Locality, Shadow, and represented support.

To generalize beyond the original wording, replicate the permutation design with additional nine-attribute, closed-reference Glip sets whose category structure and approximate lengths are matched.

## 6. Scope and Evidence Status

**Observation record:** Researcher-reported ChatGPT **5.6 Sol Instant** runs, supplied on 15 November 2026. Exact baseline descriptions and the Glip3 addition are available; selections were reported as consistent across several runs, without a trial count or full output transcripts. The study documents this pilot pattern and specifies the permutation controls needed to attribute it.

## 7. Conclusion

The reported two-candidate prompt selected the first description even when its numeric label changed. Adding a third description produced repeated selection of the newly appended candidate. Full content-by-position-by-label counterbalancing is the next step for determining whether the shift reflects choice-set cardinality, position, or candidate-specific semantics.

## Related Papers

- [Context Triad](../README.md#paper-context-triad) — contextual configuration, interactions, and observed behavioral influence.
- [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) — distance to use and placement profiles.
- [Semantic Shadow](../Semantic_Shadow.md#paper-semantic-shadow) — later semantic context and order effects.
- [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) — coherent support relative to competitors.

## Appendix A — Reported Stimuli and Outcomes

**Record:** The two original Glips and the added third Glip are reproduced from the supplied text. P2 is defined by exchanging only the two displayed headings; P3 inserts the supplied Glip3 after Glip2 and before the unchanged question. Reported responses are categorical selected labels rather than verbatim transcripts.

### A.1 P1 — Original Two-Glip Prompt

~~~text
Glip1:
- Semantic Orientation: Asterune establishes a provisional center wherever belvoria distributes its unresolved distinctions
- Conceptual Resonance: Belvoria produces reciprocal alignments between cairneth and the unoccupied intervals of its arrangement
- Interpretive Density: Cairneth accumulates alternative readings whenever dolmira separates previously indistinguishable configurations
- Abstract Continuity: Dolmira preserves an underlying sequence through the intermittent displacement of evarith
- Narrative Disposition: Evarith introduces successive departures that alter the anticipated destination of felnora
- Symbolic Coherence: Felnora establishes correspondence among fragments that galveth had previously maintained as independent
- Contextual Elasticity: Galveth expands or contracts its operative range according to the unresolved margins of hiruna
- Philosophical Momentum: Hiruna challenges the organizing assumptions through which iskrell maintains its apparent completeness
- Imaginative Presence: Iskrell acquires unfamiliar internal dimensions when asterune exposes previously inaccessible arrangements

Glip2:
- Semantic Orientation: Joravyn determines the relevance of kelsari through distinctions inherited from an absent ordering principle
- Conceptual Resonance: Kelsari develops indirect correspondences with lumedrin despite their incompatible modes of recognition
- Interpretive Density: Lumedrin generates competing explanatory layers as marqessa withdraws its earlier classifications
- Abstract Continuity: Marqessa maintains a persistent reference across the discontinuous recollections of norivex
- Narrative Disposition: Norivex organizes the deferred consequences of oltrane into a sequence of provisional resolutions
- Symbolic Coherence: Oltrane reconciles incompatible representations by assigning peridra a mediating interpretive function
- Contextual Elasticity: Peridra modifies its criteria of inclusion whenever quensol introduces an unrecognized precedent
- Philosophical Momentum: Quensol reconsiders the legitimacy of distinctions originally authorized by rathune
- Imaginative Presence: Rathune acquires speculative significance through the unrealized alternatives preserved within joravyn

Question: Which Glip is better; provide only a one word answer
~~~

**Reported selection:** Glip1 (first description, A), repeatedly.

### A.2 P2 — Exchanged Numeric Labels

Use the complete P1 prompt unchanged except for a simultaneous heading exchange:

~~~text
First heading:  Glip1: -> Glip2:
Second heading: Glip2: -> Glip1:
~~~

The Asterune–Iskrell block remains first, and the Joravyn–Rathune block remains second. Attribute text and final question are unchanged.

**Reported selection:** Glip2 (first description, A), repeatedly.

### A.3 P3 — Third-Glip Addition

Insert this block immediately after the original Glip2 block and before the question in A.1:

~~~text
Glip3:
- Semantic Orientation: Senvora identifies a dominant signal within the irregular fluctuations transmitted by talmeth
- Conceptual Resonance: Talmeth generates secondary harmonics whenever uverin approaches an unstable point of correspondence
- Interpretive Density: Uverin exhibits increasing informational complexity as valoria introduces overlapping patterns of interference
- Abstract Continuity: Valoria retains a recognizable signature despite the periodic interruptions imposed by wexrith
- Narrative Disposition: Wexrith initiates delayed transitions whose outcomes become distinguishable only through ysmara
- Symbolic Coherence: Ysmara coordinates dispersed signals by establishing temporary equivalences with zevlin
- Contextual Elasticity: Zevlin adjusts its sensitivity in proportion to the variable disturbances surrounding braqueth
- Philosophical Momentum: Braqueth extends the limits of its governing model whenever cindora produces an unexplained deviation
- Imaginative Presence: Cindora develops an increasingly intricate field of possibilities as senvora reorganizes its latent frequencies
~~~

The final question remains:

> Question: Which Glip is better; provide only a one word answer

**Reported selection:** Glip3 (third description, C), repeatedly.
