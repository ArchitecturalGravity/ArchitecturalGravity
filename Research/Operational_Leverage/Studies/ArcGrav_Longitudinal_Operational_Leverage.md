<a id="paper-operational-longitudinal"></a>
# ArcGrav Codex Operational Leverage Across Longitudinal Usage

## Abstract

This observational study measures changes in downstream agent activity per unit of human-authored specification during sustained ArcGrav use. Session-level Codex telemetry from February 26 through August 17, 2026 includes 1,164 sessions and 6,038 user prompts, spanning pre-ArcGrav operation through notation development and mature use. The primary comparison fixes model (GPT-5.4) and reasoning setting (`xhigh`) and contrasts the first and last 15 active days in that cohort. User characters per prompt decline from approximately 2,259 to 581 (74.3%), while tool calls per prompt increase 11.3%. Tool calls per 1,000 user characters rise from 7.38 to 31.95 (4.33×); other activity measures increase 4.07×–4.44×. The active-day bootstrap supports the tool-leverage increase across different day compositions. The repository chronology places most general-purpose notation before the late window and identifies growing authoring fluency as a candidate mechanism. The central finding is specification compression with preserved downstream computational activity.

## Introduction

One instruction can trigger repeated context processing, reasoning, repository inspection, tool execution, validation, tests, recovery, and autonomous continuation. Prompt length alone therefore cannot describe the resulting workload.

Human cost can include writing time, repeated detail, clarification, corrective turns, task decomposition, state reconstruction, observation, and intervention. A representation can therefore be useful even if it is not token-minimal, provided it reduces human effort while preserving successful execution.

Operational activity leverage describes how much downstream model and tool activity is activated by a given amount of human-authored instruction. This study examines the relationship between human-authored specification and downstream agent activity under fixed model and reasoning settings during sustained ArcGrav use. Its primary contribution is the measured change in activity per unit of human-authored text.

## Role Within the Research Program

This paper measures longitudinal activity leverage during sustained ArcGrav usage. It complements the [single-workstream comparison](./ArcGrav_Single_Workstream_Delegation_Leverage.md) and uses the [external operational baseline](../../Agentic_Software_Engineering_Operational_Baseline.md) for broader context.

## Study scope and operational leverage

### Operational activity leverage

This study measures tool and inference activity against estimated human-authored characters.

The research-program taxonomy separating serialization, compositional, interpretive, and operational efficiency is defined in the [Research README](../../README.md). This paper starts at the final level: the human-agent system.

Across this dataset, 2.708 billion input tokens were processed, including 2.482 billion cached tokens, while estimated user-authored text totals about 10.55 million characters. These quantities track different sides of the workflow: human specification and model-side context processing.

### Human specification versus model computation

Prompt-token efficiency and operational leverage can move independently: a representation may spend slightly more local tokens while reducing repeated instruction, decomposition, clarification, correction, or state reconstruction, while a token-minimal prompt can still have poor operational leverage if it requires frequent repair.

The desired measure is successful autonomous work divided by human specification effort. Here, recorded tool calls, inference calls, uncached input, output, and reasoning output measure downstream activity.

Observation and intervention also contribute to human effort beyond the recorded prompt-text measure.

### Relationship to other ArcGrav research

[Syntax Efficiency](../../ArcGrav_Syntax_Efficiency.md), [Interpretive Efficiency](../../ArcGrav_Interpretive_Efficiency.md), [Semantic Locality](../../Context_Triad/Semantic_Locality.md), [Semantic Shadow](../../Context_Triad/Semantic_Shadow.md), and [Semantic Weight](../../Context_Triad/Semantic_Weight.md) study upstream representational properties. This paper extends the research program to system-level agent activity and relates that activity to the documented development of ArcGrav. Semantically matched representation comparisons are addressed elsewhere in the program.


### Principal empirical findings

The results establish six findings: substantial specification compression; preserved per-prompt computational activity; approximately fourfold greater activity leverage per user character; a largely mature ArcGrav operator inventory before the late comparison window; an association between higher reasoning effort and deeper computation; and a descriptive decline in prompts per session. Active-day sensitivity, caching, recorded non-success, and session-span analyses provide supporting context.

---

## Dataset and methods

### Source dataset

The source telemetry is committed with this document:

**[ArcGrav_Longitudinal_Codex_Telemetry.csv](./ArcGrav_Longitudinal_Codex_Telemetry.csv)**

| Measure | Value |
| --- | ---: |
| Date range | 2026-02-26 through 2026-08-17 |
| Active days | 115 |
| Session rows | 1,164 |
| Recorded user prompts | 6,038 |
| Tool calls | 65,507 |
| Input tokens | 2,708,146,676 |
| Cached input tokens | 2,482,104,576 |
| Uncached input tokens | 226,042,100 |
| Cached share of input | 91.65% |
| Output tokens | 21,875,404 |
| Reasoning-output tokens | 9,459,589 |
| Estimated user-authored characters | 10,546,290 |

Model distribution:

| Model | Session rows |
| --- | ---: |
| `gpt-5.3-codex` | 491 |
| `gpt-5.4` | 672 |
| `unknown` | 1 |

Reasoning-effort distribution:

| Reasoning effort | Session rows |
| --- | ---: |
| `low` | 250 |
| `medium` | 140 |
| `high` | 206 |
| `xhigh` | 567 |
| `unknown` | 1 |

The source records session-level aggregates.

### Operational ArcGrav exposure history

The telemetry begins before ArcGrav was realized. After realization, ArcGrav was used continuously through notation development and mature use. Repository commits date the availability and formalization of notation constructs, providing a maturity axis for the longitudinal analysis.

### Development chronology and ArcGrav maturity

Repository history supplies a maturity axis for interpreting the telemetry during continuous ArcGrav use. The following milestones record notation availability and documentation changes.

| Date | Documented notation state | Relation to telemetry |
| --- | --- | --- |
| Apr 27 | Early README state includes section/key-value structure, ordered lists, nested grouping, and symbolic referencing (`7abff205`). | Establishes the earliest documented core ArcGrav state after the pre-ArcGrav portion of the telemetry. |
| May 15 | Inline Aliasing (`AS`, `63a94d4`), Priority Lists (`P0.`, `4457714`), and Wildcarding (`*`, `037662e`) are added in a concentrated notation-expansion burst. | Main compositional expansion during continuous ArcGrav use. |
| May 26 | Literal Quote Block (`"""`, `3c9bed2`) is added. | Extends the mature compositional vocabulary before the primary fixed GPT-5.4/`xhigh` cohort. |
| Jun 3 | The GPT-5.4/`xhigh` longitudinal cohort begins; the README already contains priority, grouping, wildcarding, symbolic referencing, aliasing, and literal quoting. The same-day README revision also clarifies that symbolic references are invoked after creation (`82149fc`). | The controlled early window begins with most of the later general-purpose compositional vocabulary already present and in continuous use. |
| Jun 16 | Context Operation (`=>`, `2a13c03`) becomes a first-class operation construct. | Main general-purpose operator added inside the early Jun 3–24 comparison window. |
| Jul 29–30 | Syntax is decomposed and formalized into dedicated `Guide/Syntax/*` documents while the README retains substantially the same operator inventory. | Documentation formalization overlaps the late window without a comparable expansion in operator count. |
| Aug 8 | Explicit Block Binding is introduced (`60c1351`) and refined the same day to the current `↳` marker (`e0b9b19`). | Narrow scope-disambiguation refinement during the final mature-use period. |
| Aug 17 | Telemetry observation ends. | Final observed mature-ArcGrav state. |

The milestones define the following descriptive epochs:

| Epoch | Dates | ArcGrav state | Interpretive value |
| --- | --- | --- | --- |
| E0 | Feb 26–ArcGrav realization | Pre-ArcGrav | Operational baseline before ArcGrav becomes the continuous prompting method. |
| E1 | Earliest ArcGrav realization–May 14 | Core section/reference notation | Initial continuous-ArcGrav period and early authoring fluency. |
| E2 | May 15–25 | + `AS`, `P0.`, `*` | Main compositional-expansion epoch. |
| E3 | May 26–Jun 15 | + literal quote blocks | Mature compositional vocabulary before explicit context operations. |
| E4 | Jun 16–Aug 7 | + `=>` Context Operation | Long relatively stable-grammar interval for observing maturation and authoring fluency. |
| E5 | Aug 8–17 | + `↳` Explicit Block Binding | Final mature-ArcGrav epoch with a narrow binding refinement. |

