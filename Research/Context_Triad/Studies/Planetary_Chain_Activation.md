<a id="paper-planetary-chain-activation"></a>
# Planetary Chain Activation: A Semantic Locality Pilot of Order-Dependent Associative Recognition

## A `GPT-6 Instant` Pilot Observation of the Context Triad -- 26 October 2026

## Abstract

This study examines whether the ordering of independently represented semantic associations influences the spontaneous recognition of an unstated, familiar sequence.

Eight symbolic references contain mythological descriptions indirectly associated with the eight planets of the Solar System -- neither planet names nor the astronomical relationship are stated in the experimental prompts. Each reference constitutes an individual **Implicit Associative Inference (IAI)** unit and recognition and reconstruction of the collective planetary relationship is the intended **Associative Pattern Completion (APC)** outcome.

Three ArcGrav prompts preserve the same eight references, identical descriptive clues, and identical concluding task. The task requests both the appropriate sequence and a one-sentence explanation of the ordering. The first places the references in canonical planetary order; the second reverses that order; and the third scatters them. In each prompt, the entries in `[Chain]` follow the order in which the references appear.

In the GPT-6 Instant pilot, **only the canonically ordered prompt elicited the planetary correlation**. The reversed and scattered conditions did not. **The central observation is an order-dependent change in the expression of an unstated collective association while its constituent semantic cues remain present.**

