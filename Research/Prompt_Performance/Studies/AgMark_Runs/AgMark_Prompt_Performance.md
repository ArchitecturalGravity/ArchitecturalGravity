<a id="study-agmark-prompt-performance"></a>
# Prompt Performance Across Five Authority Resolution Representations

## Abstract

Prompt comparisons can produce different rankings for correctness, resource use and response timing. This study examines five retained AgMark runs comparing ArcGrav, common prose, Markdown, XML and YAML representations of one authority-resolution task. Each run contains ten repetitions per treatment on one case, yielding 250 scored observations under `gpt-5.6-luna` with low reasoning. Recalculation from retained scores gives mean field accuracy of 99.7361% for ArcGrav, 99.7083% for prose, 99.9167% for Markdown, 100% for XML and 98.6367% for YAML. ArcGrav uses 18.63–22.62% fewer total tokens and 40.07–45.97% fewer uncached input tokens than the other treatments, but has the highest pooled mean inference-duration proxy. Its lower token use accompanies a substantially shorter prompt. Field accuracy also differs from exact-result agreement: four YAML observations receive full field credit despite ordering discrepancies. The findings support separate assessment of content, output obligations and resource consumption.

## Introduction

A prompt must convey the task, preserve distinctions that affect its answer and produce a response that an evaluator can assess. These requirements need not improve together. A shorter prompt can reduce input consumption while eliciting more output; a response can preserve expected field values while violating ordering requirements; an inexpensive response can still be unacceptable to its consumer.

The [Prompt Performance research program](../../README.md) treats performance as observed task fulfillment rather than an intrinsic property of a notation. This study applies that distinction to five AgMark run reports and their retained evidence. It asks whether the treatment rankings remain consistent across accuracy, exact-result agreement, token use and timing proxies, and whether observed discrepancies correspond to construction problems documented in the separate [historical refinement study](../ArcGrav_ARB_Trials/README.md).

This study contributes a reproducible comparison with explicit aggregation rules to the [Studies collection](../README.md). Format sensitivity documented by Sclar et al. (2024) motivates examining complete prompt formulations rather than assuming that a format label determines performance. Prompt optimization research, including Pryzant et al. (2023), likewise motivates preserving the distinction between a selected formulation's observed results and the effect of its individual edits.

## Research question and scope

In plain language, **prompt performance** is how well a model's response meets the task's requirements under specified execution conditions. Here it is operationalized through the registered field-accuracy score, the scorer's exact-result companion, retained token counters and duration-derived timing proxies. Each measurement captures a separate performance dimension. Confidence labels inside the benchmark output are prescribed task values, not estimates of the model's probability of correctness.

The primary comparison concerns five fixed treatment texts: `arb-arcgrav`, `arb-common-prose`, `arb-markdown`, `arb-xml` and `arb-yaml`. The analysis correlates evidence by generation, treatment and observation: scores identify discrepancies, retained counters identify resource use, and accepted plans identify the text and execution boundary.

## Dataset and methods

### Retained runs and execution conditions

The dataset contains five accepted generations of benchmark `arcgrav.authority-resolution.benchmark.core` version 2.0.0, case set version 1.0.0 and comparison track `arcgrav.authority-resolution.field-accuracy`. All runs use `gpt-5.6-luna` with low reasoning. Each contains five treatments, the same single case and ten repetitions per treatment. All 250 planned observations completed and were scored, with no failed, missing, excluded or non-scorable observations. Post-treatment validation evidence is excluded from the original-run results.

Table 1 identifies runs in execution chronology. Times are the earliest and latest recorded attempt starts, not run completion times. Every observation has one attempt, and the 250 attempt starts are distinct. Observation identifiers recur across generations because they identify the same planned treatment/case/repetition combinations; the correct cross-run key includes the generation.

**Table 1. Retained run identifiers and attempt-start ranges on 5 November 2026, UTC.** Each run contributes 50 observations.

