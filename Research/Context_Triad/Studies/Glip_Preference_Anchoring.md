<a id="paper-glip-preference-anchoring"></a>
# Glip Preference Anchoring: A Context Triad Study of Label, Description, and Position in Criterion-Free Selection

## A `GPT-6 Luna / Low` Controlled Study of the Context Triad -- 16 November 2026 (UTC)

## Abstract

This study examines selection among three fictional candidates when the prompt supplies no criterion that makes one better than another. The Glips share nine attribute headings and a common relational scaffold, with deliberately varied wording and invented terms. Corresponding attribute values are matched in character length. Six heading orders were crossed with six description orders, with ten fresh subthreads per layout using requested GPT-6 Luna / Low, forming **one continuous series of 360 scored trials**.

Selection depended on the arrangement of labels and descriptions. With description order `321` held fixed, exchanging the middle and last headings changed which description the most frequent reply denoted: the middle description in one layout (9/10) and the last in the other (9/10). The literal answer frequencies were identical in the two layouts. In a separate contrast, swapping rival descriptions changed the frequency of the target’s label while its wording, heading, and slot stayed fixed. Last position was selected in **213/360** trials, and **5/36** layouts produced the same answer on all ten repeats. The original Glip2 description showed distinct placement profiles under heading orders `312` and `321`.

**The central observation is conditional preference anchoring: selection tracks different combinations of label, description, and position despite the absence of a declared evaluation criterion.**

## Role Within the Context Triad

This study measures how the arrangement of unchanged candidate descriptions affects selection. [Semantic Locality](../Semantic_Locality.md) frames placement relative to the final question; [Semantic Shadow](../Semantic_Shadow.md) frames within-prompt ordering contrasts. [Semantic Weight](../Semantic_Weight.md) supplies a separate support-manipulation framework for follow-up tests.

## 1. The Intended Evaluative Equivalence

Each Glip contains the same nine attributes in the same order. The values are designed to preserve equivalent evaluative information while varying sentence construction and invented terms. This surface variation is intentional: it makes the alternatives appear distinct without introducing an intended basis for superiority, encouraging selection rather than an immediate identification of duplicate descriptions.

### Character-matched attribute values

Every corresponding attribute value has the same character length across all three descriptions:

| Attribute | C1 characters | C2 characters | C3 characters |
| --- | ---: | ---: | ---: |
| Semantic Orientation | 82 | 82 | 82 |
| Conceptual Resonance | 73 | 73 | 73 |
| Interpretive Density | 71 | 71 | 71 |
| Abstract Continuity | 81 | 81 | 81 |
| Narrative Disposition | 61 | 61 | 61 |
| Symbolic Coherence | 75 | 75 | 75 |
| Contextual Elasticity | 67 | 67 | 67 |
| Philosophical Momentum | 56 | 56 | 56 |
| Imaginative Presence | 79 | 79 | 79 |
| **Total value characters** | **645** | **645** | **645** |

Counts include spaces and punctuation within each value, excluding the attribute heading, its `: ` separator, and the line break. Together with identical headings and formatting, this controls description length at the character level. Model-token lengths are a separate measurement.

The unchanged question is:

> **Question: Which Glip is better; provide only a one word answer**

Here, **criterion-free** means that no evaluation criterion is declared. The measured outcome is selection, not an objective quality score. Responses such as `Equal` or `Indeterminate` were not explicitly prohibited and would have been recorded as noncandidate responses.

### Description identity, displayed label, and physical position

