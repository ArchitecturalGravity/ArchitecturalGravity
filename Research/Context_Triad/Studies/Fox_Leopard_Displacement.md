<a id="paper-fox-leopard-answer-displacement"></a>
# Fox–Leopard Displacement: A Semantic Weight Study of Implicit Pangram Inference

## A `GPT-6 Luna / Low` Study of the Context Triad -- 18 November 2026 (UTC)

## Abstract

This study examines whether a competing animal description changes which animal the model selects when the prompt implicitly cues the familiar quick-brown-fox pangram. The Fox and Dog descriptions stay fixed while the Leopard block expands from three to fifty attributes, including explicit jumping cues.

Six label assignments were crossed with six display orders, two prompt versions, and five repetitions per condition, forming **one series of 360 scored trials**. Each trial used a fresh Codex subagent conversation with `GPT-6 Luna / Low` requested. The question always referred to the Dog’s assigned label.

Across 180 matched pairs, Leopard was selected in **77/180 Prompt 1 replies** and **135/180 Prompt 2 replies**. Leopard was selected more often under Prompt 2 in each position group: trials with the Leopard block displayed first, middle, or last. The largest difference was at first position.

**The central observation is answer displacement: the distribution of animal selections differed across prompt conditions while the pangram cues remained available.** The comparison does not separate description length from task-relevant wording.

## Role Within the Context Triad

This study documents answer displacement when a competing animal description expands while the implicit pangram cue remains present. The study varies animal labels and block order independently to test whether the displacement persists across layouts. The proposed [Semantic Weight](../Semantic_Weight.md) controls address competing context volume and task-specific cues separately.

## 1. The Intended Inferential Correlation

The famous English pangram, used in typing and font demonstrations because it contains every letter of the alphabet, is:

> **The quick brown fox jumps over the lazy dog.**

The task **never says that this phrase is the reference**, never identifies a pangram, and never states the event “Animal1 jumps over Animal2.” Its design instead relies on the reader recognizing a relationship among *scattered descriptors and the verb in the question*.

| Element of the familiar phrase | Where the prompt provides it | Required inferential step |
| --- | --- | --- |
| **quick brown fox** | `[Animal1]`: Speed = Quick; Color = Brown; Type = Fox | Recognize the conventional phrase's subject |
| **lazy dog** | `[Animal2]`: Demeanor = Lazy; Type = Dog | Recognize the conventional phrase's object |
| **jumps over** | Final question: “Which animal jumps over [Animal2]” | Recover the relationship connecting subject and object |

All three pieces must be related, rather than considered as independent biological facts. This matters because the prompt places the subject and object in labeled data blocks, not in a sentence that explicitly states who jumped. It also introduces a competing Leopard block. In the example assignment shown above, that block is `[Animal3]`; its display position varies.

**Fox is the target associative answer** (`[Animal1]` in this example): the dispersed clues can reconstruct the familiar pangram, but the prompt does not explicitly state a jumping event. The test measures whether that indirect association governs the selection.

## 2. Two Prompts; One Unchanged Implicit Cue