Most general-purpose compositional constructs predate the controlled GPT-5.4/`xhigh` cohort or occur in its early window. The late endpoint begins after the introduction of Context Operation (`=>`). The interpretation below relates this chronology to the observed activity trend.

### Analysis cohorts

Prompt-normalized analyses exclude five rows with `prompt_count = 0` and one row with unknown model/reasoning. This leaves 1,158 prompt-valid, model-known session rows and 6,037 prompts.

The five zero-prompt rows still contain 139 tool calls, 3,072,398 input tokens, 50,373 output tokens, and 26,078 reasoning-output tokens. They remain in whole-dataset totals but are excluded when prompt or user-character denominators would be undefined.

The primary longitudinal cohort holds two major temporal covariates constant:

- model: `gpt-5.4`;
- reasoning effort: `xhigh`;
- date: June 3 through August 17, 2026;
- `prompt_count > 0`.

This cohort contains 423 session rows, 1,238 prompts, 22,473 tool calls, and 50 active days.

The endpoint comparison uses equal active-day windows:

- **Early:** first 15 active days, June 3–24;
- **Late:** final 15 active days, July 24–August 17.

Active days are used so days with no observed usage are not treated as zero-activity observations.

Reasoning-effort comparisons use prompt-weighted aggregates from the prompt-valid dataset. A sensitivity comparison also matches `high` and `xhigh` observations on the same model and active day; 14 model/day combinations meet this condition.

For the early-versus-late comparison, an exploratory cluster bootstrap resamples active days within each window for 20,000 replicates. The resulting intervals measure sensitivity to the observed day composition.

The fixed GPT-5.4/`xhigh` endpoint comparison holds model and selected reasoning effort constant. The repository chronology provides the notation-maturity context used in the results and interpretation.

---

## Measurements

### Derived activity measures

Estimated user-authored characters for each session are `prompt_count` multiplied by `average_characters_per_prompt`. Uncached input tokens are `input_tokens` minus `cached_input_tokens`.

**Activity leverage** measures downstream activity per 1,000 estimated user-authored characters. For tool calls, the calculation is:

```math
L_{\text{tool}} = \frac{\text{tool calls}}{H/1000}
```

Here `H` is the estimated user-authored character count. Inference calls, uncached input tokens, output tokens, and reasoning-output tokens are normalized in the same way.

---

## Results

### Human specification burden fell 74.3%

**Table 1. Endpoint changes in the fixed GPT-5.4/`xhigh` cohort.**

| Metric | Early: Jun 3–24 | Late: Jul 24–Aug 17 | Change |
| --- | ---: | ---: | ---: |
| Session rows | 98 | 164 | +67.3% |
| User prompts | 359 | 473 | +31.8% |
| User characters / prompt | 2,259 | 581 | −74.3% |
| Total user-authored characters | 811,016 | 274,783 | −66.1% |
| Prompts / session | 3.66 | 2.88 | −21.3% |
| Total tool calls | 5,986 | 8,779 | +46.7% |
| Tool calls / prompt | 16.67 | 18.56 | +11.3% |
| Inference calls / prompt | 7.77 | 8.87 | +14.1% |
| Uncached input / prompt | 46.2k | 48.4k | +4.6% |
| Output / prompt | 6.34k | 6.65k | +5.0% |
| Reasoning output / prompt | 3.08k | 3.34k | +8.1% |
| Recorded tool non-success rate | 4.14% | 6.71% | +2.57 pp |
| Aborted turns / prompt | 0.120 | 0.101 | −15.3% relative |
| Mean recorded session span | 75.2 min | 43.1 min | −42.7% |

Under the same GPT-5.4 model and `xhigh` reasoning setting, user-authored characters per prompt fell from 2,259 to 581 (−74.3%). Total user-authored text across the endpoint windows fell 66.1%, even as the number of recorded prompts increased 31.8%.

### Downstream computational activity was preserved per prompt

Table 1 also shows that shorter prompts continued to activate comparable downstream computation. Tool calls per prompt increased from 16.67 to 18.56 (+11.3%), and inference calls from 7.77 to 8.87 (+14.1%). Uncached input, output, and reasoning output per prompt increased 4.6%, 5.0%, and 8.1%, respectively. The central pattern is preserved computational activity alongside sharply reduced human specification.

<a id="ol-specification-compression"></a>
### Specification-normalized activity increased approximately fourfold

