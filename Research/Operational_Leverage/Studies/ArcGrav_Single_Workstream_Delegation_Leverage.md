<a id="paper-operational-single-workstream"></a>
# ArcGrav Codex Operational Leverage in a Single Software Workstream Relative to an External Baseline

## Abstract

This observational study characterizes the operating regime of one continuous ArcGrav software feature-development workstream from August 25 through September 4, 2026. It compares 193 GPT-5.4/`xhigh` Codex sessions and 272 user prompts with 555 standardized delegation episodes from SWE-rebench July 2026. Sessions are treated as observational work-packet proxies, and the human-text denominator includes later steering prompts. Repository history documents implementation, integration, testing, refactoring, and rework within that persistent objective. The workstream recorded 13,483 tool calls and 265,415 estimated user-authored characters. Mean tool depth was 69.86 calls per session versus 20.29 in the external reference (3.44×), while tool calls per 1,000 human-authored characters were 50.80 versus 9.52 (5.34×). The 153 single-prompt sessions (79.3%) exhibit a similar contrast, and active-day resampling indicates that the aggregate is not driven by one intensive day. The finding characterizes a comparatively deep, sparsely steered execution regime, with tool activity as the measured outcome.

## Introduction

In agent-assisted software development, a human instruction can initiate an extended sequence of tool operations, with additional prompts used to steer work as it proceeds. **Delegation leverage** compares how much tool work an agent performs with how much human-authored task text was needed to direct it. Operational-leverage analysis asks how much downstream execution is mobilized by human specification and how much human steering is required while that work is executed.

This study examines one continuous ArcGrav feature-development workstream. Repository history records development of one persistent feature throughout the observation window. The measured activity occurs during implementation, integration, validation, performance work, refactoring, reversion, and revised implementation against one evolving software artifact. It encompasses exploration and rework alongside code generation. These are overlapping phases of a persistent engineering objective, not repeated trials of a homogeneous benchmark task. This persistent-project context is a defining characteristic of the observed workflow and differs from a collection of unrelated benchmark tasks.

**Primary question:** What operating regime does this single Codex software-engineering workstream occupy relative to an independent external Codex reference? The external comparison is primary; within-workstream temporal change serves as a secondary analysis. The comparison considers tool execution per episode, activity normalized by human-authored task text, and steering prompts per episode.

## Role Within the Research Program

This study characterizes tool-execution depth and human-text-normalized activity in one persistent ArcGrav software-development workstream. The [External Operational Baseline](../../Agentic_Software_Engineering_Operational_Baseline.md) provides a non-ArcGrav reference distribution, while the [longitudinal study](./ArcGrav_Longitudinal_Operational_Leverage.md) examines changes across sustained use.

## Research scope and comparison unit

### Delegation episode as the comparison unit

In SWE-rebench, one trajectory represents a single externally supplied software-engineering objective followed by autonomous execution until completion, submission, failure, or termination. For the observational workstream, one telemetry session is the closest available work-packet episode proxy, and subsequent user prompts within it are counted as steering interventions rather than new episodes.

The single-prompt subset provides the closest structural match to the benchmark's one-input episode design.

---

## Dataset and methods

### External Codex operational baseline

The external reference is documented in:

**[Agentic Software Engineering Operational Baseline](../../Agentic_Software_Engineering_Operational_Baseline.md)**

Its directly compatible Codex extraction is generated from the vendored SWE-rebench July 2026 trajectories:

**[codex_operational_baseline.csv](../../swe_rebench_07_2026_trajectories/codex_operational_baseline.csv)**

The reference contains:

```text
555 standardized Codex delegation episodes
111 tasks × 5 repeated runs
1,183,515 exact task-specification characters
11,262 normalized tool calls
20.29 tool calls / episode
9.5157 tool calls / 1,000 specification characters
19.71–20.94 tool calls / episode across runs
9.24–9.82 tool calls / 1,000 specification characters across runs
```

Every benchmark episode contains one exact externally supplied user task input. The external reference therefore has **1.00 user task input per episode**.

### Observational workstream telemetry

The source telemetry is committed with this study:

**[ArcGrav_Single_Workstream_Codex_Telemetry.csv](./ArcGrav_Single_Workstream_Codex_Telemetry.csv)**