| Run | Generation prefix | First attempt start | Last attempt start | ArcGrav field accuracy | Common prose field accuracy | Markdown field accuracy | XML field accuracy | YAML field accuracy |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| R1 | `4ea77c4be355` | 17:11:11 | 17:25:39 | 100.0000% | 99.5833% | 100.0000% | 100.0000% | 96.5517% |
| R2 | `e9e3e53a556a` | 17:30:19 | 17:45:13 | 100.0000% | 99.7917% | 100.0000% | 100.0000% | 100.0000% |
| R3 | `2f4eaa54d275` | 17:47:18 | 18:01:36 | 98.8889% | 99.7917% | 100.0000% | 100.0000% | 98.1132% |
| R4 | `8c198165d61b` | 18:03:59 | 18:18:04 | 99.7917% | 99.7917% | 100.0000% | 100.0000% | 100.0000% |
| R5 | `1c0c6542f5be` | 18:41:47 | 18:56:21 | 100.0000% | 99.5833% | 99.5833% | 100.0000% | 98.5185% |

The accepted plans preserve identical treatment hashes, benchmark and case identities, and execution-boundary fingerprints across the five generations. They enable randomized treatment starts and randomization per iteration. Retained execution evidence records fresh processes and work directories and no reuse of prior observation context, while session homes are reused.

### Task and treatment content

The case contains four source-record occurrences under three IDs and two relations. Authority-ranked selection must preserve a supported field even when a sibling field is unresolved. The expected result contains three records, five findings, one uncertainty entry and execution metadata. Conflict reporting, missing-value reporting, instruction-like source text and relation construction exercise distinct output obligations.

The accepted plans embed each treatment's bytes and hash. ArcGrav is 9,559 bytes; common prose, 33,048; Markdown, 30,802; XML, 38,704; and YAML, 35,788. The comparison evaluates these complete formulations, with representation and length varying together.

### Aggregation and evidence linkage

Scores are read from retained `score.json` artifacts rather than reconstructed from rounded report percentages. Let `C` denote correctly matched expected field units, `G` the number of expected units and `E` unexpected output units. The registered observation score is:

```math
s_{rti}=\frac{C_{rti}}{G_{rti}+E_{rti}},\qquad
\bar{s}_{t}=\frac{1}{5}\sum_{r=1}^{5}\left(\frac{1}{10}\sum_{i=1}^{10}s_{rti}\right).
```

Here `r` indexes runs, `t` treatments and `i` repetitions. All observations have `G=48`: eighteen record fields, twenty-five finding fields, one uncertainty entry and four execution fields. Unexpected units can enlarge the denominator. The registered reducer averages repetition scores within each case, then weights cases equally. With one case and ten observations per treatment in every run, the cross-run mean also equals the mean of 50 observation scores. It is not the ratio of pooled correct and total field counts.

Token totals sum retained observation counters; per-observation means divide those totals by 50. Relative reductions use the comparator treatment as denominator: `(comparator − ArcGrav) / comparator`. Timing means average available observation measurements. All observations supply the reported proxies, while none supplies direct TTFT or direct TBT.

## Measurements

**Field accuracy** compares typed JSON field values, matching records by exact ID and findings by ID and occurrence. Missing or incorrect fields lose their own credit; unexpected units penalize the denominator. Record and finding order are diagnostic rather than primary-score components, while uncertainty positions are scored. Whitespace and object-key order are immaterial. The output's `execution.validated` is one compared field, not an independent acceptance gate.

**Exact-result agreement** is the retained `exact_result_match` companion. It is reported alongside, not substituted for, field accuracy. It must also be distinguished from the historical study's stricter complete-visible-response acceptance contract, which includes delivery-envelope requirements.

**Resource consumption** uses input, uncached input, output and total token counters. Reasoning tokens are already included in output tokens, and cached tokens are already included in input. Adding either subset again would double-count consumption. Uncached input is input minus eligible cached input; cache-read fraction is the ratio of summed cached input to summed input. These are retained execution counters, not treatment-file tokenizations or billing records.

**Timing proxies** use retained item durations. The inference-duration proxy combines paired reasoning-item and agent-message-item durations. The TTFT proxy uses reasoning-item duration, not request-to-first-token time. The TBT proxy divides agent-message-item duration by output tokens minus one, rather than measuring actual inter-token intervals. Because the output counter includes reasoning tokens, changes in its composition can affect this proxy without establishing faster visible-token delivery.