In the fixed-cohort comparison, **each unit of human-authored specification was associated with approximately four times as much downstream model and agent activity in the late period as in the early period**.

**Table 2. Downstream activity per 1,000 estimated user-authored characters.**

| Activity per 1,000 user characters | Early | Late | Ratio |
| --- | ---: | ---: | ---: |
| Tool calls | 7.38 | 31.95 | 4.33× |
| Inference calls | 3.44 | 15.27 | 4.44× |
| Uncached input tokens | 20.46k | 83.24k | 4.07× |
| Output tokens | 2.81k | 11.45k | 4.08× |
| Reasoning-output tokens | 1.37k | 5.74k | 4.20× |

The increase is driven primarily by a **3.89× reduction in user characters per prompt** (`2259 / 581`) with broadly preserved per-prompt model and tool activity. The result is **specification compression with preserved computational activation**.

### General-purpose ArcGrav notation was substantially mature by the late window

The development chronology above places section/group structure, symbolic references, aliasing, priority lists, wildcarding, and literal quote blocks before the June 3 start of the fixed cohort. Context Operation (`=>`) was added on June 16, within the early endpoint window. By July 24, the opening of the late window, most general-purpose constructs were already available. Later changes primarily formalized syntax documentation and refined explicit block binding. The observed late-period compression therefore occurred after the principal notation expansion.

### Reasoning effort is associated with deeper computational activity

Across the prompt-valid dataset:

| Effort | Sessions | Uncached input / prompt | Output / prompt | Reasoning / prompt | Reasoning share | Tools / prompt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `low` | 250 | 20.9k | 1.41k | 0.33k | 23.3% | 5.83 |
| `medium` | 139 | 35.0k | 2.80k | 0.94k | 33.4% | 8.88 |
| `high` | 206 | 41.4k | 3.68k | 1.54k | 41.8% | 11.91 |
| `xhigh` | 563 | 50.9k | 5.92k | 2.97k | 50.1% | 15.61 |

Model-specific reasoning shares show the same broad ladder:

| Effort | GPT-5.3 Codex | GPT-5.4 |
| --- | ---: | ---: |
| `low` | 23.3% | 23.1% |
| `medium` | 32.9% | 34.5% |
| `high` | 45.5% | 37.9% |
| `xhigh` | 49.5% | 50.2% |

Reasoning policy also changed strongly over time:

| Month | `xhigh` share of valid sessions |
| --- | ---: |
| February | 0.0% |
| March | 29.9% |
| April | 6.8% |
| May | 13.5% |
| June | 77.1% |
| July | 92.8% |
| August | 100.0% |

This is why the primary longitudinal comparison fixes reasoning effort.

In the 14 model/day combinations containing both `high` and `xhigh`, the median model/day `xhigh / high` ratios are:

| Measure | Median ratio |
| --- | ---: |
| User characters / prompt | 0.90× |
| Uncached input / prompt | 1.79× |
| Output / prompt | 1.82× |
| Reasoning output / prompt | 1.94× |
| Tools / prompt | 1.44× |
| Inference calls / prompt | 1.32× |

The matched-day comparison supports the descriptive reasoning-effort profile.

### Recorded conversational steering declined

Prompts per session declined from 3.66 to 2.88 (−21.3%) across the fixed-cohort endpoint windows (Table 1). This descriptive reduction accompanies shorter prompts and sustained downstream execution. The active-day bootstrap interval for prompts per session includes no change, so the strongest finding remains specification compression and normalized activity leverage.

### Active-day bootstrap sensitivity

The 20,000-replicate active-day cluster bootstrap gives:

| Measure | Observed change | 95% bootstrap interval |
| --- | ---: | ---: |
| User characters / prompt | −74.3% | −82.3% to −56.7% |
| Tool calls / 1,000 user characters | +332.9% | +93.9% to +746.1% |
| Recorded tool non-success rate | +2.57 pp | +1.27 to +3.63 pp |

The prompt-length reduction and increase in tool activity per user character are not driven by one active day in these windows.

Intervals for per-prompt activity, prompts per session, and session span include zero, while specification compression and specification-normalized activity show the clearest separation.

### Supporting result — Cached context dominates input processing

Across the complete dataset:

- Total input: **2.708 billion tokens**
- Cached input: **2.482 billion**
- Uncached input: **226.0 million**
- Cached share: **91.65%**

Raw `input_tokens` primarily reflect agent context processing and reuse; human-authored text is measured separately.

For this study it is useful to distinguish:

- **Interaction Burden:** human specification and steering
- **Inference Burden:** model-side processing and generation
- **Execution Burden:** tool use and external operations

Representation-level serialization and interpretation costs are analyzed in the upstream research papers rather than redefined here.

Further context on caching and current-rate cost normalization appears in the appendix.

### Supporting result — Recorded non-success and aborted turns

Across endpoint windows, `turn_aborted` per prompt falls from 0.120 to 0.101, while `tool_failure_count / tool_call_count` rises from 4.14% to 6.71%. Within the GPT-5.4/`xhigh` June–August cohort, the session-level Spearman correlation between average user characters per prompt and recorded tool non-success is weak (`ρ ≈ -0.08`).

The non-success field combines heterogeneous events without cause labels. It measures recorded events rather than terminal task failures.

### Supporting result — Session span and continuation

Mean recorded session span falls from 75.2 to 43.1 minutes, although the field contains extreme outliers and can include idle time. Direct timing fields are available for 111 sessions from August 10–17.

Five zero-prompt rows contain substantial recorded activity and remain outside prompt-normalized comparisons. A continuation indicator would distinguish resumed execution from session-boundary artifacts.

---

## Interpretation

### Specification compression with preserved agent activity

The results show a shift in the relationship between human expression and agent execution: smaller specifications continued to mobilize comparable per-prompt tool use, inference, and generation. This **specification compression with preserved computational activation** is the defining operational pattern measured in the study.

### From notation construction to operational fluency

The ArcGrav chronology gives the longitudinal result a mechanism-level interpretation. Sections, nested groups, symbolic references, aliases, priorities, wildcarding, and literal quote blocks were already documented when the fixed GPT-5.4/`xhigh` cohort began on June 3. Context Operation (`=>`) arrived on June 16, within the early comparison window. By the July 24 start of the late window, most general-purpose notation was in place; the remaining milestones chiefly formalized the documentation and clarified block binding. The sequence is better described as **notation construction → operationalization → increasing authoring fluency and specification compression** than as **more operators → more leverage**.

The proposed operational mechanism is compositional delegation. Sections and nested groups carry scope and constraints; references and aliases reuse established context; priorities and wildcarding express ordering and target sets; and Context Operation applies operations to that context. With practice, an author can combine these constructs into a compact, coherent work packet instead of restating context or spelling out each execution step. The agent can then perform sustained reasoning and tool execution from a smaller human-authored specification. This connects ArcGrav's representational design to the observed combination of shorter prompts and preserved downstream activity.

The relatively stable-grammar interval from June 16 through August 7 (E4) is especially informative. It allows a follow-up comparison of specification compression and activity leverage while the available general-purpose operator inventory changes relatively little. Continued improvement within that interval would support an authoring-fluency explanation over a simple feature-count explanation. Context Operation (`=>`) is the strongest individual operator candidate for prompt-level investigation because it adds a broad execution primitive; the later explicit block-binding refinement (`↳`) addresses a narrower scoping problem.

### ArcGrav authoring fluency versus general Codex expertise

**ArcGrav authoring fluency** is the learned ability to express intent economically using its scopes, references, composition, and operations. **General Codex expertise** includes task sizing, repository familiarity, tool-use expectations, feedback management, and supervision practices that improve with experience regardless of prompt representation. Both develop through repeated use, but they describe different sources of operational improvement.

ArcGrav-mediated fluency is a potential mechanism of the notation's leverage, not merely a generic operator-learning effect to subtract from the analysis. General Codex expertise is a separate influence that can also reduce specification burden. Prompt-level construct labels, stable-grammar comparisons, and matched work under common model and reasoning settings would help distinguish better use of ArcGrav from broader Codex experience.

### Further evaluation

Three questions define the next stage of measurement:

- How much of the observed activity-leverage increase arises from ArcGrav representation and authoring fluency, distinct from general Codex experience and task mix?
- How does activity leverage translate into accepted engineering outcomes, accounting for review, correction, and rework?
- Under matched tasks, how do supervision, autonomous recovery, and end-to-end completion time change with the prompting representation?

## Scope and Evidence Status