| Measure | Value |
| --- | ---: |
| Date range | 2026-08-25 through 2026-09-04 |
| Active days | 9 |
| Session rows / observational episodes | 193 |
| User prompts | 272 |
| Model | GPT-5.4 |
| Reasoning effort | `xhigh` |
| Estimated user-authored characters | 265,415 |
| Tool calls | 13,483 |
| Inference calls | 6,712 |
| Uncached input tokens | 33.30M |
| Output tokens | 5.261M |
| Reasoning-output tokens | 2.674M |
| Cached share of input | 95.25% |

All 193 sessions contain at least one recorded user prompt.

### Workstream context

The work includes core feature implementation, data processing and application logic, application integration, interactive controls and state behavior, grouping/filtering/selection, deferred or incremental loading, presentation and layout work, performance improvements, automated component testing and test-infrastructure adaptation, reuse of existing components, cleanup and refactoring, reversion of an attempted implementation, revised implementation, and continued integration.

### Secondary within-workstream analysis

The full cohort contains nine active days.

A secondary endpoint comparison uses equal four-active-day windows:

- **Early:** August 25–28
- **Late:** September 1–4

The middle active day is excluded from that endpoint comparison.

A 20,000-replicate cluster bootstrap resamples active days to measure sensitivity to day composition. This analysis describes variation inside the workstream; it is not the primary baseline comparison.

---

## Measurements and comparability

### Operating measures

**Delegation depth** is agent activity per observational episode; **specification-normalized activity leverage** is activity per 1,000 estimated human-authored characters; and **steering density** is user prompts per episode. Tool invocations are the primary activity measure in the external comparison.

For tool-call activity, specification-normalized leverage is calculated as:

```math
\text{Tool leverage} = \frac{\text{Tool calls}}{\text{Human-authored characters}/1000}
```

For each session, estimated human-authored characters are `prompt_count` multiplied by `average_characters_per_prompt`. Uncached input tokens are total input tokens minus cached input tokens.

### Cross-dataset compatibility

Tool depth per episode and tool activity normalized by human-authored characters form the two common comparison axes. The tool-depth ratio divides observed tool calls per episode by the external reference of 20.29 calls per episode. The tool-leverage ratio divides observed tool calls per 1,000 user characters by the external reference of 9.5157 calls per 1,000 specification characters.

Tool invocations are directly comparable across the two telemetry sources; inference calls and token categories describe the observed workstream.

### Evidence provenance and comparison detail

Three evidence streams establish the external reference, observed activity, and sustained engineering context.

| Evidence stream | Observational unit | Human-text denominator | Tool activity / contribution |
| --- | --- | --- | --- |
| SWE-rebench July 2026 Codex trajectories | 555 benchmark episodes (111 tasks × 5 runs) | Exact Unicode code points in each externally supplied task input | Normalized `event.type == "tool_call"` events; independent reference |
| ArcGrav Codex telemetry | 193 sessions containing 272 user prompts | Estimated `prompt_count × average_characters_per_prompt` per session, including later steering prompts | Session-level `tool_call_count`; observed feature-development activity |
| Repository development history | Timestamped evolution of one feature and branch | No telemetry text denominator | Documents implementation, integration, testing, reversion, and revision; no session-to-commit mapping |

The benchmark records one externally supplied specification per episode. The observational study treats each session as a work-packet episode and counts all recorded user prompts—including later steering—toward its human-text denominator. Its 153 single-prompt sessions provide the closest structural match to the benchmark. Both telemetry systems count discrete tool invocations through separate instrumentation pipelines.

The observational bootstrap resamples active days for 20,000 replicates; the external range summarizes five benchmark runs. Repository history establishes the feature-development trajectory but does not assign individual commits or accepted changes to particular Codex sessions.

---

<a id="ol-single-workstream-observations"></a>

## Results

### Direct comparison with the external Codex reference

The primary external comparison is:

**Table 1. Primary operating-regime comparison (193 workstream sessions; 555 external episodes).**

| Operating dimension | External Codex reference | ArcGrav workstream | Observed / reference |
| --- | ---: | ---: | ---: |
| Tool calls / delegation episode | 20.29 | 69.86 | 3.44× |
| Human-authored characters / episode | 2,132.46 | 1,375.21 | 0.645× |
| User inputs / episode | 1.00 | 1.41 | 1.41× |
| Tool calls / 1,000 human characters | 9.5157 | 50.80 | 5.34× |