## Results

### Accuracy and exact-result agreement differ

**Table 2. Cross-run correctness and mean retained consumption per observation.** Each treatment contributes 50 observations. Accuracy is the mean registered score; exact agreement is a count, not a field percentage. Token means include cached input and reasoning output where applicable.

| Treatment | Field accuracy | Exact-result agreement | Input tokens | Uncached input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ArcGrav | 99.7361% | 48/50 | 16,010.88 | 5,770.88 | 672.08 | 16,682.96 |
| Common prose | 99.7083% | 44/50 | 19,869.80 | 9,629.80 | 633.92 | 20,503.72 |
| Markdown | 99.9167% | 48/50 | 19,882.52 | 9,642.52 | 635.52 | 20,518.04 |
| XML | 100.0000% | 50/50 | 20,921.72 | 10,681.72 | 637.96 | 21,559.68 |
| YAML | 98.6367% | 43/50 | 20,216.96 | 9,976.96 | 644.62 | 20,861.58 |

XML has the highest observed accuracy and exact-result agreement. ArcGrav and Markdown each have two non-exact results, but their errors have different magnitudes under field scoring. Prose has six non-exact results yet a mean field score close to ArcGrav's. These measures therefore answer different questions: how much scored content is correct, and how often the scorer considers the entire result an exact match.

Four YAML observations score 100% while failing the exact-result companion because of ordering diagnostics. Field accuracy alone hides these ordering deviations.

### Input reduction exceeds output overhead

**ArcGrav has the lowest total and uncached input token counts in every retained run.** Across all runs, its total is 834,148 tokens, versus 1,025,186 for prose, 1,025,902 for Markdown, 1,077,984 for XML and 1,043,079 for YAML. The corresponding reductions are 18.63%, 18.69%, 22.62% and 20.03%. Uncached input reductions are 40.07%, 40.15%, 45.97% and 42.16%.

The savings arise on the input side. ArcGrav emits the most output tokens on average, including 254.54 reasoning tokens per observation, compared with 217.38 for prose, 218.52 for Markdown, 220.96 for XML and 226.38 for YAML. Its input reduction more than offsets this output increase in the retained total counter.

Every treatment has 512,000 cached input tokens summed over its 50 observations. ArcGrav's higher aggregate cache-read fraction therefore reflects its smaller input denominator. The larger percentage reduction in uncached input than in total tokens also follows from removing the same cached-input amount from different input totals.

### Timing does not follow the token ranking

**Table 3. Mean duration-derived timing proxies, milliseconds per observation.** Direct TTFT and direct TBT are unavailable for all 250 observations.

| Treatment | Inference-duration proxy | TTFT proxy | TBT proxy |
| --- | ---: | ---: | ---: |
| ArcGrav | 12,134.96 | 4,776.90 | 11.026741 |
| Common prose | 11,619.70 | 3,956.66 | 12.184244 |
| Markdown | 11,572.12 | 4,065.48 | 11.930428 |
| XML | 11,467.68 | 3,975.36 | 11.870936 |
| YAML | 11,957.34 | 4,370.60 | 11.892783 |

ArcGrav has the highest pooled inference-duration and TTFT proxies despite the lowest token total. It has the lowest pooled TBT proxy, but the per-run minimum varies. Its token reduction is not accompanied by a consistent timing advantage. No tool calls, distinct tool identities or failed tool calls are recorded in these runs, so tool activity does not account for the observed differences.

### Discrepancies connect metrics to output obligations

Three retained examples show why a small number of imperfect outputs can produce different treatment means:

- In R3, ArcGrav repetition 1 preserves all 48 expected units but duplicates the otherwise correct `item_1` record, adding six unexpected units. Its score is `48/54 = 88.8889%`; its schema diagnostic is invalid. Correct expected content does not establish correct collection membership.
- In R4, ArcGrav repetition 5 sets `item_1` authority to `mixed` instead of `A` at `/records/0/authority`, with 47 correct units and no extras. Its score is `47/48 = 97.9167%`. This is a metadata discrepancy rather than the extra-record error in R3.
- In R1, YAML repetition 9 has 38 correct units and ten unexpected units. Two expected relation findings are missing and two unexpected findings appear, yielding `38/58 = 65.5172%`. A wrong finding identity can lose expected credit and add unexpected units in the same response.