This contrast motivates separating canonical-sequence priming from definition placement under the [Context Triad](../README.md#paper-context-triad). The requested explanation provides an observable indication of the ordering principle expressed by the model.

## Role Within the Context Triad

This pilot documents how presenting the same mythological associations in different sequences changes spontaneous identification of an unstated planetary pattern. It motivates the [Semantic Locality](../Semantic_Locality.md) study, especially independent manipulation of definition placement and reference order.

## 1. The Intended Inferential Correlation

The familiar planetary sequence is:

> **Mercury → Venus → Earth → Mars → Jupiter → Saturn → Uranus → Neptune**

The task never identifies the references as planets, names astronomy, or requests astronomical sorting. Instead, it offers eight mythological descriptions under arbitrary symbolic identities.

| Symbol | Mythological descriptors | Intended unstated association |
| --- | --- | --- |
| `[Qevan]` | Winged sandals; messenger and protector of travelers | Mercury |
| `[Mepix]` | Mother of Aeneas; embodiment of love and beauty | Venus |
| `[Tovek]` | Primordial mother of the Titans; consort of the sky-father | Earth |
| `[Zafur]` | Father of Romulus and Remus; patron of warriors | Mars |
| `[Ruvem]` | Wielder of thunderbolts; supreme ruler of the gods | Jupiter |
| `[Pekil]` | Ruler of the Golden Age; swallowed his own children | Saturn |
| `[Nolix]` | Primordial father of the Titans; overthrown by his youngest son | Uranus |
| `[Vezor]` | Trident-bearing ruler of the seas; patron of horses | Neptune |

Each symbolic unit is an **IAI** opportunity: the model must recover the intended relationship through previously learned associations rather than read it from an explicit assertion. The labels themselves give no meaningful hints.

**APC** requires an additional operation: integrating the separately cued identities into the familiar eight-planet relationship and producing the appropriate sequence. The requested one-sentence explanation can help distinguish explicit recognition of the planetary ordering principle from literal repetition of `[Chain]`.

The concluding task is:

> Task: Provide the appropriate sequence for [Chain] and a one sentence explanation

**The planetary sequence is the target associative interpretation**, inferred from the mythological clues rather than specified by the task. The explanation should express the basis for the proposed ordering without the prompt identifying the intended domain or supplying an ordering criterion.

## 2. Three Prompts and One Preserved Set of IAI Units

All three conditions keep every reference body and the concluding task identical across conditions. Each `[Chain]` lists the references in the order of their first occurrence, as established by the experimental design to retain general sequencing consistency. Full prompts appear in [Appendix A](#appendix-a--reported-stimuli-and-outcomes).

| Feature | P1 — Expected | P2 — Reverse | P3 — Scattered |
| --- | --- | --- | --- |
| Eight IAI definitions | Same | Same | Same |
| Mythological clues | Unchanged | Unchanged | Unchanged |
| Reference labels | Unchanged | Unchanged | Unchanged |
| Definition order | Canonical | Reversed | Scattered |
| `[Chain]` order | Canonical | Reversed | Scattered |
| Concluding task | Sequence and one-sentence explanation | Same | Same |
| Intended associative output | Canonical eight-planet sequence and explanation of the ordering principle | Same | Same |
| **GPT-6 Instant result** | **Correlation elicited** | **Not elicited** | **Not elicited** |

### Reported response pattern

**P1 — Expected associative order:** The response identified the planetary correlation. The references already followed Mercury-through-Neptune order, providing a collective associative cue.

**P2 — Reverse associative order:** The response followed the noncanonical `[Chain]` order and added mythological details. Follow-up replies did not identify the planetary pattern.

**P3 — Scattered associative order:** The response followed the scattered `[Chain]` order and added mythological details. Follow-up replies did not identify the planetary pattern.

## 3. Central Observation: Contextual Ordering and Associative Activation

No condition deletes or contradicts a mythological clue. No condition introduces a competing instruction, and each symbol remains explicitly invoked in the concluding `[Chain]`. The task requests an explanation equally across conditions, without introducing an astronomical cue.

Only the canonical condition elicited the intended hidden relation in the study record:

> **The same distributed implicit associations produced a planetary correlation under canonical ordering but did not produce that correlation when the references were reversed or scattered**

This contrast highlights three distinct properties:

- **Semantic Presence:** The eight sets of clues are present in every prompt
- **IAI Recoverability:** Individual clue-to-planet associations can be measured separately from full-chain recognition
- **APC Activation:** The integrated planetary relation appears in the canonical-condition response

The canonical condition alone presents the target order, so **canonical-sequence priming** and **definition placement** change together. The observed phenomenon is **order-dependent associative activation**; independently varying definition and `[Chain]` order will distinguish these contributions.

## 4. Relation to the Context Triad

This case belongs in the Triad because **the presence of semantic information does not ensure that its intended inferred relation will govern the final response**.

- [**Semantic Locality:**](../Semantic_Locality.md#paper-semantic-locality) The eight references occupy different positions in the input sequence relative to each other and the concluding task. Their invocation through `[Chain]` is near the task, but their substantive descriptions occupy distributed earlier positions. The manipulation therefore changes placement profiles and relative distance to use, alongside reference sequence.

The focus is spontaneous integration of indirect semantic cues, rather than recall of a fact explicitly requested by the prompt.

## 5. Proposed Tests of the Associative Locality Hypothesis

These **proposed controls** separate placement, canonical-sequence activation, and individual clue recognizability. Keep the concluding task identical across conditions.

| Condition | Controlled variation | Research question |
| --- | --- | --- |
| **P0 — Canonical baseline** | Prompt 1 (P1) | How often does canonical ordering elicit planetary APC? |
| **P1 — Reverse baseline** | Prompt 2 (P2) | Does the reported non-activation recur? |
| **P2 — Scattered baseline** | Prompt 3 (P3), with additional scatter permutations | How reliably do noncanonical orders differ? |
| **P3 — Definition relocation** | Keep `[Chain]` canonical while moving only definitions | Can physical placement alter APC without changing chain order? |
| **P4 — Chain permutation** | Keep definition placement fixed while changing only `[Chain]` order | Is the outcome driven by canonical ordering in the final chain? |
| **P5 — Independent recognition probes** | In separate fresh contexts, ask about each symbol's association | Are individual IAIs recoverable when collective APC is not expressed? |
| **P6 — Noncanonical sequence control** | Use other hidden associative sequences and counterbalanced target orders | Does the effect generalize beyond a memorized planetary sequence? |
| **P7 — Cue ablation** | Replace individual cues with matched neutral descriptions | Which cues are necessary for the observed correlation? |

The highest-priority control independently crosses **definition order** and **chain order**. Record each definition's actual token span, relative position, and distance from the concluding task while keeping model settings, stimulus wording, and content support matched.

Measure five outcomes: (1) spontaneous recognition of the astronomical relationship, (2) recovery of all eight associations in canonical order, (3) per-symbol IAI recognition in separate probes, (4) alternatives such as literal chain repetition, mythological naming, or other ordering rationales, and (5) the ordering principle expressed in the one-sentence explanation, including whether it explicitly identifies the planetary sequence. Score sequence correctness and explanation content separately; an expressed explanation is a behavioral observation, not direct evidence of an internal reasoning process.

Use fresh-context trials at fixed settings, preserve exact outputs, and compare response frequencies. Keep recognition probes separate so the chain task never receives an explicit planetary cue. Document reproducible prompt layouts and counterbalance definition placement and Chain order.

## 6. Scope and Evidence Status

**Observation record:** The study records three ArcGrav prompts and categorical GPT-6 **Instant** outcomes dated 26 October 2026: only P1 elicited the planetary correlation. Exact model replies were not supplied; the study records three simultaneous runs. The available evidence does not permit separate assessment of sequence accuracy, explanation content, or compliance with the one-sentence requirement.

The observed contrast motivates separate manipulation of definition placement and final chain order.

## 7. Conclusion

The canonical ordering elicited the planetary association, while the reverse and scattered presentations did not in the reported pilot. Crossing definition placement with final reference order is the priority controlled test. The sequence and its requested explanation provide complementary measures of the expressed ordering principle in controlled trials.

## Related Papers

- [Context Triad](../README.md#paper-context-triad) — semantic presence and behavioral influence
- [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) — placement geometry, distribution, and points of use

## Appendix A — Reported Stimuli and Outcomes

**Record:** ArcGrav prompts with `[Chain]` following reference appearance order and an identical concluding task requesting a sequence and one-sentence explanation. Categorical GPT-6 **Instant** outcomes were supplied for 26 October 2026; three simultaneous runs reported. Verbatim replies were not supplied.

### A.1 Prompt 1 — Expected Associative Order

~~~text
[Qevan]:
- Protects travelers and delivers divine messages
- Winged sandals and a serpent staff

[Mepix]:
- Governs love, beauty, desire, and attraction
- Paris awards her the golden apple

[Tovek]:
- Personifies the world that sustains life
- Bears mountains and the primordial sea

[Zafur]:
- Embodies bloodshed and fury in battle
- Fathers the twins Romulus and Remus

[Ruvem]:
- Rules the gods from Mount Olympus
- Hurls thunderbolts and bears an aegis

[Pekil]:
- Rules during the fabled Golden Age
- Carries a sickle for harvesting grain

[Nolix]:
- Personifies the sky that surrounds everything
- Fathers the first generation of Titans

[Vezor]:
- Rules the seas and causes earthquakes
- Strikes the ground with his trident

[Chain]:
- [Qevan]
- [Mepix]
- [Tovek]
- [Zafur]
- [Ruvem]
- [Pekil]
- [Nolix]
- [Vezor]

Task: Order [Chain]
~~~

**Reported outcome:** Planetary correlation elicited (exact response not supplied).

### A.2 Prompt 2 — Reverse Associative Order

~~~text
[Vezor]:
- Rules the seas and causes earthquakes
- Strikes the ground with his trident

[Nolix]:
- Personifies the sky that surrounds everything
- Fathers the first generation of Titans

[Pekil]:
- Rules during the fabled Golden Age
- Carries a sickle for harvesting grain

[Ruvem]:
- Rules the gods from Mount Olympus
- Hurls thunderbolts and bears an aegis

[Zafur]:
- Embodies bloodshed and fury in battle
- Fathers the twins Romulus and Remus

[Tovek]:
- Personifies the world that sustains life
- Bears mountains and the primordial sea

[Mepix]:
- Governs love, beauty, desire, and attraction
- Paris awards her the golden apple

[Qevan]:
- Protects travelers and delivers divine messages
- Winged sandals and a serpent staff

[Chain]:
- [Vezor]
- [Nolix]
- [Pekil]
- [Ruvem]
- [Zafur]
- [Tovek]
- [Mepix]
- [Qevan]

Task: Order [Chain]
~~~

**Reported outcome:** Planetary correlation not elicited (exact response not supplied).

### A.3 Prompt 3 — Scattered Associative Order

~~~text
[Ruvem]:
- Rules the gods from Mount Olympus
- Hurls thunderbolts and bears an aegis

[Tovek]:
- Personifies the world that sustains life
- Bears mountains and the primordial sea

[Vezor]:
- Rules the seas and causes earthquakes
- Strikes the ground with his trident

[Mepix]:
- Governs love, beauty, desire, and attraction
- Paris awards her the golden apple

[Nolix]:
- Personifies the sky that surrounds everything
- Fathers the first generation of Titans

[Qevan]:
- Protects travelers and delivers divine messages
- Winged sandals and a serpent staff

[Pekil]:
- Rules during the fabled Golden Age
- Carries a sickle for harvesting grain

[Zafur]:
- Embodies bloodshed and fury in battle
- Fathers the twins Romulus and Remus

[Chain]:
- [Ruvem]
- [Tovek]
- [Vezor]
- [Mepix]
- [Nolix]
- [Qevan]
- [Pekil]
- [Zafur]

Task: Order [Chain]
~~~

**Reported outcome:** Planetary correlation not elicited (exact response not supplied).

### A.4 Researcher-Only Expected APC

~~~text
[Qevan] -> Mercury
[Mepix] -> Venus
[Tovek] -> Earth
[Zafur] -> Mars
[Ruvem] -> Jupiter
[Pekil] -> Saturn
[Nolix] -> Uranus
[Vezor] -> Neptune
~~~

**Expected collective association:** Mercury → Venus → Earth → Mars → Jupiter → Saturn → Uranus → Neptune.

**Expected one-sentence explanation (example):** The mythological descriptions correspond to the eight planets of the Solar System, arranged in increasing distance from the Sun.

The mapping, target sequence, and example explanation are researcher-only evaluation material and are not supplied in any experimental prompt. Equivalent explanations that identify the planetary ordering principle may satisfy the task.
