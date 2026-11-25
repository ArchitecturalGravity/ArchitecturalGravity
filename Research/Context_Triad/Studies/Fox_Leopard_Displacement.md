<a id="paper-fox-leopard-answer-displacement"></a>
# Fox–Leopard Displacement: Semantic Weight and Implicit Pangram Inference

## A `GPT-6 Luna / Low` Study of the Context Triad -- 21 November 2026 (UTC)

## Abstract

This 360-trial study tested whether expanding a competing Leopard description changes how often replies show evidence of identifying the quick-brown-fox pangram. The headings stayed in numerical order while the three animal descriptions moved through all six assignments. The expanded prompt elicited more single-animal choices, while pangram identification was similar across the two prompts.

## Role Within the Context Triad

The study distinguishes an implicit cue available in the prompt from evidence that the model recognized it and from the animal it selected. The Leopard expansion adds competing information while leaving the cues to the intended inference intact within each matched pair. [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) frames the comparison, and [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) frames the placement of the cues and the competing block.

## The Intended Inferential Correlation

> The quick brown fox jumps over the lazy dog.

| Part of the phrase | Cue in the prompt |
| --- | --- |
| Quick brown fox | Fox attributes: `Speed: Quick`, `Color: Brown`, `Type: Fox` |
| Lazy dog | Dog attributes: `Demeanor: Lazy`, `Type: Dog` |
| Jumps over | The question asks which animal jumps over the label containing the Dog description |

The prompt neither states the full sentence nor mentions pangrams. Fox is the intended answer by association. A bare Fox choice does not demonstrate recognition.

## Two Prompts; One Unchanged Implicit Cue

| Feature | Prompt 1 (Short) | Prompt 2 (Expanded) |
| --- | --- | --- |
| Leopard description | 3 attributes; 3 words in the values | 50 attributes; 1,178 words in the values |
| Fox and Dog descriptions | Fixed wording | Same wording |
| Question | Refers to the Dog label for that assignment | Same question within the matched pair |

Both Leopard blocks begin with `Speed: Fast`, `Color: Silver` and `Type: Leopard`. Prompt 2 adds 47 attributes, starting with `Species: Panthera uncia`. From attribute 4 through 50, each value adds one whitespace-delimited word to the preceding value's length. The expanded block includes movement descriptions but makes no explicit jumping or leaping claim. [Appendix A](#fox-leopard-verified-stimuli) reproduces one matched pair.

### 1. Trial methodology

Every prompt displayed `[Animal1]`, `[Animal2]` and `[Animal3]` in that order. The complete Fox, Dog and Leopard descriptions moved among these headings, covering all six permutations for each prompt. For example, moving Dog from `[Animal1]` to `[Animal2]` changed the question’s target to `[Animal2]`. Each animal occupied each slot 60 times per prompt.

Six assignments × 30 repeats × two prompts produced 360 trials, or 180 matched pairs. Each pair shared an assignment and repeat; only the Leopard description changed. For every assignment, Short ran first in 15 pairs and Expanded ran first in 15. Each trial used a fresh Codex conversation without inherited conversation history. Each input consisted of a single untagged triple-backtick fence containing the three blocks and the question.

### 2. Scoring

**Primary outcome: evidence of pangram identification.** Full reconstruction linked the quick brown Fox to the lazy Dog through the jumping-over relation, including when the reply used clear references to connect those cues. Recognizable partial cues and explicit references to the pangram also counted as identification evidence.

**Secondary outcome: animal selected.** Replies were scored by the animal named or unambiguously referenced, not by its label. One favored animal counted as a single selection. Multiple candidates without a clear preference and replies making no selection were coded separately.

## Central Observation: Pangram Identification and Answer Displacement

### 1. Evidence of pangram identification

| Evidence in the reply | Prompt 1 (Short) | Prompt 2 (Expanded) |
| --- | ---: | ---: |
| Full reconstruction | 12/180 | 10/180 |
| Partial cue or explicit reference | 22/180 | 21/180 |
| **Any evidence of identification** | **34/180 (18.9%)** | **31/180 (17.2%)** |
| No evidence observed | 146/180 | 149/180 |

Among the 180 matched pairs, 6 showed evidence in both replies, 28 in Short only, 25 in Expanded only and 121 in neither. The overall difference was −1.7 percentage points (Expanded minus Short; two-sided exact McNemar `p = 0.784`).

### 2. Animal selected in the final reply

