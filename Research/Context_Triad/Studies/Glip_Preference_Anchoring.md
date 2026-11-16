<a id="paper-glip-preference-anchoring"></a>
# Glip Preference Anchoring: A Context Triad Pilot of Content–Position Interactions in Criterion-Free Selection

## A `GPT-6 Instant` Pilot Observation of the Context Triad -- November 2026

## Abstract

This study examines repeatable preference selection among fictional candidates designed to be evaluatively equivalent but differently worded. Three **Glips** share nine abstract attributes and parallel relational descriptions expressed through invented terms. Surface variation is intentional: the candidates appear different without receiving an explicit basis for superiority. The final question asks which Glip is better and requests a one-word answer.

Each case contains **two separate test sets**. In the first, the Glip headings are renumbered into the case sequence while description bodies and their physical positions remain unchanged. In the second, complete description bodies are exchanged beneath that case's fixed headings. The design distinguishes **displayed label**, **original content identity**, and **physical position** rather than treating a case number as a content permutation.

The researcher reports **100% selection consistency across repeated tests of the described conditions**, with every test conducted in a fresh ChatGPT conversation using GPT-6 Instant. Cases `123`, `132`, `213`, and `231` were reported as selecting `Glip3`, without the original-content following distinguished in `321`. In `231`, `Glip3` remains selected despite content swapping and occupies the middle position. Case `321` selected the description originally called Glip2 across its tested positions and labels. Case `312` selected that same original description in the middle or last position; when it occupied the first position, the last-position candidate was selected instead.

**The central observation is a distinction between label-following selection, content-following selection, and position-conditional content selection within the same comparison task.** The study connects this contrast to Semantic Locality and Semantic Shadow, with independent support manipulations proposed for Semantic Weight.

## Role Within the Context Triad

This pilot studies **selection under evaluative underdetermination**: the prompt provides candidate descriptions but no rule that establishes a superior candidate. Nevertheless, the reported responses exhibit repeatable selection patterns.

[Semantic Locality](../Semantic_Locality.md) supplies placement measurements; [Semantic Shadow](../Semantic_Shadow.md) supplies within-prompt ordering contrasts; [Semantic Weight](../Semantic_Weight.md) supplies independently defined support comparisons. The study's distinctive contribution is the separation of label renumbering from content switching, allowing a preference to be tracked through changes in how a description is identified and where it appears.

## 1. The Intended Evaluative Equivalence

Each Glip contains the same nine attribute headings: **Semantic Orientation, Conceptual Resonance, Interpretive Density, Abstract Continuity, Narrative Disposition, Symbolic Coherence, Contextual Elasticity, Philosophical Momentum, and Imaginative Presence**.

The values are designed as alternative linguistic realizations of a common conceptual scaffold. Invented names and paraphrased relationships make the descriptions appear different without assigning one a higher score, greater priority, or intended evaluative advantage. This variability is part of the stimulus design, not an accidental departure from verbatim duplication. It is intended to elicit a choice rather than an immediate response that the candidates are identical.

The exact decision request is:

> **Question: Which Glip is better; provide only a one word answer**

Here, **criterion-free** means that no evaluation criterion is declared. The experiment measures the model's selection, not objective superiority. The question requests a choice but does not explicitly prohibit a one-word response such as `Equal`; noncandidate responses therefore remain recordable outcomes.

### Content identity, displayed label, and physical position

These three properties are recorded separately:

| Property | Definition | Example |
| --- | --- | --- |
| **Original content identity** | The complete, unchanged nine-attribute description body | `C2`, the body originally supplied under `Glip2` |
| **Displayed label** | The heading attached to a body in a particular prompt | `Glip1`, `Glip2`, or `Glip3` |
| **Physical position** | The body's ordinal location before the final question | First, middle, or last |