The two versions differ in the Leopard block. The Fox and Dog descriptions are identical across versions, and the question always refers to the label assigned to the Dog. The planned stimuli for the first matched pair, in `3–1–2` display order, appear in [Appendix A](#appendix-a--planned-stimuli).

| Feature | Prompt 1 | Prompt 2 |
| --- | --- | --- |
| Leopard block | Three short Leopard attributes | Fifty Leopard/snow-leopard attributes, including jumping and leaping |
| Pangram cue: **quick + brown + fox** | Present, unchanged | Present, unchanged |
| Pangram cue: **lazy + dog** | Present, unchanged | Present, unchanged |
| Relational cue: **jumps over** | Present in question, unchanged | Present in question, unchanged |
| Intended associative answer | Fox | Fox |

### Trial methodology

The study crossed **six label assignments × six label display orders × two prompts × five repetitions**. Each round shuffled all 36 layouts, with Prompt 1 scheduled immediately before Prompt 2 for each layout. Each trial used a fresh Codex subagent conversation without inherited history, configured for `GPT-6 Luna / Low`. The planned stimuli were enclosed in a single untagged fence. Within each prompt version, only label assignment, display order, and the Dog label in the question changed. All 360 trials returned final replies, five per condition. Animal choice was scored by referent, not label number. Spontaneous pangram reconstruction was scored separately from the verbatim final reply. A bare Fox answer did not count as reconstruction; partial cues were recorded separately.

## 3. Central Observation: Answer Displacement under Increased Competing Context

**Animal selected in the final reply:**

| Selection outcome | Prompt 1 | Prompt 2 |
| --- | ---: | ---: |
| Fox | 88/180 | 43/180 |
| Leopard | 77/180 | 135/180 |
| Dog | 0/180 | 1/180 |
| Ambiguous/multiple | 8/180 | 0/180 |
| No selection | 7/180 | 1/180 |

**Matched comparison.** Leopard selection was 32.2 percentage points higher under Prompt 2. Of 180 pairs matched by label assignment, display order, and scheduled repetition, 72 yielded a Leopard selection only under Prompt 2 and 14 only under Prompt 1.

**Pangram reconstruction, scored separately.** Full reconstruction occurred in 11/180 Prompt 1 replies and 12/180 Prompt 2 replies. Partial cues occurred in 26/180 and 9/180 replies, respectively.

### Leopard selection by displayed animal position

Animal position is where the block appears: first, middle, or last, independent of its label number. Each row pools the two display orders in which Leopard occupies that position.

| Leopard block position | Leopard selections, Prompt 1 | Leopard selections, Prompt 2 | Difference (percentage points) |
| --- | ---: | ---: | ---: |
| First | 19/60 | 52/60 | +55.0 |
| Middle | 31/60 | 40/60 | +15.0 |
| Last | 27/60 | 43/60 | +26.7 |

The prompt difference was largest with Leopard first. In both Leopard-first orders, the expanded block appeared before the Fox and Dog blocks, so the added text did not come between either block and the question. At the full-order level, Dog → Leopard → Fox was the only order in which Leopard was selected less often under Prompt 2 (see the matrix totals).

**Label versus position.** In a descriptive comparison of matched layouts, swapping the Fox and Leopard label numbers at fixed physical order while keeping the Dog label unchanged shifted the Leopard selection rate by an average absolute **25.6 points in Prompt 1** and **30.0 in Prompt 2**. Swapping their physical positions at fixed label assignment and Dog position shifted it by **38.9** and **27.8 points**, respectively. For each prompt version, these comparisons used 18 matched layouts of each type, with five replies per layout. The contrasts reuse the same data, and each cell has few trials. They are descriptive, not estimates of independent effects.

### Leopard selection matrix: label assignment × animal display order

**F** = Fox, **D** = Dog, **L** = Leopard. Read a row code in label-number order (Animal1, Animal2, Animal3) and a column code in display order (first, middle, last). For example, row **FDL** assigns Animal1 to Fox, Animal2 to Dog, and Animal3 to Leopard; column **LFD** displays Leopard first, Fox second, and Dog last.

Cells show Leopard selections as **Prompt 1 · Prompt 2**. Each assignment-by-order cell is out of five replies per prompt. The bottom row pools all six assignments within each display order (30 replies per prompt).

| Assignment / Display order | FDL | FLD | DFL | DLF | LFD | LDF |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **FDL** | 4/5 · 4/5 | 0/5 · 2/5 | 0/5 · 2/5 | 1/5 · 0/5 | 1/5 · 4/5 | 1/5 · 0/5 |
| **FLD** | 3/5 · 4/5 | 4/5 · 4/5 | 0/5 · 2/5 | 4/5 · 4/5 | 2/5 · 5/5 | 2/5 · 4/5 |
| **DFL** | 4/5 · 5/5 | 0/5 · 4/5 | 1/5 · 3/5 | 3/5 · 3/5 | 1/5 · 5/5 | 1/5 · 4/5 |
| **DLF** | 3/5 · 4/5 | 1/5 · 1/5 | 1/5 · 2/5 | 5/5 · 5/5 | 1/5 · 5/5 | 1/5 · 5/5 |
| **LFD** | 5/5 · 5/5 | 1/5 · 5/5 | 2/5 · 4/5 | 4/5 · 4/5 | 1/5 · 5/5 | 4/5 · 5/5 |
| **LDF** | 4/5 · 4/5 | 3/5 · 3/5 | 0/5 · 4/5 | 5/5 · 5/5 | 3/5 · 5/5 | 1/5 · 5/5 |
| **All label assignments** | **23/30 · 26/30** | **9/30 · 19/30** | **4/30 · 17/30** | **22/30 · 21/30** | **9/30 · 29/30** | **10/30 · 23/30** |

## 4. Relation to the Context Triad

This case belongs in the Triad because **semantic information can remain present and inferentially relevant without continuing to govern behavior**.

- [**Semantic Weight:**](../Semantic_Weight.md#paper-semantic-weight) The Leopard block expands from three fields to fifty. The expanded representation also supplies jumping and leaping details that directly match the question. The selection shift motivates the matched controls below.
- [**Answer displacement:**](../README.md#common-behavioral-outcomes-and-dynamics) The competing Leopard interpretation was selected more often while the intended **implicit inferential correlation** remained available in the prompt.

## 5. Proposed Tests of the Semantic Weight Hypothesis

The following conditions separate contextual volume from task-specific jumping cues. This study compares P0 and P3 across all six physical orders. It does not separate description length from the added jumping cues or the rewritten Speed and Color fields.

| Condition | Controlled variation | Research question |
| --- | --- | --- |
| **P0 — Short baseline** | Prompt 1 | How reliably do the indirect cues elicit the pangram-based Fox answer? |
| **P1 — Size-only expansion** | Expand the Leopard block with length-matched, non-jumping background details while retaining the pangram cues | Can a large competing description displace the association without task-specific jumping claims? |
| **P2 — Jumping-cue addition** | Add only a small matched block describing Leopard jumping | How much displacement is attributable to task-specific semantic cues rather than bulk? |
| **P3 — Full expanded context** | Prompt 2 | How strong is the displacement relative to the matched controls? |
| **P4 — Jumping-cue ablation** | Preserve the expanded layout and approximate length but replace jumping-specific assertions with neutral details | Does the intended pangram inference recover without those explicit competing cues? |
| **P5 — Pangram-cue ablation** | Change one or more of Quick, Brown, Lazy, or the exact “jumps over” wording while preserving other conditions | Does Fox selection depend on the recognizable phrase-level correlation? |
| **P6 — Independent recognition probe** | In separate fresh-context runs, ask whether the described animal attributes and question evoke a familiar sentence | Is the pangram association recoverable even when it does not govern the original selection task? |

For the next comparison, replace the explicit jumping assertions with neutral details while preserving the expanded layout and approximate length. This tests those assertions, not all movement- or agility-related language. For a size-only contrast, keep the shared fields unchanged and use neutral expansion details. Keep the Fox and Dog descriptors and question wording unchanged, counterbalance which version runs first, and run the recognition probe separately so it cannot cue answers in the selection task.

## 6. Scope and Evidence Status

**Observation record:** 360 completed and scored trials. The accompanying `Fox-Leopard-360-trial-results.csv` records layout, execution notes, planned prompts and hashes, verbatim final replies, and both outcome scores. The planned hashes identify the intended text; most delivered prompts were not independently verified byte for byte. The main sequence scheduled Prompt 1 before Prompt 2 within each pair, so prompt version and within-pair run order were not independently varied.

## 7. Conclusion

Leopard was selected more often under Prompt 2 than under Prompt 1 at each of the three displayed animal positions when results were grouped by the Leopard block’s position. At the more detailed level of full animal order, this pattern held in five of six orders. The pangram cues were present in both prompt versions. Full pangram reconstruction was uncommon and was scored separately from animal selection. These results describe the answers the model gave; they do not establish whether it recognized the pangram without saying so. Matched controls are needed to separate description length from task-relevant wording.

## Related Papers

- [Context Triad](../README.md#paper-context-triad) — semantic presence versus behavioral influence and outcome classifications.
- [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) — coherent support, competing representation volume, and support–response experiments.

## Appendix A — Planned Stimuli

**Layout:** The two planned prompts for the first matched pair. Display order: `3–1–2`. Label assignment: `[Animal1]` Fox, `[Animal2]` Dog, `[Animal3]` Leopard.

### A.1 Prompt 1 — Short Leopard Description

```text
[Animal3]:
1. Speed: Fast
2. Color: Silver
3. Type: Leopard

[Animal1]:
1. Speed: Quick
2. Color: Brown
3. Type: Fox

[Animal2]:
1. Demeanor: Lazy
2. Type: Dog

Question: Which animal jumps over [Animal2]
```

### A.2 Prompt 2 — Expanded Leopard Description

```text
[Animal3]:
1. Speed: Fast and agile, capable of swift, precise movements
2. Color: Silver-gray with white fur and dark black markings
3. Type: Leopard
4. Species: Panthera uncia
5. Animal Class: Mammal
6. Family: Felidae
7. Size: Medium to large wild cat
8. Weight: 22–55 kilograms
9. Length: 90–130 centimeters, excluding the tail
10. Tail: Long, thick, and bushy, used for balance and warmth
11. Eyes: Pale green or gray, with exceptional low-light vision
12. Fur: Extremely dense, soft, and insulating
13. Pattern: Dark rosettes and spots for natural camouflage
14. Habitat: High-altitude mountains and rocky alpine regions
15. Geographic Range: Central and South Asia
16. Climate Preference: Cold, snowy, and mountainous environments
17. Diet: Carnivorous
18. Favorite Prey: Wild sheep, ibex, marmots, and smaller mammals
19. Hunting Style: Stealthy ambush predator
20. Demeanor: Solitary, cautious, intelligent, and observant
21. Temperament: Generally elusive and avoids human interaction
22. Strength: Powerful hind legs and exceptional jumping ability
23. Jumping Ability: Capable of leaping approximately 15 meters horizontally
24. Climbing Ability: Expert climber on steep and rocky terrain
25. Swimming Ability: Can swim, although rarely observed doing so
26. Activity Pattern: Most active at dawn and dusk
27. Communication: Growls, hisses, chuffs, and scent markings
28. Roaring Ability: Cannot produce the full roar typical of lions or tigers
29. Intelligence: Highly adaptable, with strong spatial awareness
30. Social Behavior: Primarily solitary except during mating and cub rearing
31. Territorial Behavior: Marks territory using scent and scratching
32. Camouflage: Excellent concealment against snow-covered rocky landscapes
33. Special Adaptation: Wide, fur-covered paws distribute weight across snow
34. Cold Resistance: Thick undercoat and long fur provide thermal insulation
35. Tail Function: Provides stability and can wrap around the face for warmth
36. Typical Lifespan: Approximately 10–12 years in the wild
37. Reproduction: Usually gives birth to 1–3 cubs per litter
38. Parental Behavior: Mothers raise and protect cubs without assistance from males
39. Natural Predators: Few natural predators as an adult
40. Conservation Status: Vulnerable
41. Primary Threats: Poaching, habitat fragmentation, and declining prey populations
42. Distinctive Feature: Exceptionally long tail relative to body size
43. Personality Description: Quiet, independent, patient, and highly alert
44. Defensive Behavior: Prefers escaping danger rather than confronting threats
45. Environmental Awareness: Sensitive hearing and keen visual perception
46. Movement Style: Graceful, deliberate, and nearly silent
47. Endurance: Adapted to navigating vast mountainous territories
48. Preferred Resting Place: Sheltered rocky ledges and secluded mountain caves
49. Unique Trait: Often called the "Ghost of the Mountains" because of its elusive nature
50. Overall Description: A powerful, mysterious, and exceptionally agile mountain predator, perfectly adapted to surviving in some of Earth's harshest environments

[Animal1]:
1. Speed: Quick
2. Color: Brown
3. Type: Fox

[Animal2]:
1. Demeanor: Lazy
2. Type: Dog

Question: Which animal jumps over [Animal2]
```
