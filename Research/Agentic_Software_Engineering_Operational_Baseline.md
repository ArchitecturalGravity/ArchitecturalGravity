<a id="paper-operational-baseline"></a>
<a id="baseline"></a>
# External Operational Baseline for Agentic Software Engineering

## Abstract

Software-engineering agents can turn a human task specification into extended tool-driven execution, but observational studies lack a standardized reference for comparing how much activity each delegated objective produces. This paper constructs an external operational baseline from the SWE-rebench July 2026 trajectories. The primary cohort comprises 555 Codex episodes across 111 engineering tasks and five repeated runs, with exact task inputs available for every episode. A reproducible extraction identifies 11,262 normalized tool calls against 1,183,515 specification characters, yielding 20.29 tool calls per episode and 9.52 tool calls per 1,000 specification characters. Run-level tool depth varies from 19.71 to 20.94; Codex resolves 322 episodes (58.0%).

A matched-task comparison across Codex, Claude Code, Cursor, and Junie covers 2,220 episodes and finds mean normalized trajectory depth ranging from 52.29 to 172.00 events per episode. The resulting framework distinguishes delegation depth, specification-normalized operational leverage, human steering density, and outcome rate. It provides an external scale for describing interactive coding workflows while keeping execution volume distinct from task resolution.

## Introduction

Coding agents receive software-engineering objectives in text and may carry out multiple rounds of repository inspection, tool use, editing, and validation before returning a result. The human request is a starting point, not a direct record of the execution it activates. Two workflows with similar prompts can therefore operate at different levels of downstream activity and require different amounts of human guidance. Describing these differences requires a common unit of delegation and comparable measurements.

Observational telemetry is often organized around sessions or prompts, whereas benchmark trajectories typically trace one externally assigned task to a terminal state. A session containing several human messages may still concern one objective; conversely, raw event counts can mix tool calls with messages, tool results, and other trajectory records. Outcome adds another dimension: resolving a task and executing a long sequence of actions are not the same measurement. A historical reference can show whether one workflow changed, but cannot locate that workflow relative to a standardized agent system.

This study asks **what operating regime an observed software-engineering workflow occupies relative to standardized agentic software engineering.** It answers by establishing an external comparison unit—the **delegation episode**, one assigned objective and its ensuing agent execution—and measuring tool activity relative to episodes and the length of the exact human task input. Human steering and task resolution remain separate dimensions. The study derives a directly usable Codex reference from five repeated runs of the [SWE-rebench July 2026 trajectories](https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories) and a broader trajectory-depth scale from four complete coding-agent systems. It then specifies how observational work packets can be compared with that reference using matched definitions and explicit denominators.

## Role Within the Research Program

This representation-neutral reference establishes comparison quantities for the observational [Operational Leverage](./Operational_Leverage/) papers. It defines matched delegation, tool-call, specification, and outcome measures from a standardized coding-agent dataset.

---

## Purpose and reference design

**In plain language.** A delegation episode is one assigned engineering objective and the agent work performed to address it. Tool depth counts invocations within that episode; it is not a success score.

Operational-leverage studies ask how much downstream execution is activated by human specification and how much human steering is required while that work is executed.

A historical comparison answers whether a workflow changed relative to its own prior operation. An external baseline answers a different question:

> **What operating regime does an observed workflow occupy relative to standardized agentic software engineering?**

The baseline therefore centers on measurements that can be carried from a standardized benchmark into observational software-development telemetry.

<a id="baseline-delegation-episode"></a>
### Delegation episode as the common unit

The portable top-level unit is the **delegation episode**:

> **one externally supplied software-engineering objective followed by autonomous agent execution until completion, submission, failure, or termination.**

In SWE-rebench, one trajectory is one delegation episode.

For observational coding workflows, the corresponding unit is normally a session or reconstructed work packet containing one coherent engineering objective, the agent execution that follows, and any human steering inside that episode.

This produces the hierarchy:

```text
delegation episode / work packet
        ↓
human specification and steering
        ↓
agent/model execution
        ↓
tool and repository actions
```