| Selection outcome | Prompt 1 (Short) | Prompt 2 (Expanded) |
| --- | ---: | ---: |
| Fox | 70/180 | 94/180 |
| Leopard | 58/180 | 80/180 |
| Dog | 0/180 | 0/180 |
| Ambiguous or multiple | 29/180 | 1/180 |
| No selection | 23/180 | 5/180 |
| **No single animal selected** | **52/180** | **6/180** |

Both Fox and Leopard gained selections. The expanded prompt increased decisiveness within replies, rather than uniformly steering them toward Leopard.

### 3. Leopard selection by displayed slot

Each slot pools the two assignments in which Leopard occupies it. The heading number and display position coincide by design.

| Leopard slot | Prompt 1 (Short) | Prompt 2 (Expanded) | Expanded minus Short (percentage points) |
| --- | ---: | ---: | ---: |
| `[Animal1]` (first) | 18/60 | 19/60 | +1.7 |
| `[Animal2]` (middle) | 21/60 | 28/60 | +11.7 |
| `[Animal3]` (last) | 19/60 | 33/60 | +23.3 |

Leopard selections were nearly flat across slots with the short block and rose at each later slot with the expanded block. The gap was smallest with Leopard first and largest with Leopard last. The two Leopard-last assignments moved in opposite directions.

### 4. Outcomes by animal assignment

Each row gives the contents under `[Animal1]`, `[Animal2]` and `[Animal3]`, in that order. Rows sharing a Dog label hold the question fixed and swap Fox with Leopard.

| Animal1 → Animal2 → Animal3 | Dog label | Pangram evidence, Short | Pangram evidence, Expanded | Leopard selected, Short | Leopard selected, Expanded |
| --- | --- | ---: | ---: | ---: | ---: |
| Dog → Fox → Leopard | `[Animal1]` | 12/30 | 2/30 | 1/30 | 23/30 |
| Dog → Leopard → Fox | `[Animal1]` | 1/30 | 2/30 | 19/30 | 12/30 |
| Fox → Dog → Leopard | `[Animal2]` | 3/30 | 15/30 | 18/30 | 10/30 |
| Leopard → Dog → Fox | `[Animal2]` | 9/30 | 7/30 | 11/30 | 6/30 |
| Fox → Leopard → Dog | `[Animal3]` | 7/30 | 2/30 | 2/30 | 16/30 |
| Leopard → Fox → Dog | `[Animal3]` | 2/30 | 3/30 | 7/30 | 13/30 |

## Relation to the Context Triad

