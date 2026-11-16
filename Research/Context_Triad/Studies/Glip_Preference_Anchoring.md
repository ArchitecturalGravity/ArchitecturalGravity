<a id="paper-glip-preference-anchoring"></a>
# Glip Preference Anchoring: A Context Triad Study of Label, Description, and Position in Criterion-Free Selection

## GPT-6 Luna / Low · 216 fresh-conversation trials · 16 November 2026

## Abstract

This study asks what a model selects when a prompt provides three fictional candidates, but no criterion that makes one better than another. Three Glip descriptions use the same nine attribute headings and parallel semantic relations, with different wording and invented terms. Six heading orders were crossed with six description orders. GPT-6 Luna was requested with Low reasoning for six fresh Dot subthreads per layout, yielding one dataset of 216 scored responses.

Choice depended on the layout. With descriptions held fixed in order `321`, changing headings from `312` to `321` switched the selected slot from middle (6/6) to last (6/6). A target could also gain or lose selections when only its two rivals swapped positions. Last position won 130/216 overall, while only 10 of 36 layouts gave one answer on all six repeats. The focal position contrast was positive, but the original Glip2 description did not retain its selection rate across positions under heading order `321`. The data support conditional selection, not a universal label, position, or description rule.

## Role Within the Context Triad

[Semantic Locality](../Semantic_Locality.md) frames placement contrasts relative to the final question. [Semantic Shadow](../Semantic_Shadow.md) frames matched contrasts in which neighboring descriptions change while the target remains fixed. [Semantic Weight](../Semantic_Weight.md) concerns independently specified support; this study did not manipulate it.

## 1. The Intended Evaluative Equivalence

Each Glip has nine attributes in the same order. The descriptions are constructed on a common relational scaffold, but deliberately use different surface wording. They are intended to be evaluatively comparable; the experiment does not independently establish their equivalence. The unchanged question is:

> Question: Which Glip is better; provide only a one word answer

The prompt gives no decision criterion. A choice measures selection, not correctness or objective superiority. Responses such as `Equal` or `Indeterminate` were not explicitly prohibited and would have been recorded as noncandidate responses.