These examples show how output discrepancies determine field scores.

## Interpretation

### Separate fidelity, construction and cost

The observed frontier depends on the outcome of interest. XML supplies the highest measured fidelity but consumes the most total tokens. ArcGrav consumes the fewest tokens while producing two non-exact results and the highest pooled duration proxy. Markdown matches ArcGrav's exact-result count with a higher field mean and higher token consumption. The preferred formulation depends on the performance measure.

Deployment decisions should weigh error tolerance, ordering requirements, prices and measured latency.

### Relationship to the historical refinement observations

The historical [ArcGrav ARB trials](../ArcGrav_ARB_Trials/README.md) contain 407 completed strict-response trials across 57 tested prompt hashes, with 236 passes and 171 failures. Their eight thematic analyses are views of one adaptive series. They provide a separate comparison of error types.

The current extra-record and relation-finding discrepancies correspond to the distinction between [collection membership and component correctness](../ArcGrav_ARB_Trials/Collection_Membership_Multiplicity_and_Order.md). The authority discrepancy corresponds to the separation between [selected field values and derived metadata](../ArcGrav_ARB_Trials/Reference_Binding_and_Independent_Decisions.md). The YAML order-only results reinforce the need to distinguish [content and rendering obligations](../ArcGrav_ARB_Trials/Evidence_Assembly_and_Exact_Rendering.md).

Historical trial 310 also illustrates why the historical and current endpoints must remain separate: its extracted JSON matched the expected object, but additional assistant text violated complete-response acceptance. The historical 58.0% strict-pass rate and the current field scores measure different acceptance requirements.

### Tests suggested by the findings

A controlled extension should vary representation and length separately while preserving task-relevant content. A useful design would cross concise and expanded formulations with several notations, use held-out cases and verify semantic equivalence before evaluating outcomes. Cases should discriminate missing fields, duplicate occurrences, equal-rank conflicts, relation identity and ordering, rather than repeatedly expose only the current fixture.

Correctness should retain both partial-credit and consumer-acceptance outcomes. Timing should capture request starts and actual token timestamps; cost should use applicable prices and cache treatment. Multiple models and reasoning settings would test transfer. These experiments would distinguish a formulation-specific input reduction from a general syntax benefit and determine whether any resource advantage persists under stricter correctness requirements.

## Scope

The results describe repeated executions on one case, one model and one reasoning setting. Representation and prompt length vary together, so the comparison does not isolate syntax effects. Timing uses item-duration proxies, and token counts measure consumption rather than billed cost.

## Conclusion

The retained AgMark evidence separates three outcomes that a single performance label would obscure: near-ceiling but unequal correctness, a consistent input-driven token reduction for the compact ArcGrav formulation, and timing proxies that do not share its token ranking. Evaluating prompt performance requires preserving these distinctions and relating discrepancies to specific output obligations. Controlled representation-and-length comparisons on new cases are the next test of whether these observed tradeoffs transfer.

## Data and Reproducibility

The five original Markdown reports and `.agmark` archives are retained under `Data/`. The archives are ZIP containers. Full report and generation identities are available through these source reports:

- [R1 report, generation 4ea77c4be355](./Data/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d/report.md) · [retained archive (.agmark)](./Data/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d.agmark).
- [R2 report, generation e9e3e53a556a](./Data/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0/report.md) · [retained archive (.agmark)](./Data/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0.agmark).
- [R3 report, generation 2f4eaa54d275](./Data/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7/report.md) · [retained archive (.agmark)](./Data/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7.agmark).
- [R4 report, generation 8c198165d61b](./Data/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e/report.md) · [retained archive (.agmark)](./Data/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e.agmark).
- [R5 report, generation 1c0c6542f5be](./Data/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e/report.md) · [retained archive (.agmark)](./Data/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e.agmark).