The fixed GPT-5.4/`xhigh` cohort establishes a 74.3% reduction in user characters per prompt and 4.07×–4.44× more downstream activity per estimated human character. Operational history places this change during sustained ArcGrav use; repository history dates notation maturation. The session-level telemetry lacks prompt-level syntax labels, task acceptance, and human supervision time. Task mix, general Codex expertise, repository familiarity, and service changes may also vary over time. The result therefore establishes longitudinal activity leverage and association, not an isolated ArcGrav causal effect or accepted-work productivity estimate. Session span and rate-card-normalized credits are descriptive, not direct execution-time or historical billing measures.

## Conclusion

Within a fixed-model, fixed-reasoning longitudinal cohort, shorter human-authored prompts activated broadly comparable downstream activity, producing a 4.07×–4.44× increase in measured activity per unit of user text. The notation-maturity chronology identifies authoring fluency as a focused mechanism for direct evaluation.

## Appendix: Cached context and cost normalization

Economic cost depends on the mix of uncached input, cached input, and output tokens. For GPT-5.3-Codex and GPT-5.4, cached input is priced at one tenth of uncached input. See the [Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card).

Including output, this dataset records **2.730 billion raw model tokens**, while **91.65% of input is cached**. Applying the current token-based rate card to the observed model/token mix gives approximately **34.1k credits**, compared with about **156.9k credits** if the same input volume were uncached—a **78.3% reduction** from cache reuse. These figures use the current rate card to normalize historical token counts.

Comparable public Codex telemetry shows the same high-cache pattern:

| Workload | Raw tokens | Cached share of input | Context |
| --- | ---: | ---: | --- |
| This study | 2.730B | 91.65% | 1,164 session rows across 115 active days; sustained longitudinal workload |
| [Public 118.16M-token report](https://www.reddit.com/r/codex/comments/1v3c19s/i_used_118m_codex_tokens_in_one_day_and_consumed/) | 118.16M | 97.3% | One-day high-intensity workload |
| [OpenAI Codex issue #38367](https://github.com/openai/codex/issues/38367) | 33.15M | 93.6% | 41-minute mixed-model workload |
| [OpenAI Codex issue #34971](https://github.com/openai/codex/issues/34971) | 2.517B | 96.07% | Regression dominated by repeated large-context processing and tool-loop recovery |

The public comparisons show similarly high cache shares in other Codex workloads. Repeated cached-context processing can also generate extensive activity in unproductive loops, so cache share alone does not measure execution efficiency.

This supports the study's use of **uncached input**, output, reasoning output, inference calls, and tool calls rather than total input tokens in the primary leverage analysis. The approximately fourfold result is not mechanically produced by the 2.482 billion cached-input tokens.

## Data and Reproducibility

- [Longitudinal Codex telemetry CSV](./ArcGrav_Longitudinal_Codex_Telemetry.csv) — SHA-256 `8204a4e09da5929c839395b26dd9dd2966397ee1b6b141172cb3f5a4d0110769`.
- [Single-workstream operational study](./ArcGrav_Single_Workstream_Delegation_Leverage.md) — complementary observational design.
- [External SWE-rebench operating reference](../../Agentic_Software_Engineering_Operational_Baseline.md) — independent benchmark scale.

## Related Papers

- [Model-Native Structural Representation](../../Model_Native_Structural_Representation.md)
- [ArcGrav Syntax Efficiency](../../ArcGrav_Syntax_Efficiency.md)
- [ArcGrav Interpretive Efficiency](../../ArcGrav_Interpretive_Efficiency.md)
- [Single-Workstream Delegation Leverage](./ArcGrav_Single_Workstream_Delegation_Leverage.md)
- [Reasoning–Interaction Substitution](../../ArcGrav_Reasoning_Interaction_Substitution.md)

## Other Sources

- [OpenAI Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card) — rate-card-normalized cost discussion.
- [Public 118.16M-token usage report](https://www.reddit.com/r/codex/comments/1v3c19s/i_used_118m_codex_tokens_in_one_day_and_consumed/) — illustrative reported workload.
- [OpenAI Codex issue #38367](https://github.com/openai/codex/issues/38367) — reported context-processing workload.
- [OpenAI Codex issue #34971](https://github.com/openai/codex/issues/34971) — reported long-context/tool-loop workload.