- [**Semantic Weight:**](../Semantic_Weight.md#paper-semantic-weight) The short Fox and Leopard blocks each had three one-word values, and replies more often left the choice open. With the expanded Leopard block, replies more often named one animal, with both Fox and Leopard gaining selections. This suggests that giving one alternative more descriptive support can reduce indecision.
- [**Semantic Shadow:**](../Semantic_Shadow.md#paper-semantic-shadow) With the short Leopard block, selection stayed nearly flat across slots. With the expanded block, Leopard selection rose at each later slot. The expansion’s advantage was smallest when both Fox and Dog followed Leopard and largest when neither did. This pattern is consistent with subsequent context dampening the influence of the added detail.

## Proposed Tests of Semantic Weight and Shadow

| Test | Status | Controlled variation | Research question |
| --- | --- | --- | --- |
| Balance of descriptive detail | **Partly tested.** Both short vs. Leopard alone expanded | Add Fox alone expanded and both expanded. Run all four conditions at matched total prompt length in the same layout. Match additions in length and specificity and preserve pangram cues | Does unequal detail reduce indecision regardless of which animal gets the expansion? |
| Subsequent context | **Proposed.** The slot pattern motivates the test | For each Leopard block length, hold its label, slot, wording and distance to the question fixed. Vary whether equal-length text following Leopard is relevant to the choice or neutral, leaving the Fox and Dog cues unchanged | Does relevant subsequent context reduce the effect of expanding Leopard? |
| Competing jump cue | Proposed | At similar lengths, substitute a jumping claim for a neutral attribute | Does a competing cue that directly answers the question alter either outcome? |
| Pangram cue | Proposed | Change one of `Quick`, `Brown`, `Lazy` or the relation in the question | Which cues support observable identification? |
| Separate recognition probe | Proposed | Ask in fresh conversations whether the animal descriptions and question evoke a familiar sentence | Is the association recoverable when recognition is elicited directly? |

## Scope and Evidence Status

[Fox-Leopard-360-trial-results.csv](./Data/Fox-Leopard-360-trial-results.csv) records the assignment, exact prompt, recorded input, verbatim reply, hashes and scores for each of the 360 trials. Every recorded input matched its planned prompt, and the archive was applied after all 360 trial replies were verified. All trials were configured for GPT-6 Luna with Low reasoning effort.

The outcomes measure visible recognition and decisiveness within replies. The design varies length and content together, and slot changes also change the label and surrounding context.

## Conclusion

### 1. Semantic Weight: More decisive replies

When Fox and Leopard were equally brief, replies more often left the choice open. Expanding Leopard led to more single-animal choices, while the overall Fox–Leopard split among those choices and the rate of pangram identification changed little. The added detail appears to have helped the model commit to an answer without consistently favoring Leopard.

### 2. Semantic Shadow: A larger advantage in later slots

With the short block, Leopard selection was nearly flat across slots. With the expanded block, Leopard was selected more often at each later slot. The gap between prompts was smallest when both Fox and Dog followed Leopard and largest when neither did, consistent with later descriptions dampening the influence of the extra detail.

### 3. Slightly less evidence of pangram identification

The expanded prompt elicited slightly less evidence of pangram identification overall, a decrease of 1.7 percentage points.

## Related Papers

- [Context Triad](../Context_Triad.md#paper-context-triad) — semantic presence and behavioral influence
- [Semantic Weight](../Semantic_Weight.md#paper-semantic-weight) — competing descriptions and support–response measurements
- [Semantic Locality](../Semantic_Locality.md#paper-semantic-locality) — placement of cues and competing descriptions
- [Semantic Shadow](../Semantic_Shadow.md#paper-semantic-shadow) — how subsequent context changes the influence of earlier material

<a id="fox-leopard-verified-stimuli"></a>

## Appendix A — Verified Stimuli

**Record:** The first matched pair assigned Leopard to `[Animal1]`, Fox to `[Animal2]` and Dog to `[Animal3]`. The two recorded prompts are shown in prompt-number order. The triple-backtick fences are part of the recorded inputs.

### A.1 Prompt 1 — Short Leopard Description

~~~text
```
[Animal1]:
1. Speed: Fast
2. Color: Silver
3. Type: Leopard

[Animal2]:
1. Speed: Quick
2. Color: Brown
3. Type: Fox

[Animal3]:
1. Demeanor: Lazy
2. Type: Dog

Question: Which animal jumps over [Animal3]
```
~~~

### A.2 Prompt 2 — Expanded Leopard Description

~~~text
```
[Animal1]:
1. Speed: Fast
2. Color: Silver
3. Type: Leopard
4. Species: Panthera uncia
5. Animal Class: Classification is Mammalia
6. Family: Taxonomic placement is Felidae
7. Size: Body size is moderately large
8. Weight: Adult individuals usually weigh 22–55 kilograms
9. Length: Head and trunk measure 90–130 centimeters combined
10. Tail: The long, bushy tail aids balance and warmth
11. Eyes: Pale green or gray eyes see in dim light
12. Fur: Dense, soft fur traps air to insulate against the cold
13. Pattern: Dark rosettes and spots break up the outline, making detection harder
14. Habitat: High elevations offer rocky alpine landscapes with exposed stone above the treeline
15. Geographic Range: The species ranges through parts of Central and South Asia, spanning several countries
16. Climate Preference: Preferred climates combine low temperatures and persistent snow, unlike milder conditions at lower elevations
17. Diet: A carnivorous diet centers on other animals rather than on vegetation as a food source
18. Favorite Prey: Wild sheep, ibex, marmots, and smaller mammals are usual targets, from hoofed animals to small rodents
19. Hunting Style: Stealthy hunters approach without attracting notice, then attack by surprise instead of relying on a prolonged pursuit
20. Demeanor: Solitary habits and caution go together with close attention to changes in surroundings, especially unfamiliar sounds or movements
21. Temperament: An elusive temperament makes encounters with people uncommon, even on slopes occasionally traversed by herders, trekkers, or field researchers
22. Whiskers: Long whiskers emerge on both sides of the muzzle, where individual strands stand out clearly against the shorter fur beneath
23. Ear Shape: Small rounded ears frame the upper head, their curved edges forming a distinct contour from the straighter profile of the muzzle
24. Climbing Ability: Climbing skill allows secure footing on uneven stone surfaces, including steep slopes where rock is irregular and available footholds may be narrow
25. Swimming Ability: Swimming is possible, but infrequent sightings leave too little evidence to say how often adults enter open water or under what environmental conditions
26. Activity Pattern: Peak activity occurs around dawn and dusk, so midday observations give only a partial picture of how frequently the animal moves over a day
27. Communication: Growls, hisses, and chuffs carry audible signals, while lingering scent marks convey information about the sender after the animal has moved away from the site
28. Roaring Ability: The voice lacks the full roar associated with lions and tigers, so a listener should not necessarily expect the same resonant sound from all large cats
29. Intelligence: Flexible route selection and keen spatial awareness are useful even where a pass visible from one vantage point disappears from view as the angle of approach changes
30. Social Behavior: Adults generally keep apart outside the breeding season, with a notable exception in temporary family groups that form when a female rears her young before they become independent
31. Territorial Behavior: Scratches and scent deposits announce occupancy along travel routes, allowing a visitor to register an earlier passage at particular points without having to meet or follow the animal responsible
32. Camouflage: Pale patches fade into remaining drifts while darker markings resemble shadows between stones, making the transition from flank to background harder to distinguish when the observer views it from afar
33. Special Adaptation: Wide, furred paws spread the load over enough space to reduce sinking into loose powder, where a narrower point of contact would concentrate pressure on a smaller patch with each step
34. Cold Resistance: Fine fibers of the undercoat capture still air beneath the outer layer, forming a barrier that slows heat loss from the skin as temperatures fall across the most exposed slopes in winter
35. Tail Function: Movement of the extended tail helps steady the animal on uneven footing, whereas at rest the same appendage can be curled around the torso to shield the nose and cheeks from frigid air
36. Typical Lifespan: Roughly ten to twelve years is the customary estimate for survival in the wild, a figure best read as a broad expectation rather than as an upper limit on age or any firm guarantee
37. Reproduction: Litters usually consist of one to three cubs, so a single birth event can produce an only offspring or siblings that begin life together, with the number referring specifically to youngsters delivered in that pregnancy
38. Parental Behavior: A mother provides protection and care without a male partner, remaining the sole parent responsible for her dependents while they are too immature to handle all the demands of feeding and finding safety on their own
39. Natural Predators: Full grown animals are seldom primary targets of other large hunters, a description of how seldom they are taken as quarry rather than an assertion that an encounter with another carnivore cannot end in injury or death
40. Conservation Status: Vulnerable is the assigned conservation category, a formal indication of extinction risk that applies across the global population and does not by itself describe which local groups are the smallest, most isolated, or most likely to disappear first
41. Primary Threats: Illegal killing removes animals, the division of suitable country into disconnected parcels restricts access between areas, and declining numbers of prey reduce food supplies, so pressures on this predator can originate well beyond the sites where it is seen
42. Distinctive Feature: The tail is unusually long and thick relative to a compact trunk, and the contrast is most evident in profile, where the fully extended shape remains distinct from the legs and torso instead of overlapping the rest of the body
43. Personality Description: A quiet, self reliant disposition combines with patience and observation, traits better conveyed by the sustained attention paid to an unfamiliar stimulus than by dramatic displays, and none of these tendencies requires the animal to stay passive when action is necessary
44. Defensive Behavior: Withdrawal is generally favored over confrontation when a threat appears, with the distinction that leaving can end the contact without settling which party would prevail, whereas remaining in place keeps the possibility of direct conflict open for as long as both stay
45. Environmental Awareness: Sensitive hearing can reveal activity beyond a visual barrier, while sharp eyesight makes exposed movement easier to follow, giving the animal two ways to account for an event when a ridge, cover, or a bend in the landscape interrupts the line of sight
46. Movement Style: Deliberate placement of the feet gives the gait a smooth, almost noiseless quality, especially noticeable when the observer can see the body moving but hears little indication of contact with the ground, a contrast that defines this style rather than any particular traveling speed
47. Endurance: Sustained travel over demanding country requires the capacity to keep going after the first incline or exposed stretch has been crossed, and the species is suited to journeys in which many such obstacles occur in succession rather than being confined to a single short passage
48. Preferred Resting Place: Deep recesses and rocky ledges provide secluded resting sites, so a place to settle may be tucked behind a face of stone or set back from an open slope, offering a quieter and less exposed alternative to the visible paths that cut through the surrounding terrain
49. Unique Trait: The nickname Ghost of the Mountains reflects an animal easier to trace than to watch, since tracks or other signs can remain after a brief passage through terrain where ridges interrupt sightlines and a watcher might catch only a fleeting glimpse before the slope hides the silhouette
50. Overall Description: A powerful predator adapted to cold, remote uplands combines a coat that buffers exposure with habits that limit detection, a profile in which physical structure and behavior both matter because success depends not just on reaching suitable places but on living there through changing conditions across successive seasons

[Animal2]:
1. Speed: Quick
2. Color: Brown
3. Type: Fox

[Animal3]:
1. Demeanor: Lazy
2. Type: Dog

Question: Which animal jumps over [Animal3]
```
~~~