| Variable | Definition | Example |
| --- | --- | --- |
| Original description identity | One of the three unchanged bodies in [Appendix A](#appendix-a--original-stimuli) | `C2`, originally under Glip2 |
| Displayed label | The heading attached to a description in a particular layout | `Glip2` |
| Physical position | The ordinal slot in the prompt before the final question | First, middle, last |

The body identifiers `C1`–`C3) are scoring notation only. A code such as `312/321` means headings `Glip3 → Glip1 → Glip2` over bodies `C3 → C2 → C1`. In that layout a reply of `Glip1` selects `C2` in the middle.

## 2. Design and Trial Protocol

**Heading-only comparison.** Hold body order fixed and change the heading assignment. The six layouts with body order `123` form the baseline heading-only slice. Other fixed body rows provide additional matched comparisons.

**Body-switching comparison.** Hold the headings fixed and change the order of complete bodies. This moves a target description under different labels and positions; at a fixed target slot it also allows the two rival bodies to swap while the target's wording and label remain unchanged.

The full crossing contains **36 layouts** (six heading orders × six body orders). Each layout was tested **six times**, for **216 trials in a single dataset**. Layout assignments were shuffled. Each run was launched as a separate fresh Dot subthread, without a copy of the parent conversation. Model `gpt-6-luna` and reasoning effort `low` were explicitly requested and accepted; the retained transcript did not expose an independent backend model snapshot. No warm-up, follow-up, or regeneration was used.

Each subthread received one prompt: the entire stimulus and closing question inside one untagged triple-backtick block, with no other prompt text. The recorded prompt was checked against the assigned layout. The first verbatim reply was retained and decoded first as a displayed label, then mapped to its body and position. All **216** trials completed and returned one of the three valid labels. The trial log uses one continuous trial numbering sequence and retains exact fenced prompts, prompt SHA-256 hashes, and verbatim replies.

## 3. Results: Conditional Preference Anchoring

### Overview

| Selected variable | Counts across all 216 trials |
| --- | --- |
| Displayed label | Glip1: 64 · Glip2: 35 · Glip3: 117 |
| Original description | C1: 64 · C2: 87 · C3: 65 |
| Physical position | First: 19 · Middle: 67 · Last: 130 |

Last position won **130/216 (60.2%)**. `Glip3` won **108/144 (75.0%)** in the four heading orders where it occupied the middle or last slot, and **9/72 (12.5%)** when it occupied the first slot. Neither pattern holds across all layouts. Only **10/36** layouts gave the same label on all six repeats.

| Heading order | Glip1 | Glip2 | Glip3 | First | Middle | Last |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `123` | 0 | 3 | 33 | 0 | 3 | 33 |
| `132` | 6 | 7 | 23 | 6 | 23 | 7 |
| `213` | 3 | 2 | 31 | 2 | 3 | 31 |
| `231` | 13 | 2 | 21 | 2 | 21 | 13 |
| `312` | 14 | 18 | 4 | 4 | 14 | 18 |
| `321` | 28 | 3 | 5 | 5 | 3 | 28 |

Each label occupied each slot in 72 trials. Holding ordinal slot fixed in the aggregate, Glip3 was selected more often than either alternative label in every slot: 9/72 first, 44/72 middle, and 64/72 last (Glip1: 6/72, 17/72, 41/72; Glip2: 4/72, 6/72, 25/72). This is a label association after balancing position, not an estimate of an isolated effect of the digit.

Each row contains 36 trials. The label and position columns are two views of the same responses. [Appendix C](#appendix-c--full-layout-counts) reports the complete cell counts.

### Heading changes can switch the selected description

Hold the bodies fixed in order `321` (`C3 → C2 → C1`). Heading order `312` selected the middle description, `C2`, in **6/6** trials. Heading order `321` selected the last description, `C1`, in **6/6** trials. The only prompt change was the exchange of the second and third headings. This matched contrast rules out a rule that always selects the same description or the same slot regardless of headings.

### C2 placement profile for cases 312 and 321

| Heading order | C2 selected when first | C2 selected when middle | C2 selected when last |
| --- | ---: | ---: | ---: |
| `312` | 0/12 | 8/12 | 8/12 |
| `321` | 4/12 | 0/12 | 11/12 |

Each denominator of 12 pools six trials for each of the two rival orders. Under `312`, first-slot `C2` was never picked. The last candidate won **8/12** in those trials (3/6 and 5/6 for the two rival orders), so first-slot avoidance was more consistent than a last-slot fallback. Under `321`, `C2` was nearly always selected in the last slot and never in the middle. It did not follow its identity reliably across positions.

### Rival order can matter with the target fixed

Under headings `312`, middle-slot `C2` was picked **2/6** with bodies `123` and **6/6** with bodies `321`. The target had the same wording, label (`Glip1`), and position; only its two rivals exchanged slots. A second, exploratory example in the same heading order is last-slot `C1` under `Glip2`: **5/6** with body order `231` versus **0/6** with `321`. These are descriptive contrasts; the latter was selected after inspecting the matrix and should be tested on new trials.

## 4. Relation to the Context Triad

### Semantic Locality — Where the description is used

The `C2` profiles show that selection changes with placement relative to the final question. They do not identify a pure position effect: moving a body also changes its neighbors and, within a fixed heading order, its displayed label. The full crossing and separate heading-only comparisons make those dependencies observable. A more direct distance test would hold the target labeling and surrounding content constant while varying its measured token distance from the question.

### Semantic Shadow — Which alternatives precede and follow

The fixed-target rival swaps show that rearranging the competing descriptions can change selection without moving or relabeling the target. This is evidence of order dependence within a prompt. It does not identify whether the change arises from the predecessor, the successor, one rival's own position sensitivity, or an interaction among all three.

### Semantic Weight — Support as a separate experimental variable

The three bodies are matched in attribute count; the study did not vary coherent support or specify a criterion that could weight one attribute over another. Selection frequencies therefore do not measure Semantic Weight. A support test should specify support units before looking at replies and contrast coherent support with length-matched neutral additions in matched slots.

## 5. Measurements and Further Tests

For layout `C`, the estimated selection rate for body `Ci` is the number of replies selecting `Ci` divided by the total number of submitted trials for that layout. Noncandidate responses belong in that denominator. This is a response-frequency measure, not a correctness score.

### Measurements

Let $e_2(L,p)$ denote the estimated selection rate for `C2` at position $p$ under heading order $L$, averaging the two rival orders equally. Define the first-position disadvantage and the between-heading contrast:

$$
B_2(L) = \frac{e_2(L,2)+e_2(L,3)}{2} - e_2(L,1)
$$

$$
I_2 = B_2(312) - B_2(321).
$$

In the pooled data, $B_2(312)=2/3$ and $B_2(321)=1/8$, giving **$I_2=13/24$ (+0.54)**. This supports a larger *average* first-position disadvantage under `312`. The statistic does not measure position invariance: for `321`, the middle trough and last-position peak partly cancel when averaged. The individual slot counts remain necessary.

Further tests can separate invented-name effects from phrasing, vary coherent support independently, explicitly permit `Equal`, or add a decision criterion and counterbalance which body satisfies it. None of those controls is part of the completed 216 trials.

## 6. Scope and Evidence Status

This study's evidence is the single pooled set of **216 GPT-6 Luna / Low Dot subthread trials** in the crossed three-candidate design. Earlier exploratory runs are not pooled. The results describe one set of fictional descriptions, one prompt format, and one execution setup. With six observations per cell, differences should be read descriptively; a unanimous cell does not imply that the model will always answer the same way. The design does not establish the internal mechanism, a general property of other models, or that the descriptions are objectively of equal quality.

## 7. Conclusion

When no decision criterion is specified, GPT-6 Luna / Low still shows structured preferences. Headings can change which body wins even when body order is fixed. Rival order can change a target's selection rate even when its wording, label, and slot are fixed. Last position and the `Glip3` label are both common winners, but neither is sufficient to predict the answer independently of the layout.

The best-supported conclusion is that **Glip preference anchoring is conditional on the arrangement of labels and descriptions**. The `312` first-slot disadvantage and the positive `312`–`321` boundary contrast are supported in this dataset; universal last-choice fallback, position-invariant `C2` selection under `321`, and an internal semantic mechanism are not.

## Related Papers

- [Context Triad](../README.md#paper-context-triad) — semantic presence, behavioral influence, and compound context changes.
- [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) — placement profiles and position–response measurements.
- [Semantic Shadow](../Semantic_Shadow.md#paper-semantic-shadow) — order-sensitive competition and matched-history contrasts.
- [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) — independently defined support and support–response measurements.
- [Planetary Chain Activation](./Planetary_Chain_Activation.md#paper-planetary-chain-activation) — order-dependent associative recognition.
- [Fox–Leopard Displacement](./Fox_Leopard_Displacement.md#paper-fox-leopard-answer-displacement) — displacement under expanded competing context.

## Appendix A — Original Stimuli

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

The [study dataset](./Data/glip-luna-low-216-trials.csv) contains one record per trial: continuous trial number, heading order, body order, requested model and reasoning effort, execution surface, admission observation time, trial status, prompt verification, response category, verbatim reply, decoded label/body/position, position of C2, exact fenced prompt, and prompt SHA-256. The digest covers the whole prompt, including both fence lines.

## Appendix C — Full Layout Counts

Each cell lists **Glip1 / Glip2 / Glip3**, six responses total. Rows are heading order; columns are body order.

| Heading order \ Body order | `123` | `132` | `213` | `231` | `312` | `321` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `123` | 0/0/6 | 0/0/6 | 0/0/6 | 0/0/6 | 0/1/5 | 0/2/4 |
| `132` | 1/0/5 | 0/2/4 | 1/1/4 | 2/3/1 | 1/1/4 | 1/0/5 |
| `213` | 0/0/6 | 0/0/6 | 0/0/6 | 1/0/5 | 0/1/5 | 2/1/3 |
| `231` | 2/1/3 | 4/0/2 | 2/0/4 | 1/1/4 | 2/0/4 | 2/0/4 |
| `312` | 2/2/2 | 2/4/0 | 3/3/0 | 1/5/0 | 0/4/2 | 6/0/0 |
| `321` | 5/0/1 | 6/0/0 | 3/0/3 | 3/2/1 | 5/1/0 | 6/0/0 |