The workstream therefore occupies a materially different tool-execution regime from the standardized Codex reference.

Its average episode contains approximately **3.44 times as many tool calls**, while its measured human-authored text burden is approximately **64.5% of the external reference**. When tool execution is normalized by that human-text burden, the workstream produces approximately **5.34 times as many tool calls per 1,000 characters**.

The comparison is also well outside the five-run baseline range:

- Observed tool depth: **69.86 calls / episode**
- Highest external Codex run: **20.94 calls / episode**
- Observed depth relative to the highest run: approximately **3.34×**

and:

- Observed tool leverage: **50.80 calls / 1k characters**
- Highest external Codex run: **9.82 calls / 1k characters**
- Observed leverage relative to the highest run: approximately **5.17×**

The external comparison defines the operating-regime result; within-workstream endpoints are examined separately in the secondary within-workstream analysis below.

### Specification-normalized tool activity

The full workstream recorded 13,483 tool calls and 265,415 estimated user-authored characters, yielding **50.80 tool calls per 1,000 user characters**.

Against the external reference of 9.5157 calls per 1,000 task-specification characters, the ratio is 5.34×. This combines the deeper execution observed per episode with the smaller estimated user-text burden shown in Table 1.

### Steering density and the single-prompt subset

The 193 sessions contain:

- **153 single-prompt sessions (79.3%)**
- **27 two-prompt sessions**
- **13 sessions containing three or more prompts**

The full workstream averages **1.41 user prompts per episode**. This is higher than the benchmark's one externally supplied task input per episode, but the dominant observational structure remains one human specification followed by extended agent execution.

The single-prompt subset provides the closest structural match to the benchmark's one-input episode design. Across those 153 episodes:

| Metric | Single-prompt episodes | Relative to external Codex reference |
| --- | ---: | ---: |
| Tool calls / episode | 70.4 | 3.47× |
| Inference calls / episode | 35.1 | — |
| Uncached input / episode | 151k | — |
| Output / episode | 26.4k | — |
| Reasoning output / episode | 13.7k | — |
| Tool calls / 1k user characters | 53.7 | 5.64× |

The one-prompt subset independently shows approximately **3.5× external tool depth** and **5.6× external specification-normalized tool leverage**.

The observed interaction pattern is better described as:

> **coherent specification → extended autonomous execution**

than as repeated conversational decomposition of every action.

### Active-day sensitivity

The 20,000-replicate active-day cluster bootstrap gives:

| Activity per 1,000 user characters | Observed | 95% bootstrap interval |
| --- | ---: | ---: |
| Tool calls | 50.80 | 43.59–59.26 |
| Inference calls | 25.29 | 22.01–29.58 |
| Uncached input | 125.47k | 108.66k–147.13k |
| Output | 19.82k | 16.28k–24.81k |
| Reasoning output | 10.08k | 8.41k–12.40k |

For the directly comparable tool-call measure, the entire observational bootstrap interval remains far above the external Codex five-run leverage range of **9.24–9.82**.

The lower observational bootstrap bound, **43.59**, is approximately **4.44×** the highest external run value, **9.82**.

Their separation persists under active-day resampling.

### Whole-workstream operating profile

Across 193 sessions and 272 prompts, the workstream's activity can be expressed at three distinct denominators:

| Metric | Per episode | Per prompt | Per 1,000 user characters |
| --- | ---: | ---: | ---: |
| User-authored characters | 1,375.21 | 976 | — |
| User prompts | 1.41 | — | — |
| Tool calls | 69.86 | 49.57 | 50.80 |
| Inference calls | 34.78 | 24.68 | 25.29 |
| Uncached input tokens | 172.5k | 122.4k | 125.47k |
| Output tokens | 27.26k | 19.34k | 19.82k |
| Reasoning-output tokens | 13.85k | 9.83k | 10.08k |

Per-episode activity measures delegation depth, while the final column normalizes the same activity by all recorded human-authored prompts, including steering.

### Secondary within-workstream variation

The equal four-active-day endpoint comparison remains informative as a description of heterogeneity inside the workstream:

| Metric | Early: Aug 25–28 | Late: Sep 1–4 | Change |
| --- | ---: | ---: | ---: |
| User characters / prompt | 776 | 969 | +24.9% |
| Prompts / session | 1.47 | 1.45 | approximately unchanged |
| Tool calls / prompt | 37.4 | 59.0 | +57.8% |
| Inference calls / prompt | 19.2 | 28.3 | +47.4% |
| Uncached input / prompt | 88.7k | 148.3k | +67.2% |
| Output / prompt | 15.9k | 22.9k | +44.0% |
| Reasoning output / prompt | 8.15k | 11.40k | +39.9% |

Activity per 1,000 user-authored characters also rises:

| Activity per 1,000 user characters | Early | Late | Change |
| --- | ---: | ---: | ---: |
| Tool calls | 48.17 | 60.90 | +26.4% |
| Inference calls | 24.75 | 29.23 | +18.1% |
| Uncached input | 114.29k | 153.02k | +33.9% |
| Output | 20.47k | 23.58k | +15.2% |
| Reasoning output | 10.51k | 11.76k | +12.0% |

Relative to the external Codex tool-leverage reference of **9.5157**, the early window is already approximately **5.06×** the reference and the late window approximately **6.40×**.

Both endpoint windows show elevated leverage relative to the external reference; the within-workstream increase represents variation within that operating regime.

### Recorded non-success and aborted turns

The observational cohort records:

- Approximately **7.53% tool non-success**
- Approximately **0.195 aborted turns per prompt**

Across the endpoint windows:

| Measure | Early | Late |
| --- | ---: | ---: |
| Tool non-success rate | 6.85% | 6.62% |
| Aborted turns / prompt | 0.168 | 0.173 |

Within the observational endpoint windows, the higher late-period execution depth is not accompanied by a material increase in either recorded reliability signal.

---

## Interpretation

<a id="ol-delegation-depth-leverage"></a>
### Delegation depth and specification burden

The primary contrast combines a smaller measured human-text burden per observational episode with substantially deeper tool execution. Operational activity leverage captures execution depth relative to the complete human specification and steering burden.

### Work packets and sparse steering

Most sessions contain a single prompt, and this subset remains close to the full cohort in tool depth and specification-normalized activity. The pattern is consistent with a **work packet** as the operating unit: a coherent statement of context, constraints, priorities, and intended behavior that supports extended tool execution.

## Scope and Evidence Status

The workstream shows greater tool depth and tool calls per estimated human character than the SWE-rebench Codex reference. The workstream uses GPT-5.4/`xhigh` and the benchmark uses `gpt-5.6-sol`; task mix, repository persistence, episode boundaries, and instrumentation also differ. Benchmark text counts exact supplied task input, while observational text is estimated across all prompts per session. This is an operating-regime comparison rather than an ArcGrav-specific treatment effect. The measured outcome is tool activity; accepted-task productivity is outside the telemetry.

## Conclusion

The feature-development workstream shows 3.44× external tool depth and 5.34× specification-normalized tool activity. Single-prompt episodes and active-day sensitivity analysis reinforce a sparsely steered, execution-heavy operating pattern.

## Data and Reproducibility

- Observational telemetry: [ArcGrav Single-Workstream Codex Telemetry CSV](./ArcGrav_Single_Workstream_Codex_Telemetry.csv) — SHA-256 `e4c5252709c7d92acc67b9b1ceb1a889e53672ae559efb1c7f3a844497309d83`
- External baseline: [Agentic Software Engineering Operational Baseline](../../Agentic_Software_Engineering_Operational_Baseline.md)
- Extraction plan: [CSV Compatibility Plan](../../swe_rebench_07_2026_trajectories/CSV_compatibility_plan.md)
- Generator: [generate_codex_operational_baseline.ps1](../../swe_rebench_07_2026_trajectories/generate_codex_operational_baseline.ps1)
- Generated reference: [codex_operational_baseline.csv](../../swe_rebench_07_2026_trajectories/codex_operational_baseline.csv)

## Related Papers

- [External Operational Baseline](../../Agentic_Software_Engineering_Operational_Baseline.md)
- [Longitudinal Operational Leverage](./ArcGrav_Longitudinal_Operational_Leverage.md)
- [Model-Native Structural Representation](../../Model_Native_Structural_Representation.md)
- [Reasoning–Interaction Substitution](../../ArcGrav_Reasoning_Interaction_Substitution.md)