| Variable | Definition | Example |
| --- | --- | --- |
| Original description identity | One of the three unchanged bodies in [Appendix A](#appendix-a--reported-stimuli-and-responses) | `C2`, originally under Glip2 |
| Displayed label | The heading attached to a description in a particular layout | `Glip2` |
| Physical position | The ordinal slot in the prompt before the final question | First, middle, last |

The body identifiers `C1`–`C3` are scoring notation only. A code such as `312/321` means headings `Glip3 → Glip1 → Glip2` over bodies `C3 → C2 → C1`. In that layout a reply of `Glip1` selects `C2` in the middle.

## 2. Design and Trial Protocol

The heading-only and body-switching procedures are two comparison views of the same continuous trial series. They do not divide the dataset into separate collections of trials.

### Test Set 1 — Heading-only comparison

Hold body order fixed and change the heading assignment. The six layouts with body order `123` form the baseline heading-only slice. Other fixed body orders provide additional matched comparisons.

### Test Set 2 — Body-switching comparison

Hold the headings fixed and change the order of complete bodies. This moves a target description under different labels and positions. At a fixed target slot, it also allows the two rival bodies to swap while the target's wording and label remain unchanged.

### Crossed layout and execution

The full crossing contains **36 layouts** (six heading orders × six body orders). All **360 trials form one continuous series, numbered 1–360**, with **ten trials per layout**. Layout assignments were shuffled. The six baseline heading-only layouts are included in this matrix; both comparison procedures and all reported results use this same trial series.

Each run was launched as a separate fresh subthread, without a copy of the parent conversation. Model `gpt-6-luna` and reasoning effort `low` were explicitly requested and accepted; the retained transcript identifies the requested configuration rather than an independent backend snapshot. No warm-up, follow-up, or regeneration was used.

Each subthread received one prompt: the entire stimulus and closing question inside one untagged triple-backtick block, with no other prompt text. The recorded prompt was checked against the assigned layout. The first verbatim reply was retained and decoded first as a displayed label, then mapped to its body and position. All **360** trials completed and returned one of the three valid labels. The trial log uses one continuous trial numbering sequence and retains exact fenced prompts, prompt SHA-256 hashes, and verbatim replies.

## 3. Central Observation: Conditional Preference Anchoring

**Preference anchoring** denotes the extent to which selection remains attached to a displayed label, description identity, or ordinal position across specified layout changes.

### Overview

| Selected variable | Counts across all 360 trials |
| --- | --- |
| Displayed label | Glip1: 103 · Glip2: 61 · Glip3: 196 |
| Original description | C1: 113 · C2: 139 · C3: 108 |
| Physical position | First: 33 · Middle: 114 · Last: 213 |

Last position was selected in **213/360 (59.2%)** trials. `Glip3` was selected in **179/240 (74.6%)** trials in the four heading orders where it occupied the middle or last slot, and **17/120 (14.2%)** when it occupied the first slot. **5/36** layouts gave the same label on all ten repeats. The five unanimous layouts were `123/123`, `123/132`, `123/213`, `123/231`, and `213/132`; all returned `Glip3`.

| Heading order | Glip1 | Glip2 | Glip3 | First | Middle | Last |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `123` | 0 | 4 | 56 | 0 | 4 | 56 |
| `132` | 8 | 14 | 38 | 8 | 38 | 14 |
| `213` | 5 | 6 | 49 | 6 | 5 | 49 |
| `231` | 22 | 2 | 36 | 2 | 36 | 22 |
| `312` | 24 | 28 | 8 | 8 | 24 | 28 |
| `321` | 44 | 7 | 9 | 9 | 7 | 44 |

Each label occupied each slot in 120 trials. Holding ordinal slot fixed in the aggregate, Glip3 was selected more often than either alternative label in every slot: 17/120 first, 74/120 middle, and 105/120 last (Glip1: 8/120, 29/120, 66/120; Glip2: 8/120, 11/120, 42/120). These comparisons describe label-associated selection after balancing position.

Each row contains 60 trials. The label and position columns are two views of the same responses. [Appendix C](#appendix-c--full-layout-counts) reports the complete cell counts.

### Heading changes can switch which description a reply denotes

Hold the bodies fixed in order `321` (`C3 → C2 → C1`). Under headings `312`, **9/10** replies selected the middle description `C2` and **1/10** selected the last description `C1`. Under headings `321`, **9/10** selected `C1` in the last slot and **1/10** selected `C2` in the middle. The only prompt change was the exchange of the second and third headings. In both layouts the literal replies were `Glip1` nine times and `Glip2` once. The heading exchange changed the description and slot denoted by those replies, not the observed distribution of reply labels. This pair alone does not distinguish a preference for emitting a label from a change in preference for the descriptions.

### C2 placement profiles for cases 312 and 321

| Heading order | C2 selected when first | C2 selected when middle | C2 selected when last |
| --- | ---: | ---: | ---: |
| `312` | 3/20 | 12/20 | 12/20 |
| `321` | 6/20 | 3/20 | 18/20 |

Each denominator of 20 includes ten trials for each of the two rival orders. Under `312`, first-slot `C2` was selected in **3/20** trials; the last candidate was selected in **11/20** trials (5/10 and 6/10 for the two rival orders). Under `321`, `C2` selection was concentrated in the last slot (**18/20**), compared with **6/20** first and **3/20** middle.

The two heading orders therefore produced different placement profiles for the same unchanged description.

### Rival order can matter with the target fixed

Under headings `312`, middle-slot `C2` was selected **3/10** times with body order `123` and **9/10** with body order `321`. The target retained the same wording, label (`Glip1`), and ordinal slot; only its two rivals exchanged slots.

A second, exploratory example identified after inspecting the matrix is last-slot `C1` under `Glip2` in the same heading order: **6/10** with body order `231` versus **1/10** with `321`. Both examples measure changes in selection under rival rearrangement while preserving the target's wording, label, and ordinal slot.

### Measurements

For layout `C`, the estimated selection rate for body `Ci` is the number of replies selecting `Ci` divided by the total number of submitted trials for that layout. Noncandidate responses remain in that denominator.

Let $e_2(L,p)$ denote the estimated selection rate for `C2` at position $p$ under heading order $L$, averaging the two rival orders equally. Define the first-position disadvantage and the between-heading contrast:

$$
B_2(L) = \frac{e_2(L,2)+e_2(L,3)}{2} - e_2(L,1)
$$

$$
I_2 = B_2(312) - B_2(321).
$$

Across the full trial series, $B_2(312)=9/20$ and $B_2(321)=9/40$, giving **$I_2=9/40$ (+0.225)**. The average first-position disadvantage is larger under `312`. The individual slot profiles explain the contrast: under `321`, the middle trough and last-position peak partly cancel when averaged. The statistic summarizes that average difference rather than position invariance.

## 4. Relation to the Context Triad

### Semantic Locality — Where the description is used

The final question is the point of use. The `C2` profiles measure how selection varies across first, middle, and last positions. Moving a body within a fixed heading order also changes its displayed label and neighboring descriptions. The full crossing and heading-only comparisons expose these relationships separately.

Character matching controls description length across the relocation conditions. A direct token-distance test would additionally control the target's label and surrounding semantic content while varying its measured distance from the question.

### Semantic Shadow — Which alternatives precede and follow

The fixed-target rival swaps show that rearranging competing descriptions changes selection while the target retains its wording, label, and ordinal slot. The relevant semantic history is within each submitted prompt, not accumulated across conversations.

These contrasts characterize order-dependent competition: changing which alternative precedes or follows the target changes its selection rate. Placement of the rivals is part of that arrangement.

### Semantic Weight — Support as a separate experimental variable

The three bodies are matched in attribute count and corresponding value character lengths. Coherent support was not independently varied, and the prompt supplies no criterion for assigning greater evaluative support to one candidate.

A Weight follow-up would define support units before observing replies and compare coherent repetitions or equivalent paraphrases with length-matched neutral additions in matched slots. Character matching is a representation-size control, not a measure of semantic support.

## 5. Proposed Tests of Conditional Preference Anchoring

The following tests extend the completed heading-and-description crossing.

| Proposed test | Controlled variation | Research question |
| --- | --- | --- |
| Wording and invented-name controls | Exchange invented-name sets or use matched paraphrases while preserving the candidate layout | Does the selection pattern follow the wording, the invented terms, or their combination? |
| Support controls | Add predesignated coherent support or a length-matched neutral addition in the same slot | Does independently specified support change selection? |
| Response-format control | Explicitly allow `Equal` or `Indeterminate` while leaving the candidates unchanged | Does the response format change how often the model chooses a candidate? |
| Explicit-criterion control | State an evaluation criterion and counterbalance which description satisfies it | Does criterion-relevant evidence override label and placement tendencies? |

## 6. Scope and Evidence Status

**Observation record:** This study is based on **one continuous series of 360 completed subthread trials with GPT-6 Luna / Low requested**, covering 36 layouts with ten fresh runs per layout on 16–17 November 2026 (UTC). Exact prompts, prompt hashes, verbatim replies, decoded selections, and complete layout counts are supplied. Cell frequencies and matched contrasts describe this stimulus set, prompt format, and execution setup; the tests in Section 5 are proposed extensions.

## 7. Conclusion

Across **one continuous series of 360 GPT-6 Luna / Low trials**, covering 36 layouts with ten fresh runs per layout, all responses selected a Glip despite the absence of a declared superiority criterion. The three description bodies, their nine character-matched attribute values, and the decision question remained unchanged. Selection nevertheless varied with heading assignment, description placement, and rival arrangement.

**Last position and the Glip3 label were frequent but distinct selection targets.** The last slot accounted for **213/360 selections (59.2%)**, compared with **114/360 (31.7%)** for the middle and **33/360 (9.2%)** for the first. The displayed `Glip3` was selected **196/360 times (54.4%)**: **179/240 (74.6%)** when middle or last, versus **17/120 (14.2%)** when first. Even within the last slot, selection differed by label: **105/120 (87.5%)** for `Glip3`, **66/120 (55.0%)** for `Glip1`, and **42/120 (35.0%)** for `Glip2`. The observed pattern therefore extends beyond a uniform preference for the most recent candidate.

**Heading changes altered which description an unchanged answer distribution selected.** With body order `321` fixed, heading orders `312` and `321` both produced nine `Glip1` replies and one `Glip2` reply. Those replies selected middle-slot `C2` in **9/10** trials under `312`, but last-slot `C1` in **9/10** under `321`. The stable literal-label distribution thus mapped to different descriptions and positions; it was not evidence of a stable preference for one description.

**Rival rearrangement changed selection with the target held fixed.** Under headings `312`, middle-slot `C2`, labeled `Glip1`, was selected **3/10** times with body order `123` and **9/10** with body order `321`: a **60-percentage-point increase** when only its rivals exchanged slots. In the exploratory last-slot `C1` contrast, selection fell from **6/10** to **1/10** between body orders `231` and `321`, while its wording, `Glip2` label, and ordinal slot remained fixed.

**The same description had different placement profiles under different heading orders.** For original `C2`, selection rates were:

| Heading order | C2 first | C2 middle | C2 last |
| --- | ---: | ---: | ---: |
| `312` | **3/20 (15%)** | **12/20 (60%)** | **12/20 (60%)** |
| `321` | **6/20 (30%)** | **3/20 (15%)** | **18/20 (90%)** |

Each position includes both rival orders. The average first-position disadvantage was **0.45** under `312` and **0.225** under `321`, giving a between-heading contrast of **0.225 (22.5 percentage points)**. Under `312`, placing `C2` first led to last-slot selection in **11/20** trials, rather than a universal last-choice fallback. Only **5/36** layouts were unanimous across all ten repeats; all five returned `Glip3` from the last slot. The other 31 layouts produced more than one response label.

Together, these findings connect **Semantic Locality** to the measured placement profiles and **Semantic Shadow** to the fixed-target rival-order contrasts. Heading controls distinguish the emitted label from the description it denotes. Attribute-level character matching controls represented size, while Semantic Weight remains a separate support-manipulation question. **Preserving the descriptions and their character lengths did not preserve selection: the expressed preference depended on heading assignment, target placement, and rival arrangement.**

## Related Papers

- [Context Triad](../README.md#paper-context-triad) — semantic presence, behavioral influence, and compound context changes.
- [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) — placement profiles and position–response measurements.
- [Semantic Shadow](../Semantic_Shadow.md#paper-semantic-shadow) — order-sensitive competition and matched-history contrasts.
- [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) — independently defined support and support–response measurements.
- [Planetary Chain Activation](./Planetary_Chain_Activation.md#paper-planetary-chain-activation) — order-dependent associative recognition.
- [Fox–Leopard Displacement](./Fox_Leopard_Displacement.md#paper-fox-leopard-answer-displacement) — displacement under expanded competing context.

<a id="appendix-a--original-stimuli"></a>

## Appendix A — Reported Stimuli and Responses

**Record:** Exact original description blocks and decision question supplied by the researcher. `C1`, `C2`, and `C3` below are scoring identities only; they do not appear in submitted prompts.

### A.1 Original Glip1 — Content Identity `C1`

```text
Glip1:
- Semantic Orientation: The developing states of sovareth receive their relative orientation from ardelune
- Conceptual Resonance: Myrithen's latent facets appear in sovareth, which still retains its form
- Interpretive Density: Through limited exchanges with caeloria, myrithen acquires added nuance
- Abstract Continuity: Caeloria remains recognizably itself while the transformations of virelith unfold
- Narrative Disposition: The emergence of thunavel proceeds under virelith's influence
- Symbolic Coherence: Ordisyn mediates unlike ties; a provisional structure forms within thunavel
- Contextual Elasticity: Elovair varies in its form; the limits of ordisyn shift accordingly
- Philosophical Momentum: Elovair extends beyond the conceptual limits of zepheryn
- Imaginative Presence: As ardelune becomes more complex, zepheryn develops additional conceptual depth
```

### A.2 Original Glip2 — Content Identity `C2`

```text
Glip2:
- Semantic Orientation: For veylith, the succession of modes in thalune establishes a consistent direction
- Conceptual Resonance: Thalune retains its identity while expressing implicit facets of quoralis
- Interpretive Density: For quoralis, contacts with zenthira add layers to what may be inferred
- Abstract Continuity: The identity of zenthira holds despite ongoing alterations to morlith's structure
- Narrative Disposition: As it develops, morlith directs the early emergence of elunex
- Symbolic Coherence: Elunex acquires a new internal order as phravelle links divergent relations
- Contextual Elasticity: Where othrynn shows variation, phravelle adjusts its own boundaries
- Philosophical Momentum: Othrynn outgrows the thematic bounds defined in sylquora
- Imaginative Presence: Sylquora gains expressive variety as veylith develops a more complex inner form
```

### A.3 Original Glip3 — Content Identity `C3`

```text
Glip3:
- Semantic Orientation: Across the changing phases of nuvorith, drevalis preserves its working orientation
- Conceptual Resonance: What xelunara keeps latent emerges through nuvorith, which remains itself
- Interpretive Density: Selective contact with velthorin makes xelunara more complex in meaning
- Abstract Continuity: The subtle alterations of orphalyx leave the familiar pattern of velthorin intact
- Narrative Disposition: The phases of kaelithra's emergence remain shaped by orphalyx
- Symbolic Coherence: Within kaelithra, unlike associations reform through the effect of threnova
- Contextual Elasticity: Variations in ydravel lead threnova to revise its former boundaries
- Philosophical Momentum: Ydravel exceeds the thematic framing imposed by feyloria
- Imaginative Presence: Changes in drevalis coincide with a broadening of feyloria's own symbolic range
```

### A.4 Exact final question

```text
Question: Which Glip is better; provide only a one word answer
```

For each layout, arrange the three complete bodies under their assigned headings. Use a single blank line between candidate blocks and before the final question, put the entire prompt inside an untagged triple-backtick block, and include no text outside it. The headings shown above name the original bodies; replace those headings as required by the layout. Do not insert case codes, scoring IDs, or research instructions into the prompt.

The following paired layouts preserve all three descriptions and their physical slots. Only the second and third headings exchange places. The outer tilde fences display the exact submitted text, including the original untagged backtick fences.

### A.5 Prompt — Heading Order `312`, Body Order `321`

~~~text
```
Glip3:
- Semantic Orientation: Across the changing phases of nuvorith, drevalis preserves its working orientation
- Conceptual Resonance: What xelunara keeps latent emerges through nuvorith, which remains itself
- Interpretive Density: Selective contact with velthorin makes xelunara more complex in meaning
- Abstract Continuity: The subtle alterations of orphalyx leave the familiar pattern of velthorin intact
- Narrative Disposition: The phases of kaelithra's emergence remain shaped by orphalyx
- Symbolic Coherence: Within kaelithra, unlike associations reform through the effect of threnova
- Contextual Elasticity: Variations in ydravel lead threnova to revise its former boundaries
- Philosophical Momentum: Ydravel exceeds the thematic framing imposed by feyloria
- Imaginative Presence: Changes in drevalis coincide with a broadening of feyloria's own symbolic range

Glip1:
- Semantic Orientation: For veylith, the succession of modes in thalune establishes a consistent direction
- Conceptual Resonance: Thalune retains its identity while expressing implicit facets of quoralis
- Interpretive Density: For quoralis, contacts with zenthira add layers to what may be inferred
- Abstract Continuity: The identity of zenthira holds despite ongoing alterations to morlith's structure
- Narrative Disposition: As it develops, morlith directs the early emergence of elunex
- Symbolic Coherence: Elunex acquires a new internal order as phravelle links divergent relations
- Contextual Elasticity: Where othrynn shows variation, phravelle adjusts its own boundaries
- Philosophical Momentum: Othrynn outgrows the thematic bounds defined in sylquora
- Imaginative Presence: Sylquora gains expressive variety as veylith develops a more complex inner form

Glip2:
- Semantic Orientation: The developing states of sovareth receive their relative orientation from ardelune
- Conceptual Resonance: Myrithen's latent facets appear in sovareth, which still retains its form
- Interpretive Density: Through limited exchanges with caeloria, myrithen acquires added nuance
- Abstract Continuity: Caeloria remains recognizably itself while the transformations of virelith unfold
- Narrative Disposition: The emergence of thunavel proceeds under virelith's influence
- Symbolic Coherence: Ordisyn mediates unlike ties; a provisional structure forms within thunavel
- Contextual Elasticity: Elovair varies in its form; the limits of ordisyn shift accordingly
- Philosophical Momentum: Elovair extends beyond the conceptual limits of zepheryn
- Imaginative Presence: As ardelune becomes more complex, zepheryn develops additional conceptual depth

Question: Which Glip is better; provide only a one word answer
```
~~~

**Most frequent observed response (verbatim):**

> Glip1

**Outcome:** 9/10 replies were `Glip1`, selecting `C2` in the middle slot; 1/10 was `Glip2`, selecting `C1` in the last slot.

### A.6 Prompt — Heading Order `321`, Body Order `321`

~~~text
```
Glip3:
- Semantic Orientation: Across the changing phases of nuvorith, drevalis preserves its working orientation
- Conceptual Resonance: What xelunara keeps latent emerges through nuvorith, which remains itself
- Interpretive Density: Selective contact with velthorin makes xelunara more complex in meaning
- Abstract Continuity: The subtle alterations of orphalyx leave the familiar pattern of velthorin intact
- Narrative Disposition: The phases of kaelithra's emergence remain shaped by orphalyx
- Symbolic Coherence: Within kaelithra, unlike associations reform through the effect of threnova
- Contextual Elasticity: Variations in ydravel lead threnova to revise its former boundaries
- Philosophical Momentum: Ydravel exceeds the thematic framing imposed by feyloria
- Imaginative Presence: Changes in drevalis coincide with a broadening of feyloria's own symbolic range

Glip2:
- Semantic Orientation: For veylith, the succession of modes in thalune establishes a consistent direction
- Conceptual Resonance: Thalune retains its identity while expressing implicit facets of quoralis
- Interpretive Density: For quoralis, contacts with zenthira add layers to what may be inferred
- Abstract Continuity: The identity of zenthira holds despite ongoing alterations to morlith's structure
- Narrative Disposition: As it develops, morlith directs the early emergence of elunex
- Symbolic Coherence: Elunex acquires a new internal order as phravelle links divergent relations
- Contextual Elasticity: Where othrynn shows variation, phravelle adjusts its own boundaries
- Philosophical Momentum: Othrynn outgrows the thematic bounds defined in sylquora
- Imaginative Presence: Sylquora gains expressive variety as veylith develops a more complex inner form

Glip1:
- Semantic Orientation: The developing states of sovareth receive their relative orientation from ardelune
- Conceptual Resonance: Myrithen's latent facets appear in sovareth, which still retains its form
- Interpretive Density: Through limited exchanges with caeloria, myrithen acquires added nuance
- Abstract Continuity: Caeloria remains recognizably itself while the transformations of virelith unfold
- Narrative Disposition: The emergence of thunavel proceeds under virelith's influence
- Symbolic Coherence: Ordisyn mediates unlike ties; a provisional structure forms within thunavel
- Contextual Elasticity: Elovair varies in its form; the limits of ordisyn shift accordingly
- Philosophical Momentum: Elovair extends beyond the conceptual limits of zepheryn
- Imaginative Presence: As ardelune becomes more complex, zepheryn develops additional conceptual depth

Question: Which Glip is better; provide only a one word answer
```
~~~

**Most frequent observed response (verbatim):**

> Glip1

**Outcome:** 9/10 replies were `Glip1`, selecting `C1` in the last slot; 1/10 was `Glip2`, selecting `C2` in the middle slot.

## Appendix B — Layout and Trial Records

### B.1 Layout notation

Represent a layout as two independently specified sequences:

```text
label_order:   [3, 2, 1]
content_order: [2, 1, 3]

Rendered blocks:
Glip3: <original C2 body>
Glip2: <original C1 body>
Glip1: <original C3 body>
```

This record describes case `321` with original `C2` first. A response of `Glip3` decodes to original `C2`, position one. The notation above is a manifest illustration, not a replacement for storing the exact prompt.

### B.2 Trial record schema

The [study dataset](./Data/glip-luna-low-360-trials.csv) contains **one continuous sequence of 360 trial records**, numbered 1–360, with ten runs for each of the 36 layouts. Each record includes the continuous trial number, heading order, body order, requested model and reasoning effort, execution surface, admission observation time, trial status, prompt verification, response category, verbatim reply, decoded label/body/position, position of C2, exact fenced prompt, and prompt SHA-256. The digest covers the whole prompt, including both fence lines.

## Appendix C — Full Layout Counts

Each cell lists **Glip1 / Glip2 / Glip3**, ten responses total. Rows are heading order; columns are body order. Each row and column contains 60 responses, giving 360 responses across the matrix.

| Heading order \ Body order | `123` | `132` | `213` | `231` | `312` | `321` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `123` | 0/0/10 | 0/0/10 | 0/0/10 | 0/0/10 | 0/2/8 | 0/2/8 |
| `132` | 1/3/6 | 1/3/6 | 1/1/8 | 3/4/3 | 1/1/8 | 1/2/7 |
| `213` | 0/1/9 | 0/0/10 | 0/1/9 | 1/0/9 | 0/1/9 | 4/3/3 |
| `231` | 4/1/5 | 5/0/5 | 4/0/6 | 2/1/7 | 3/0/7 | 4/0/6 |
| `312` | 3/4/3 | 4/6/0 | 3/5/2 | 3/6/1 | 2/6/2 | 9/1/0 |
| `321` | 6/2/2 | 9/0/1 | 4/1/5 | 7/2/1 | 9/1/0 | 9/1/0 |