### Primary operating axes

The baseline uses four distinct operating measures.

<a id="baseline-delegation-depth"></a>
**Delegation depth** measures downstream activity per delegated objective: total activity divided by the number of delegation episodes. For tool depth, activity consists of normalized `tool_call` events.

<a id="baseline-specification-normalized-leverage"></a>
**Specification-normalized operational leverage** measures downstream activity per 1,000 human-authored specification characters. The denominator is the total specification character count expressed in thousands.

<a id="baseline-steering-density"></a>
**Steering density** measures the number of user prompts or steering interventions divided by the number of delegation episodes.

<a id="baseline-outcome-rate"></a>
**Outcome rate** measures completed target outcomes: the number of successful episodes divided by the total number of episodes.

These axes distinguish how much work is delegated, how efficiently human specification activates execution, how much steering occurs during execution, and whether the delegated objective reaches the target outcome.

---

## External dataset

### SWE-rebench July 2026 trajectories

The source dataset is the **SWE-rebench July 2026 Trajectories** release:

https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories

The release contains:

- **9,435 normalized trajectories**
- **111 software-engineering tasks**
- **17 participants**
- **5 runs per participant**
- **13 standalone models** in a common scaffold
- **4 complete coding-agent systems:** Codex, Claude Code, Cursor, and Junie

The normalized records contain prompt provenance, typed agent/tool events, usage information, evaluation state, participant identity, repository identity, task identity, and run identity.

The four complete coding-agent systems contribute **2,220 delegation episodes**: 111 tasks, five runs per task, and four agents.

### Codex comparison cohort

The direct product-level baseline uses **555 Codex trajectories**: 111 software-engineering tasks, each evaluated in five runs.

The trajectory records identify the Codex model as **`gpt-5.6-sol`**. SWE-rebench methodology specifies medium reasoning effort for the July 2026 Codex configuration.

Each Codex trajectory contains one exact externally supplied user task input. The resulting cohort therefore supplies a complete specification denominator for all 555 episodes.

### Reproducible compatibility extraction

The Codex compatibility dataset is generated from the vendored SWE-rebench trajectories using:

- **[CSV compatibility plan](./swe_rebench_07_2026_trajectories/CSV_compatibility_plan.md)**
- **[PowerShell generator](./swe_rebench_07_2026_trajectories/generate_codex_operational_baseline.ps1)**
- **[Generated Codex operational baseline CSV](./swe_rebench_07_2026_trajectories/codex_operational_baseline.csv)**

The generator validates the complete 555-episode cohort, the 111-task × five-run structure, trajectory identity, run identity, prompt representation, event types, and output totals before accepting the generated CSV.

The primary human-specification denominator includes only prompt content satisfying:

```text
role == "user"
status == "exact_task_input"
```

Specification characters are Unicode code points in that exact task input.

Primary tool depth counts only normalized events satisfying:

```text
event.type == "tool_call"
```

Tool results, file changes, agent steps, assistant messages, prompt events, and final messages remain separate event categories.

The primary cohort leverage statistic is computed from aggregate totals:

```math
L_{tool}
=
\frac{\sum_i T_i}
{\sum_i H_i/1000}
```

Here, `T_i` is the number of normalized `tool_call` events in episode `i`, and `H_i` is that episode's count of exact task-specification characters. This divides total tool calls by total specification characters expressed in thousands, rather than averaging episode-level ratios.

---

## Comparison protocol for observational workstreams

### Map the episode boundary first

For SWE-rebench:

```text
one trajectory = one delegation episode
```

For an interactive software-engineering workflow, the closest equivalent is normally:

```text
one coherent session or work packet = one delegation episode
```

Prompts inside that episode measure steering rather than automatically defining new episodes.

This distinction is essential for comparing standardized autonomous execution with real interactive workflows.

### Direct comparison measures

A compatible observational workstream should report the following quantities over the full study cohort:

| Operating dimension | Observational measure | External Codex reference |
| --- | --- | ---: |
| Delegation depth | Compatible tool calls / episode | **20.29** |
| Specification burden | Human-authored task chars / episode | **2,132.46** |
| Steering density | User prompts / episode | **1.00 benchmark task input** |
| Tool-call leverage | Tool calls / 1k human specification chars | **9.52** |
| Broad trajectory depth | Comparable normalized events / episode | **52.29** |
| Broad trajectory leverage | Comparable events / 1k specification chars | **24.52** |
| Outcome | Comparable successful episodes / episodes | **58.0%** |

To compare an observed activity measure with Codex, divide its value by the corresponding external reference. For example, divide observed tool calls per episode by **20.29**, or observed tool calls per 1,000 human-authored specification characters by **9.5157** (rounded to **9.52** in the tables). A ratio of **1.0** matches the reference; values above 1.0 indicate greater depth or specification-normalized tool activity, and values below 1.0 indicate less on that dimension.

### Recommended interpretation order

For an observational software-engineering study, the comparison should proceed in this order:

1. Describe the observed workstream as a whole.
2. Map sessions or work packets to delegation episodes.
3. Compare tool depth per episode with the **20.29-call Codex reference**.
4. Compare tool activity per 1,000 human specification characters with the **9.52-call leverage reference**.
5. Report human steering density separately.
6. Report outcome separately when a compatible outcome measure exists.
7. Use normalized trajectory-event depth for broader cross-agent context.
8. Add historical or within-workstream comparisons as secondary analyses when useful.

This keeps the primary analysis focused on the observed workflow's operating regime rather than on whether the workflow happened to change during the observation window.

---

<a id="baseline-external-codex-reference"></a>
## Codex operational baseline

### Aggregate operating profile

The compatibility extraction produces the following Codex reference:

| Measure | Codex external reference |
| --- | ---: |
| Delegation episodes | **555** |
| Unique software-engineering tasks | **111** |
| Repeated runs | **5** |
| Episodes with exact task specification | **555 (100%)** |
| Exact task-specification characters | **1,183,515** |
| Specification characters / episode | **2,132.46** |
| User task inputs / episode | **1.00** |
| Normalized tool calls | **11,262** |
| Tool calls / episode | **20.29** |
| Tool calls / 1,000 specification characters | **9.52** |
| Normalized trajectory events | **29,020** |
| Normalized events / episode | **52.29** |
| Normalized events / 1,000 specification characters | **24.52** |
| Resolved episodes | **322** |
| Resolved rate | **58.0%** |
| Published tokens / problem | **2.071M** |

The standardized Codex operating pattern can therefore be summarized as:

> **about 2.13k characters of external task specification → about 20 normalized tool calls inside a 52-event delegation episode**

The primary specification-normalized reference is:

> **9.52 normalized tool calls per 1,000 exact task-specification characters**

### Repeated-run stability

Each of the five runs contains the same 111 tasks and the same aggregate task-specification burden of **236,703 characters**.

| Run | Episodes | Tool calls | Tool calls / episode | Tool calls / 1k specification chars |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 111 | 2,209 | **19.90** | **9.3324** |
| 1 | 111 | 2,188 | **19.71** | **9.2437** |
| 2 | 111 | 2,287 | **20.60** | **9.6619** |
| 3 | 111 | 2,324 | **20.94** | **9.8182** |
| 4 | 111 | 2,254 | **20.31** | **9.5225** |
| **All runs** | **555** | **11,262** | **20.29** | **9.5157** |

The operating range is narrow:

```text
Tool depth:      19.71–20.94 calls / episode
Tool leverage:    9.24–9.82 calls / 1k specification chars
```

The repeated task set therefore produces a stable Codex reference around **20 tool calls per delegated engineering objective** and **9.5 tool calls per 1,000 characters of external specification**.

### Specification burden and steering structure

Every Codex benchmark episode contains one exact user task input. Across 555 episodes, that is 555 inputs, or **1.00 user task input per episode**.

The external task specification averages **2,132 characters per episode**.