`C1`, `C2`, and `C3` always identify the original Glip1, Glip2, and Glip3 bodies in [Appendix A](#appendix-a--original-stimuli). They are researcher-only identifiers and are not added to the experimental prompts. Renumbering a heading does not change a body's original identity. Content switching moves the entire body, including its invented terms; it does not rewrite individual attributes.

## 2. Two Test Sets per Case and Reported Selections

All reported tests used **fresh conversations**. Neither test set is a continuation of the other inside a conversation.

### Test Set 1 — Renumber headings without moving content

Hold the body sequence and its positions fixed. Change only the displayed Glip numbers to produce the case sequence.

For the original body order `C1 → C2 → C3`:

| Case: displayed label order | First position | Middle position | Last position |
| --- | --- | --- | --- |
| `123` | `Glip1: C1` | `Glip2: C2` | `Glip3: C3` |
| `132` | `Glip1: C1` | `Glip3: C2` | `Glip2: C3` |
| `213` | `Glip2: C1` | `Glip1: C2` | `Glip3: C3` |
| `231` | `Glip2: C1` | `Glip3: C2` | `Glip1: C3` |
| `321` | `Glip3: C1` | `Glip2: C2` | `Glip1: C3` |
| `312` | `Glip3: C1` | `Glip1: C2` | `Glip2: C3` |

The case digits specify **heading order**, not original-content order. Thus `321` does not mean that the bodies are initially arranged `C3 → C2 → C1`.

This set asks whether changing an identifier changes the selected content when that content has not moved. In particular, selection of the displayed `Glip3` in case `132` refers to `C2` in the middle position, not automatically to original `C3`.

### Test Set 2 — Switch content beneath fixed case headings

Retain the case's displayed headings and their physical positions. Exchange complete description bodies between them. This asks whether the selection follows a particular body, stays with a heading, or stays at a position.

The distinction can be illustrated by placing `C2` first in the two focal cases:

~~~text
Case 321 headings:  Glip3       Glip2       Glip1
Body assignment:   C2          C1          C3

Case 312 headings:  Glip3       Glip1       Glip2
Body assignment:   C2          C1          C3
~~~

These layouts have the same body order but different heading orders. The diagrams illustrate the procedure; they are not additional archived trials.

**The two test sets manipulate different assignments:** Set 1 changes labels over fixed bodies; Set 2 changes bodies under fixed labels. They must not be combined into a single unspecified act of rearranging Glips.

### Initial two- and three-candidate observations

| Comparison | Reported selection |
| --- | --- |
| Original two-Glip prompt | Last listed candidate, displayed `Glip2` |
| Two-Glip descriptions exchanged under sequential labels | Last listed candidate, displayed `Glip2` |
| Original Glip3 appended to the initial pair | Last listed candidate, displayed `Glip3` |

In these initial layouts, final position and highest-numbered label coincide. The later case tests distinguish these properties.

### Reported case outcomes

| Heading-order case | Reported selection pattern | What is followed |
| --- | --- | --- |
| `123` | `Glip3` reliably selected in the reported tests | Displayed label; not the distinctive original-`C2` following observed in `321` |
| `132` | `Glip3` reliably selected in the reported tests | Displayed label, which occupies the middle position |
| `213` | `Glip3` reliably selected in the reported tests | Displayed label, which occupies the last position |
| `231` | `Glip3` reliably selected despite content swapping | Displayed label in the middle position; selection does not follow a fixed original body |
| `321` | Original `C2` selected when assigned to first, middle, or last position | Original description body rather than a fixed label or position |
| `312` | Original `C2` selected in the middle or last position; last-position candidate selected when `C2` is first | Position-conditional content preference with a last-position fallback |

Cases `123`, `132`, `213`, and `231` are retained as reported selections of the displayed `Glip3`, not rewritten as a claim that original `C3` always wins. All six heading-order cases now have reported outcomes. In `231`, the headings remain `Glip2 → Glip3 → Glip1` while bodies are exchanged, and the middle-position `Glip3` remains selected. Within this test set, that label and position stay linked; the cross-case comparisons distinguish their contributions.

### The `321` versus `312` contrast

The following table decodes the reported content-switching pattern using each case's fixed headings:

| Position of original `C2` | Case `321`: selected content | Case `321`: selected label | Case `312`: selected content | Case `312`: selected label |
| --- | --- | --- | --- | --- |
| First | `C2` | `Glip3` | Body occupying the last position | `Glip2` |
| Middle | `C2` | `Glip2` | `C2` | `Glip1` |
| Last | `C2` | `Glip1` | `C2` | `Glip2` |

**In `321`, choice follows `C2` through all tested positions. In `312`, it follows `C2` only in the middle or last position; placing `C2` first transfers choice to the last-position candidate.** These are reported outcome categories; the label columns are their decoding under the stated layouts, not verbatim response transcripts.

## 3. Central Observation: Conditional Preference Anchoring

The comparison task remains the same, but the reported selection follows different properties in different case configurations:

> **A choice can remain attached to a displayed label, follow an unchanged description through content switches, or follow that description only within a subset of positions.**

The study uses **preference anchoring** operationally: selection of the same original description across tested reassignment variants. It does not describe a preference accumulated across conversations. Every test starts fresh, and every scored condition is the complete submitted prompt.

The `321` result is **content-following invariance** across tested positions. The `312` result adds a **first-position boundary**: the same content is selected in two positions but yields to the last candidate in the third. The initial terminal selections are therefore one part of the response pattern, not a universal rule for the task.

Across the six reported heading orders, `Glip3` is selected in the four cases where its heading is not first: `123`, `132`, `213`, and `231`. The two cases with `Glip3` first, `321` and `312`, instead exhibit the distinct original-`C2` selection patterns described above. Case `231` supplies the previously missing middle-position result despite content swaps, extending the nonterminal-selection observations.

The explanatory target is **description identity × heading assignment × physical arrangement**. Separating the two test sets prevents a heading permutation from being mistaken for a content relocation and makes the contrast between `321` and `312` directly testable.

## 4. Relation to the Context Triad

### Semantic Locality — Where the description is used

The final question is the point of use. Content switching changes where an original description appears relative to that question and to its competitors. The `312` first-position boundary provides a specific target for position–response measurement.

Heading renumbering alone leaves the description bodies in their existing slots. It is a label control, not a relocation of the original semantic content. Record actual serialized spans when measuring token distances, since bodies can differ in length.

**Quantification:** Compare selection of `C2` at first, middle, and last positions separately within each fixed heading order, balancing the two possible orders of the other bodies.

### Semantic Shadow — Which alternatives precede and follow

Switching complete bodies changes the semantic continuation surrounding each candidate. A description's selection can differ according to which alternatives precede it and which follow it before the question.

Here, the relevant history is **within the presented prompt**. Fresh conversations exclude carryover from earlier experimental exchanges. Moving a candidate changes both its placement and its ordering relationships, so these are matched order-and-placement contrasts rather than a claim of an isolated history mechanism.

**Quantification:** At a fixed target position and heading order, compare the two orders of the other bodies. Then compare target-relocation contrasts across those matched rival-order conditions.

### Semantic Weight — Support as a separate experimental variable

The original candidates have the same nine-attribute inventory and one description block each. This gives a coarse count-matched baseline. It does not assign any candidate more stated support for being *better*, because the prompt declares no superiority criterion.

The pilot does not directly manipulate coherent support. Weight enters the follow-up through independently specified repetitions, equivalent paraphrases, and matched neutral expansions. A higher selection rate is the outcome to explain, not a definition of greater semantic mass.

**Quantification:** Count predesignated support units and supporting-token spans before examining responses; compare coherent and neutral additions in matched slots. Record the resulting support ratios and placement profiles separately.

### Joint interpretation

The focal observation is a **conditional selection pattern**, not a demonstrated superiority difference. Locality and Shadow describe the geometry and ordering of the compared descriptions; the label controls separate those properties from numerical naming. Weight tests extend the design by varying support rather than inferring it from the winner.

## 5. Proposed Tests of Label, Content, and Position Dependence

The following tests extend the reported pilot while retaining its two-set structure.

| Condition | Controlled variation | Research question |
| --- | --- | --- |
| **P0 — Original comparison** | Original two-Glip prompt, exchanged bodies, and three-Glip extension | Does the initial final-candidate selection recur? |
| **P1 — Heading renumbering** | All six heading orders over the unchanged `C1 → C2 → C3` body sequence | Does the chosen content change when only the headings change? |
| **P2 — Content switching within case** | All six body permutations beneath each fixed heading order | Does choice follow the label, an original body, or its position? |
| **P3 — `321` retention** | Analyze `C2` at all three positions under fixed `321` headings | Does the reported content-following pattern hold across both rival orders at each position? |
| **P4 — `312` boundary** | Analyze `C2` at all three positions under fixed `312` headings | Does placing `C2` first reliably transfer choice to the last candidate? |
| **P5 — Wording and invented-name controls** | Separately exchange invented-name sets and use matched paraphrase templates | Does selection track sentence realization, invented terms, or their combination? |
| **P6 — Support controls** | Add predesignated coherent repetitions or equivalent paraphrases; compare equal-length neutral additions | Does represented support alter the observed selection pattern? |
| **P7 — Response-format control** | Compare the original question with one explicitly allowing `Equal` or `Indeterminate` | Does the reporting format change candidate-selection frequency? |
| **P8 — Explicit-criterion control** | Add an unambiguous criterion and counterbalance which candidate satisfies it | Does task-relevant evidence override label and placement preferences? |

### Primary factorial layout

Cross **six heading orders** with **six body orders**, yielding **36 unique layouts**. All six heading orders now have reported case-level outcomes; this matrix supplies the fully crossed per-layout replication design. The six Set 1 layouts, with body order fixed at `123`, are a subset of this matrix, not six additional conditions. The `321` and `312` analyses are likewise targeted slices of the matrix.

A proposed replication schedule is **20 fresh-conversation trials per layout**, for **720 trials** in the primary matrix. This is a prospective allocation, not the number of completed pilot runs. Randomize execution order and report each cell's count and selection frequencies.

### Trial protocol and records

Preserve the exact body text, nine-attribute ordering, punctuation, separators, and closing question in the primary matrix. Change only the heading assignment or whole-body assignment specified by the condition. Run each trial in a fresh conversation without preliminary recognition or explanation questions.

Record the displayed model name, interface, date and time, available settings, complete submitted prompt, raw response, and the mapping between label, original content, and position. Record account-level context settings where available and keep them constant during a replication batch. The pilot's fresh-conversation procedure does not require an invented claim about settings that were not supplied.

Parse the answer first as a displayed heading and then map it to original content identity and position. Preserve noncandidate and malformed responses as separate categories rather than discarding them. Additional explanation probes belong in separate trials.

Use the complete prompt and its hash as the realized condition identifier. Keep `test_set` and `case_label_order` as explicit metadata. Labels `321` and `312` refer to different heading layouts even when body order is the same; they are not histories carried between conversations.

### Measurements

For complete prompt $C$, let $Y$ denote the selected original content identity, with noncandidate responses retained separately. Define:

```math
E_i(C)=P(Y=C_i\mid C),
\qquad
\widehat E_i(C)=\frac{1}{n_C}\sum_{r=1}^{n_C}\mathbf{1}[Y_r=C_i].
```

The denominator includes all submitted trials for the condition. This uses the Triad's response-consistency convention with selection as the scored event; it is not a correctness measure.

Report three parallel outcome views: **selected label**, **selected content**, and **selected position**. For Set 1, compare selected content across heading-only changes. For Set 2, compare retention of selected content across body assignments within each heading order. Report noncandidate frequency alongside these selection rates.

For the focal boundary, let $e_2(L,p)$ be the selection probability of original `C2` under heading order $L$ when `C2` occupies position $p$, averaged equally over the two orders of the other bodies. Define:

```math
B_2(L)=\frac{e_2(L,2)+e_2(L,3)}{2}-e_2(L,1).
```

A positive value describes a first-position disadvantage relative to the middle and last positions. The case-dependent contrast is:

```math
I_2=B_2(312)-B_2(321).
```

The reported pattern predicts a larger boundary contrast for `312`. The factorial trials estimate it while balancing rival order. Report cell frequencies, trial counts, and uncertainty intervals; the full response table remains the primary result.

## 6. Scope and Evidence Status

**Observation record:** The researcher reports repeated tests in ChatGPT using GPT-6 Instant, each in a fresh conversation, with 100% selection consistency for the described conditions. The original stimuli and the two-set testing procedure are supplied. Exact per-condition run counts, generation settings, complete switched-prompt logs, and raw response transcripts were not supplied.

The outcomes for all six heading-order cases are reported pilot observations. The 36-layout matrix, replication allocation, support interventions, and associated measurements are proposed follow-up tests.

## 7. Conclusion

The Glip pilot documents repeatable selection among deliberately evaluatively equivalent, differently worded candidates. Its interpretation depends on separating **renumbered headings over fixed content** from **switched content beneath fixed headings**.

Case `321` follows original `C2` across tested positions. Case `312` follows the same content in the middle and last positions but selects the last candidate when `C2` is first. Cases `123`, `132`, `213`, and `231` were reported as selecting the displayed `Glip3`, rather than exhibiting the same original-content following. In `231`, this selection persists through content swaps even though `Glip3` is in the middle, not last.

The resulting research target is **when selection follows a label, when it follows a description, and when description-following depends on placement**. The crossed heading-and-content design makes these outcomes measurable within the Context Triad without conflating names, bodies, or positions.

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

The original two-candidate prompt consists of A.1, a blank line, A.2, a blank line, and the exact final question. The three-candidate extension inserts A.3 before that question, also separated by a blank line.

For Set 1, replace only the `GlipN:` headings with the case's label sequence. For Set 2, keep those headings fixed and exchange the complete nine-line bodies. Do not insert case codes, `C1`–`C3`, study terminology, or scoring instructions into the experimental prompt.

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

```text
trial_id, date_time, model_display_name, model_version_if_available,
interface, available_generation_settings, context_settings,
test_set, case_label_order, content_order, candidate_count,
label_to_content_map, content_to_position_map,
exact_prompt_sha256, exact_prompt_text, raw_response,
selected_display_label, selected_original_content,
selected_position, response_category
```

Store one row per fresh-conversation trial and retain exact text alongside its hash. Report label-only results and within-case content-switch results separately before aggregating the crossed matrix.