For each archive, inspect `{generation}/accepted-plan/plan.json` for content bytes, hashes and execution settings; `{generation}/score-*/score.json` for primary and companion scores; and `reports/{generation}/canonical-evidence.json` for joined observation measurements and provenance. The field-accuracy registration is retained under `{generation}/reporting-authority/metric-registrations/099c90659beb22a311462b2bb8fb13cc1920402135516d5a26f3d89e8123bdc2.json`. Each checked-out report now links directly to its retained `.agmark` archive, which contains the original Markdown report and the three supporting JSON files under `reports/{generation}/`. These JSON files are ZIP members rather than adjacent loose files; download/open the archive to inspect them.

The five retained archives contain the original score artifacts, accepted plans, machine-readable reports and canonical evidence. A standalone reproduction script and a derived-summary JSON file are not currently included in this repository. The following standard-library example recomputes the registered field-score means and exact-result counts directly from the archived `score.json` files; run it from the repository root:

```text
from collections import defaultdict
from pathlib import Path
from statistics import mean
from zipfile import ZipFile
import json

data = Path("Research/Prompt_Performance/Studies/AgMark_Runs/Data")
field_by_treatment = defaultdict(list)
exact_by_treatment = defaultdict(int)

for archive in sorted(data.glob("generation-*/*.agmark")):
    generation = archive.stem
    within_run = defaultdict(list)
    with ZipFile(archive) as package:
        score_names = [
            name for name in package.namelist()
            if name.startswith(f"{generation}/score-") and name.endswith("/score.json")
        ]
        assert len(score_names) == 50, (generation, len(score_names))
        for name in score_names:
            score = json.loads(package.read(name))
            treatment = score["treatment_id"]
            companions = {entry["name"]: entry["value"]
                          for entry in score["companion_values"]}
            within_run[treatment].append(float(score["value"]))
            exact_by_treatment[treatment] += int(companions["exact_result_match"])
    assert len(within_run) == 5
    for treatment, scores in within_run.items():
        assert len(scores) == 10, (generation, treatment, len(scores))
        field_by_treatment[treatment].append(mean(scores))

assert len(list(data.glob("generation-*/*.agmark"))) == 5
for treatment, run_means in sorted(field_by_treatment.items()):
    assert len(run_means) == 5
    print(f"{treatment}: {100 * mean(run_means):.4f}% field accuracy; "
          f"{exact_by_treatment[treatment]}/50 exact results")
```

To reproduce token and timing summaries, join each generation's accepted observations with the corresponding `reports/{generation}/canonical-evidence.json` archive member and its retained measurement roles. Use unrounded scores, sum compatible token counters without double-counting cached input or reasoning output, and keep direct timing measurements separate from derived proxies. Cross-run keys must include generation and observation ID; post-treatment validation is not part of the original-run results. Table 1 truncates timestamps to seconds for display; sources retain fractional seconds. Numerical tables round only after aggregation. The original reports inside the archives and the archives themselves remain unchanged; only the checked-out Markdown report copies have GitHub-friendly data links.

## Related Papers

- [Prompt Performance](../../README.md) owns the broader research object and performance dimensions.
- [Prompt Construction Principles](../../Prompt_Construction_Principles.md) develops task-conditional construction principles.
- [ArcGrav ARB prompt-refinement trials](../ArcGrav_ARB_Trials/README.md) preserve the separate historical study and thematic analyses.
- [Instructional Representation](../../../Instructional_Representation.md) distinguishes instruction structure from executable semantics.
- [ArcGrav Interpretive Efficiency](../../../ArcGrav_Interpretive_Efficiency.md) addresses the cost of recovering meaning from a representation.

## References

- Pryzant, R., Iter, D., Li, J., Lee, Y., Zhu, C., & Zeng, M. (2023). *Automatic Prompt Optimization with “Gradient Descent” and Beam Search*. Proceedings of EMNLP. https://aclanthology.org/2023.emnlp-main.494/.
- Sclar, M., Choi, Y., Tsvetkov, Y., & Suhr, A. (2024). *Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design or: How I learned to start worrying about prompt formatting*. ICLR 2024. https://arxiv.org/abs/2310.11324v2.