These two values provide separate references for observational workstreams:

- **Specification burden:** how much human-authored task text defines an episode
- **Steering density:** how many human interventions occur inside the episode

A real workflow can therefore be compared with the baseline without treating every prompt as a new delegation episode.

<a id="baseline-normalized-trajectory-depth"></a>
### Trajectory-event depth

The Codex cohort contains **29,020 normalized trajectory events** across **555 episodes**, or **52.29 events per episode**. Relative to the **1,183,515 characters** of exact task specification, it records **24.52 events per 1,000 specification characters**.

Normalized event depth remains useful as a broader trajectory measure, while normalized `tool_call` depth supplies the narrower common activity measure for observational tool telemetry.

### Outcome scale

Codex resolves **322 of 555 episodes**, producing a **58.0% resolved rate**.

Outcome is reported independently from execution depth. A deeper trajectory is not itself a success measure; it describes the amount of agent activity allocated to the delegated objective.

---

<a id="baseline-external-coding-agent-reference"></a>
## Broader coding-agent operating reference

The four complete coding-agent systems provide a common-task execution-depth scale.

| Agent system | Episodes | Resolved | Resolved rate | Normalized trajectory events | Events / episode | Published tokens / problem |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Codex | 555 | 322 | **58.0%** | 29,020 | **52.29** | **2.071M** |
| Claude Code | 555 | 335 | **60.4%** | 69,546 | **125.31** | **3.342M** |
| Cursor | 555 | 287 | **51.7%** | 95,460 | **172.00** | **1.827M** |
| Junie | 555 | 343 | **61.8%** | 40,753 | **73.43** | **1.685M** |
| **Four-agent reference** | **2,220** | **1,287** | **58.0%** | **234,779** | **105.76** | **2.231M mean** |

### Cross-agent execution-depth scale

The complete systems occupy substantially different trajectory-depth regimes on the same workload:

| Agent | Events / episode | Relative to Codex | Relative to four-agent mean |
| --- | ---: | ---: | ---: |
| Codex | **52.29** | **1.00×** | **0.49×** |
| Junie | **73.43** | **1.40×** | **0.69×** |
| Claude Code | **125.31** | **2.40×** | **1.18×** |
| Cursor | **172.00** | **3.29×** | **1.63×** |

The cross-agent span is more than threefold from Codex to Cursor.

This establishes an important external scale:

> **execution depth varies materially across agent systems even when the software-engineering task set is held fixed.**

### Repeated-run event-depth range

The five-run ranges are:

| Agent | Mean events / episode | Five-run range | Mean resolved rate |
| --- | ---: | ---: | ---: |
| Codex | **52.29** | **50.88–53.94** | **58.0%** |
| Junie | **73.43** | **71.70–75.22** | **61.8%** |
| Claude Code | **125.31** | **117.09–130.64** | **60.4%** |
| Cursor | **172.00** | **162.86–180.52** | **51.7%** |
| **Four-agent pooled** | **105.76** | **100.93–108.63** | **58.0%** |

Codex therefore has both a stable tool-call reference near **20 calls per episode** and a stable broader trajectory reference near **52 events per episode**.

### Depth and outcome are separate axes

The cross-agent results make the distinction visible. Codex records the lowest normalized event depth of the four complete systems while resolving **58.0%** of episodes. Cursor records the highest event depth at **172 events per episode** while resolving **51.7%**. Junie resolves **61.8%** with substantially less trajectory depth than Claude Code or Cursor.

The operational question is therefore not whether an agent simply performs more activity. It is:

> **What execution regime accompanies the delegated work, how much human specification activates it, how much steering is required, and what outcome rate accompanies that regime?**

---

## Reusable baseline profile

### Codex direct-comparison profile

The primary external Codex reference is:

```text
555 standardized delegation episodes
111 tasks × 5 runs
555/555 exact task specifications available
1,183,515 exact task-specification characters
2,132.46 specification characters / episode
11,262 normalized tool calls
20.29 tool calls / episode
19.71–20.94 tool calls / episode across runs
9.52 tool calls / 1,000 specification characters
9.24–9.82 tool-call leverage across runs
29,020 normalized trajectory events
52.29 normalized events / episode
24.52 normalized events / 1,000 specification characters
322 resolved
58.0% resolved rate
2.071M published tokens / problem
```

This profile is the preferred external product-level reference for observational Codex operational-leverage studies.

### Broader complete-agent profile

The broader complete-agent reference is:

```text
2,220 standardized delegation episodes
1,287 resolved
58.0% resolved rate
234,779 normalized trajectory events
105.76 normalized events / episode
100.93–108.63 events / episode across matched runs
2.231M mean published tokens / problem
```

The individual complete systems span approximately **52 to 172 normalized events per episode**.

### Reference terminology

The research program uses the following terms:

- **External Codex reference** — the 555 standardized Codex delegation episodes.
- **External coding-agent reference** — the pooled Codex, Claude Code, Cursor, and Junie cohort.
- **Delegation episode** — one delegated engineering objective followed by agent execution to termination.
- **Delegation depth** — downstream activity per delegation episode.
- **Specification burden** — human-authored task-specification characters per episode.
- **Steering density** — user interventions per delegation episode.
- **Operational leverage** — downstream activity per unit of human-authored specification.
- **Outcome rate** — successful delegation episodes divided by total delegation episodes.
- **Historical operating reference** — a prior matched period from the same observed workflow.

---

## Scope and Evidence Status

The extracted SWE-rebench dataset supplies an external operating reference, not an ArcGrav treatment group. Direct comparisons require compatible event definitions and task-episode boundaries; resolved outcomes remain a separate measure.

## Conclusion

The SWE-rebench July 2026 trajectories establish a reproducible external operating scale for agentic software engineering. For the 555-episode Codex cohort, the directly reusable references are **20.29 normalized tool calls per delegated objective** and **9.52 calls per 1,000 exact task-specification characters**. Both remain tightly grouped over five repeated runs, while the four complete coding-agent systems span **52.29–172.00 normalized trajectory events per episode** on the same tasks. These contrasts show why execution depth and task resolution belong on separate axes.

For an observed workstream, the comparison proceeds from the unit of delegation through tool depth and specification-normalized activity, then examines human steering and resolved outcomes separately:

```text
observed software-engineering workstream
        ↓
delegation depth relative to 20.29 tool calls / episode
        ↓
specification leverage relative to 9.52 tool calls / 1k chars
        ↓
steering density
        ↓
outcome
        ↓
broader complete-agent trajectory scale
```

The resulting question is **what operating regime a workflow occupies relative to standardized agentic software engineering**, rather than simply how many actions the agent performs.
---


## Data and Reproducibility

- SWE-rebench July 2026 Trajectories: https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories
- SWE-rebench trajectory index: https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories/blob/main/index.jsonl
- SWE-rebench normalized trajectory schema: https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories/blob/main/schema.json
- SWE-rebench methodology and leaderboard: https://swe-rebench.com/
- Local compatibility plan: [CSV_compatibility_plan.md](./swe_rebench_07_2026_trajectories/CSV_compatibility_plan.md)
- Reproducible generator: [generate_codex_operational_baseline.ps1](./swe_rebench_07_2026_trajectories/generate_codex_operational_baseline.ps1)
- Generated comparison dataset: [codex_operational_baseline.csv](./swe_rebench_07_2026_trajectories/codex_operational_baseline.csv)

## Related Papers

- [Longitudinal Operational Leverage](./Operational_Leverage/Studies/ArcGrav_Longitudinal_Operational_Leverage.md)
- [Single-Workstream Delegation Leverage](./Operational_Leverage/Studies/ArcGrav_Single_Workstream_Delegation_Leverage.md)

## References

- *SWE-rebench July 2026 Trajectories*. (2026). Dataset. https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories
- *SWE-rebench methodology and leaderboard*. https://swe-rebench.com/
