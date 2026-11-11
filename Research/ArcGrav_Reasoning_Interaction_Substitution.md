<a id="paper-reasoning-interaction"></a>
<a id="ris"></a>
# ArcGrav & Reasoning–Interaction Substitution in Agentic Task Completion

## Abstract

An agentic task costs more than the model inference that begins it. Tool execution, human steering, repeated context acquisition, discarded work, and revalidation can make an inexpensive attempt costly by the time its result is accepted. This paper defines **reasoning–interaction substitution**: additional model-side reasoning can replace downstream model, tool, and human work, lowering total task cost when the work avoided is worth more than the added computation. It establishes a task-level unit of analysis, distinguishes four forms of overhead, and specifies a break-even condition and non-overlapping cost accounting. Longitudinal Codex telemetry motivates the inquiry by showing how reasoning effort and specification compression relate to activity per prompt. The proposed experimental program tests how task complexity and ArcGrav specification refinement alter the cost of accepted completion.

## Introduction

An agentic task can continue long after its first model response. A software change, for example, may require an agent to inspect a repository, choose an implementation path, edit files, run tests, and recover from failures. An early mistake can cause subsequent work to be repeated or discarded, even when the original inference was inexpensive. Measuring efficiency by the cost of a single inference or the number of prompts can therefore miss substantial costs borne by the model, its tools, and the human directing the task.

This paper asks when allocating more model-side reasoning reduces the cost of reaching an accepted result across that entire trajectory. It develops a task-level accounting framework for model processing, tool use, and human effort, and distinguishes work needed for completion from avoidable reconstruction, correction, redundant execution, and accumulated context processing. It also examines how the initial specification can change this trade-off: ArcGrav expresses objectives, constraints, priorities, and completion criteria in a structured form that may help an agent direct its reasoning. Existing Codex telemetry motivates the question, while the proposed task-linked experiments are needed to determine whether additional reasoning and specification refinement actually reduce accepted-completion cost.

## Role Within the Research Program

[ArcGrav Operational Leverage](./Operational_Leverage/) examines downstream computational activity relative to human specification. This paper examines a different outcome: the total cost of reaching *accepted task completion*. High tool activity per user character is not necessarily efficient if much of it is discarded. Likewise, low inference expenditure is not necessarily cheap if a human must repeatedly diagnose, redirect, and restart the work. The unit of interest is the complete task, not the individual prompt or conversation.

---

## Construct definition and boundaries

<a id="ris-reasoning-interaction-substitution"></a>
**In plain language:** Spending more computation on reasoning can save work overall when it prevents enough subsequent corrections, retries, or reconstruction.

**Reasoning–interaction substitution (RIS)** is the replacement of downstream model, tool, and human work by additional model-side reasoning across a complete task trajectory. It is evaluated by differences in expected total cost under comparable reasoning policies, task conditions, and acceptance standards. It does not equate reasoning tokens with human prompts or treat greater computation as intrinsically better. The question is whether the entire task becomes less expensive to complete correctly.

### Task boundaries and acceptance

<a id="ris-task-trajectory"></a>
A **task trajectory** is the sequence of model calls, context processing, tool operations, human interventions, and outputs from task assignment through accepted completion or a defined termination point. A task can span several conversations or sessions; one conversation can contain several tasks. The task identifier, rather than the chat boundary, determines what work belongs in the measurement.

<a id="ris-accepted-completion"></a>
**Accepted completion** means the result meets criteria established before execution, with no corrective follow-up during a predefined observation window. For software tasks, those criteria may combine tests, static checks, required files or behavior, evaluator acceptance, and the absence of rollback. An unsuccessful task is recorded through its termination point, not omitted from the primary cost comparison.

<a id="ris-single-specification-completion"></a>
**Single-specification completion** means reaching accepted completion from one initial human specification without a corrective or clarifying human turn. It still permits multiple model inferences, repository searches, reads, shell commands, tests, autonomous retries, repairs, and final verification. It is not synonymous with a one-inference or *one-shot* attempt.

### Reasoning effort and human interaction

<a id="ris-reasoning-effort"></a>
**Reasoning effort** is the chosen model policy governing computation allocated to an inference trajectory. Beyond reasoning-output volume, it affects planning depth, search, inference count, tool exploration, verification, and autonomous recovery.

<a id="ris-interaction-burden"></a>
**Interaction burden** is the human work after the initial specification required to keep the task progressing correctly: observation, diagnosis, clarification, correction, restating constraints, redirection, scope recovery, resupplying lost state, and starting replacement conversations. A short corrective prompt can conceal substantial diagnosis and context-switching time. Initial specification and refinement effort are counted separately as part of total task cost.

### Four forms of overhead

The following categories describe why work is repeated or wasted. A single correction episode can exhibit several of them. Their diagnostic labels may overlap, but their charges must be allocated only once when calculating cost.

<a id="ris-state-reconstruction-overhead"></a>
**State-reconstruction overhead (SRO)** is work spent reacquiring task-relevant state already established in an earlier part of the trajectory. Examples include rereading repository files, rediscovering architecture or dependencies, recovering decisions and constraints, repeating exploratory searches, and rebuilding a task model after context loss. Repeated reads count as SRO only when they reconstruct previously acquired state, not when they provide necessary new evidence. A token-equivalent definition appears in the technical appendix.

<a id="ris-correction-overhead"></a>
**Correction overhead (CO)** is the work caused by an earlier attempt failing to meet the task: human correction, new inference and context, repair tools, and revalidation. This is an inclusive description of a correction episode; it can contain reconstruction, redundant execution, and context accumulation, so its unadjusted cost cannot be added to those categories.

<a id="ris-redundant-execution-overhead"></a>
**Redundant execution overhead (REO)** is repeated or discarded model and tool work from a branch that does not survive into the accepted solution. It includes abandoned edits, avoidable rebuilds, investigation of already-eliminated approaches, tests of implementations that violate explicit constraints, and repeated dependency discovery. Necessary exploration and independent validation are not redundant.

<a id="ris-context-accumulation-overhead"></a>
**Context-accumulation overhead (CAO)** is excess repeated processing from carrying an increasingly long conversation or tool history into later model calls. SRO is the cost of reacquiring lost state; CAO is the cost of continually carrying retained state. Restarting too frequently increases reconstruction, while continuing indefinitely can increase accumulated-context cost. The efficient boundary depends on which state must be preserved and what it costs to preserve or rebuild it.

---

<a id="ris-task-completion-cost"></a>
## Task cost and the substitution mechanism

### Count the whole task

Total task cost consists of model processing, separately billed tool use, and human effort:

```math
C_{\mathrm{task}} = C_{\mathrm{model}} + C_{\mathrm{tools}} + C_{\mathrm{human}}
```

Model cost includes uncached input, discounted but nonzero cached input, and output, including metered reasoning output where applicable. Count those quantities over every call and conversation belonging to the task. Tool charges and human time must be valued in a consistent cost-equivalent unit before combining them; otherwise, report each separately. Include the human cost of initial specification refinement and avoid charging a tool operation twice.

The same charges can also be classified by stage: initial specification and acquisition, productive work needed for the accepted result, and overhead. These are **alternative views of the same total**, not additional costs to sum. For diagnosis, an event may carry multiple overhead labels; for additive accounting, each priced event or separable portion belongs to one category. The technical appendix gives the allocation rule and equations.

<a id="ris-task-completion-efficiency"></a>
**Task-completion efficiency (TCE)** is reported as cost per accepted completed task, with lower cost indicating greater efficiency. The accepted-only expression retained in the appendix is a conditional average: by itself, it excludes the cost of failed assignments. The primary comparison therefore uses expected total cost **per assigned task**, measured through acceptance or termination, together with acceptance probability, failure frequency, and conditional cost per accepted completion. All comparisons apply the same acceptance standard and termination protocol.

<a id="ris-failure-amplification"></a>
### How errors become expensive

**Failure amplification** occurs when an early misunderstanding produces a long downstream branch. An incorrect architectural assumption can lead to wrong-file selection, inappropriate edits, misleading test failures, diagnosis of symptoms instead of causes, human intervention, rollback, renewed inspection, and reimplementation. The relevant cost of the error is the full branch it generates, not merely the inference that introduced it.

Additional constraint resolution and architectural verification at the start can prevent such branches. Whether the extra reasoning is economical depends on the work it actually avoids.

### The break-even condition

Compare a higher-reasoning policy with a lower-reasoning policy under the same task assignment and completion rules. Let \(\Delta C_R\) be the higher policy's additional expected initial cost, and \(\Delta C_D\) the expected downstream cost avoided by that policy. Downstream cost includes productive execution, correction, reconstruction, redundant work, retained-context processing, and human interaction.

<a id="ris-reasoning-break-even-condition"></a>
The **reasoning break-even condition** is:

```math
\Delta C_R < \Delta C_D
```

When the inequality holds, higher reasoning has lower expected total task cost. It is a cost comparison, not a claim that more reasoning always improves performance. Only when productive downstream work is unchanged can the avoided cost be described entirely as a reduction in exclusively allocated overhead.

This connects to rational metareasoning and the **value of computation**. [Lieder and Griffiths (2017)](https://doi.org/10.1037/rev0000075) study computational strategy selection under cost, and [De Sabbata et al. (2024)](https://arxiv.org/abs/2410.05563) examine value-of-computation reasoning allocation in language models. RIS extends the accounting boundary to human steering, reacquisition of task state, repeated tool execution, and context costs across an agentic task.

---

## Cache reuse, conversation boundaries, and state compression

### Cached input is still a cost

The longitudinal Codex dataset analyzed in [ArcGrav Operational Leverage](./Operational_Leverage/) contains **2.708 billion input tokens**: **2.482 billion cached** and **226.0 million uncached**. Cached input accounted for **91.65%** of input. This extensive reuse makes absolute token volume important alongside cache share.

A high cache share can coexist with expensive task completion because the same large context is processed repeatedly. Higher reasoning can increase uncached input per prompt yet reduce uncached input over a full accepted task if it prevents repeated acquisition. Compare priced cached and uncached tokens over the whole trajectory, not cache percentage alone.

### When to continue and when to restart

A replacement conversation can require renewed inspection of repository structure, files, architectural relationships, constraints, decisions, completed work, and failed approaches. The reconstruction cost comes from rebuilding state, not from crossing the session boundary itself. Cache reuse may discount the processing but does not eliminate it.

Conversely, preserving every tool result and intermediate decision in a single growing history can make later inferences expensive. Context management is a comparison between the cost of continuing with retained history and the cost of reconstructing only the necessary state in a new session.

<a id="ris-state-compressed-handoff"></a>
### State-compressed handoffs

A **state-compressed handoff** records decision-relevant state without replaying the entire history. At minimum it includes the current objective, accepted decisions, relevant file or object identities, invariants and constraints, completed work, unresolved failures, next required action, and validation status.

ArcGrav encodes this control state through scope, reference, priority, binding, and compact structural conventions. The purpose is to preserve information that affects future decisions while discarding history that does not.

---

## ArcGrav and the allocation of reasoning

### External specification and internal execution

ArcGrav seeks to compress the external control plane by expressing objective, authority, priority, scope, reference identity, transformations, exclusions, sequencing, evidence requirements, and completion criteria in a structured specification. The agent can use those relationships directly rather than reconstructing them from diffuse prose or repeated human corrections.

Higher reasoning allocates more computation to task-model construction, alternative exploration, constraint checking, repository inspection, verification, and autonomous repair. Refined specifications direct that work toward the intended objective; greater reasoning alone does not resolve an underspecified or incorrect objective.

| Specification representation | Lower reasoning | Higher reasoning |
| --- | --- | --- |
| Weakly refined or diffuse | Lower direct cost; greater risk of steering and missed constraints | More exploration, but ambiguity can still waste computation |
| Highly refined ArcGrav | Efficient for simple tasks with clear acceptance | Strong candidate for complex tasks with expensive failure amplification |

### Refinement changes the break-even point

Specification refinement can shift the difficulty at which higher reasoning becomes cost-effective in either direction. If refinement disproportionately improves higher-reasoning execution, added reasoning pays off at lower complexity. If refinement instead removes ambiguities that previously defeated lower-reasoning execution, higher reasoning may only pay off on harder tasks.

The experiment must therefore compare reasoning policies **within each specification condition and difficulty stratum**, including the human time spent refining the specification. The practical objective is to allocate both external specification effort and internal reasoning effort economically, rather than maximizing either.

### Expected routing and agent design

The proposed routing pattern is low effort for local renames and deterministic formatting; medium or high for bounded multi-file work; high for cross-file architectural changes; and high or extra-high effort for ambiguous, correctness-sensitive, multi-tool tasks. These are starting expectations, not rules based on task labels alone. The relevant predictor is expected **failure amplification**: how much repair, reconstruction, and human intervention an initial mistake is likely to create.

An agent following this principle should verify expensive architectural assumptions early, preserve compact decision-relevant state between sessions, and use specification refinement when its one-time cost is less than the steering and rework it prevents.

---

## Motivation from existing Codex telemetry

[ArcGrav Operational Leverage](./Operational_Leverage/) reports prompt- and session-level activity that motivates a task-cost analysis.

### Computational profile by reasoning effort

Across prompt-valid sessions, the reported per-prompt values were:

| Effort | Uncached input / prompt | Output / prompt | Reasoning output / prompt | Tools / prompt |
| --- | ---: | ---: | ---: | ---: |
| low | 20.9k | 1.41k | 0.33k | 5.83 |
| medium | 35.0k | 2.80k | 0.94k | 8.88 |
| high | 41.4k | 3.68k | 1.54k | 11.91 |
| xhigh | 50.9k | 5.92k | 2.97k | 15.61 |

Higher reasoning corresponds to more model computation and tool activity per prompt. Within the **14 model/day combinations** containing both high and xhigh, median xhigh-to-high ratios were:

| Measure | Median ratio |
| --- | ---: |
| User characters / prompt | 0.90× |
| Uncached input / prompt | 1.79× |
| Output / prompt | 1.82× |
| Reasoning output / prompt | 1.94× |
| Tools / prompt | 1.44× |
| Inference calls / prompt | 1.32× |

### Specification compression during mature use

Within the fixed GPT-5.4/xhigh longitudinal cohort, comparison of the first and last **15 active days** found:

- User characters per prompt declined from approximately **2,259 to 581**.
- Prompts per session declined from **3.66 to 2.88**.
- Tool calls per prompt increased from **16.67 to 18.56**.
- Inference calls per prompt increased from **7.77 to 8.87**.
- Uncached input per prompt remained near **46–48k**.
- Output and reasoning per prompt remained approximately preserved.

Measured downstream activity per **1,000 user characters** increased by approximately **4.07×–4.44×**. The cohort therefore shows specification compression with preserved downstream activation. The task-cost question is whether that activity produces accepted results with less aggregate work.

### The missing unit is the task

Prompt activity cannot identify which calls contribute to an accepted result, which recover a failed branch, or which repeat work already done. That distinction requires stable task identity across conversations, accepted-completion outcomes, corrective-versus-continuation labels, and repeated file and tool-event traces.

---

## Predictions and experimental program

The primary outcome is expected total cost per assigned task under fixed acceptance and termination rules. Acceptance probability, total cost per accepted completion, and human intervention are reported alongside it.

### Predictions and observable tests

| Prediction | Observable test |
| --- | --- |
| **Complexity threshold.** Lower reasoning minimizes cost for local, deterministic tasks; higher reasoning becomes economical as repair and reconstruction costs rise. | Estimate cost-minimizing effort across task difficulty and independently rated failure-amplification potential. |
| **Specification–reasoning interaction.** ArcGrav refinement shifts the break-even point according to which reasoning policy gains more. | Estimate the refinement × reasoning effect on expected task cost across difficulty strata. |
| **Reduced external steering.** At matched difficulty, higher reasoning reduces corrections, clarifications, restarts, and discarded branches. | Count corrective turns, restarts, and implementation reversals per assigned task. |
| **Lower aggregate uncached input.** Higher reasoning can use more uncached input per prompt but less per accepted task by avoiding repeated acquisition. | Compare full-trajectory uncached tokens and priced model cost, not per-prompt averages. |
| **Cache-share paradox.** A high cached-input share can coexist with high completion cost. | Compare absolute cached volume, cache share, and completion cost across policies. |
| **Interior cost optimum.** Some task classes have a lowest-cost reasoning level between the extremes. | Estimate cost curves across reasoning settings rather than assuming monotonic improvement. |
| **Human-time savings first.** Higher reasoning can reduce observation, diagnosis, and switching time before lowering token cost. | Measure human time and model charges separately, then combine them using explicit time valuations. |

### Required trajectory measurements

Each assigned task receives an identifier that persists across calls, sessions, and conversations. The event log records:

- Task assignment, specification version, refinement effort, difficulty, acceptance criteria, and completion window.
- Model and version, reasoning setting, inference and tool calls, billable uncached and cached input, output, and pricing assumptions.
- Human observation and diagnosis time; clarification and correction turns; restarts; and whether interventions change scope.
- Repository reads, searches, builds, edits, test runs, repeated file identities, discarded implementation branches, and revalidation.
- Compact handoffs, fresh-session reacquisition, retained-context processing, and costs attributed under a disjoint accounting ledger.
- Acceptance or failure, cost and time at termination, and rollback or corrective follow-up within the specified observation window.

Repeated reads are classified as SRO or REO only when the task history identifies avoidable reacquisition or execution. Retain raw event traces for audit and allocate each billed event once.

### Controlled comparison

Cross **specification condition** (ordinary versus refined ArcGrav) with **reasoning policy** (low, medium, high, xhigh), stratifying tasks by dependencies, ambiguity, and failure-amplification potential. Randomize comparable tasks or matched task instances across conditions. Hold model version and tool access constant, and lock initial specifications, acceptance tests, retry limits, and observation windows before execution. Blind evaluators to condition where feasible.

Compare acceptance probability, full cost through acceptance or termination, conditional cost of accepted tasks, human correction burden, and the specification-refinement × reasoning interaction. Include initial refinement time. Control or report token budgets, model and cache rates, tool availability, task order, operator experience, the assumptions behind independent retries, and differences in human observation.

A task completed across several conversations counts once. Multiple tasks completed within one conversation remain distinct. The decisive comparison is total cost at a fixed acceptance standard.

---

## Appendix: Technical accounting and simplified models

The equations here specify measurement and special-case interpretations. They are not separate claims beyond the task-level mechanism presented above.

### Model cost and reconstruction units

Across all calls in a task, model cost is:

```math
C_{\mathrm{model}} = r_u U + r_c C + r_o O
```

Here \(U\), \(C\), and \(O\) are uncached input, cached input, and output tokens (including metered reasoning output where applicable). Their rates are \(r_u\), \(r_c\), and \(r_o\). Cached input has a discounted, nonzero rate; see [OpenAI usage rate information](https://help.openai.com/en/articles/11481834). Report tool charges separately and include human time only after specifying its valuation.

A token-equivalent measure of state reconstruction for task \(j\) is:

```math
SRO_j = U^{re}_j + \alpha C^{re}_j + \beta O^{re}_j
```

The superscript \(re\) identifies tokens attributable to reacquiring previously established state. The coefficients \(\alpha\) and \(\beta\) convert cached input and output to a common unit; for an uncached-input-cost equivalent, use \(r_c/r_u\) and \(r_o/r_u\). Associated tool charges are logged separately.

A correction episode can include the following charges:

```math
CO = C_{\mathrm{human\ correction}}
   + C_{\mathrm{new\ inference}}
   + C_{\mathrm{new\ context}}
   + C_{\mathrm{repair\ tools}}
   + C_{\mathrm{revalidation}}
```

This diagnostic total is inclusive and can overlap SRO, REO, and CAO. It is **not** an additive component of a ledger until overlapping events have been exclusively allocated.

### Exclusive attribution

By process stage, the same full task cost is:

```math
C_{\mathrm{task}} = C_{\mathrm{initial}}
                + C_{\mathrm{productive}}
                + C_{\mathrm{overhead}}
```

Initial cost covers specification and first task acquisition; productive cost covers work necessary for the accepted result; overhead covers additional avoidable or nonproductive work. For an additive overhead ledger:

```math
C_{\mathrm{overhead}}
 = C^{*}_{\mathrm{SRO}} + C^{*}_{\mathrm{CO}}
 + C^{*}_{\mathrm{REO}} + C^{*}_{\mathrm{CAO}}
 + C^{*}_{\mathrm{I}} + C^{*}_{\mathrm{other}}
```

The asterisk means an **exclusive accounting allocation**, as distinct from the inclusive definitions in Section 1. For a correction that prompts a repository reread and another implementation, allocate the reacquisition to SRO*, discarded or repeated implementation to REO*, and human diagnosis to I*. Only remaining correction-specific cost belongs to CO*. Record all applicable diagnostic labels as metadata, but charge each token, tool fee, or unit of human time once. Unresolved attribution belongs in the other category, with an explicit coding protocol.

### Accepted-task cost and break-even definitions

For accepted tasks \(\mathcal{A}\), the original accepted-only TCE measure is:

```math
TCE = \frac{\sum_{j \in \mathcal{A}} C_{\mathrm{task},j}}{N_{\mathrm{accepted}}}
```

Here \(N_{\mathrm{accepted}}=|\mathcal{A}|\). This is the mean cost **conditional on acceptance**, not the mean cost of all assigned attempts. Report failed assignments and their termination cost alongside it; compare policies primarily on mean total cost per assigned task under the same completion protocol.

For higher (\(h\)) and lower (\(l\)) reasoning policies, the additional initial cost and avoided downstream cost are:

```math
\Delta C_R
  = E[C_{\mathrm{initial}}\mid h] - E[C_{\mathrm{initial}}\mid l]

\Delta C_D
  = E[C_{\mathrm{downstream}}\mid l] - E[C_{\mathrm{downstream}}\mid h]
```

Their task-cost comparison is equivalent to the break-even condition:

```math
E[C_{\mathrm{task}}\mid h] < E[C_{\mathrm{task}}\mid l]
\quad\Longleftrightarrow\quad
\Delta C_R < \Delta C_D
```

When productive downstream cost is unchanged and all other charges are exclusively attributed, the avoided downstream cost can be unpacked into non-overlapping overhead differences:

```math
\Delta C_R <
\Delta SRO^{*} + \Delta CO^{*} + \Delta REO^{*}
+ \Delta CAO^{*} + \Delta I^{*}
+ \Delta C^{*}_{\mathrm{other}}
```

The aggregate \(\Delta C_D\), measured directly across complete task trajectories, remains the primary quantity.

### Simplified retry comparison

Let \(c_r\) be expected cost per attempt and \(p_r\) the probability of accepted completion without corrective human intervention at reasoning level \(r\). For conditionally similar, independent attempts with constant costs and success probabilities under unlimited retries:

```math
E[C_{\mathrm{task}}\mid r] \approx \frac{c_r}{p_r}

\frac{c_h}{p_h} < \frac{c_l}{p_l}
\quad\Longleftrightarrow\quad
\frac{p_h}{p_l} > \frac{c_h}{c_l}
```

Under this simplified model, a more expensive attempt is economical when its proportional gain in success probability exceeds its proportional increase in attempt cost. For retries that reuse state or change in cost or success probability, estimate cost from linked task trajectories instead.

### Specification–reasoning interaction

Let \(q\) represent specification refinement and \(d\) task difficulty. The difference in expected task cost between lower and higher reasoning is:

```math
V(q,d) = E[C_{\mathrm{task}}\mid l,q,d]
       - E[C_{\mathrm{task}}\mid h,q,d]
```

Higher reasoning has a cost advantage where \(V(q,d)>0\). Compare \(V\) across specification-refinement conditions and task difficulty, including the human cost of producing each specification.

---

## Scope and Evidence Status

The Codex telemetry measures prompt- and session-level activity, not accepted task trajectories. RIS cost effects require linked task IDs, a fixed acceptance and termination protocol, measurements of human effort, and non-overlapping cost attribution. The retry model assumes comparable independent attempts; the cost effects of reasoning level and ArcGrav refinement are predictions for controlled tests rather than findings established by the cited telemetry.

## Conclusion

The cheapest inference is not necessarily the cheapest completed task. Reasoning–interaction substitution identifies when greater model-side reasoning prevents enough downstream work to lower the cost of reaching an accepted result. ArcGrav specification refinement and task difficulty determine where that trade-off should be tested and how reasoning should be allocated.

## Related Papers

- [Model-Native Structural Representation](./Model_Native_Structural_Representation.md)
- [Representational Capacity Reclamation](./Representational_Capacity_Reclamation.md)
- [ArcGrav Operational Leverage](./Operational_Leverage/)

## Other Sources

- [OpenAI usage rate information](https://help.openai.com/en/articles/11481834) — distinction between uncached input, cached input, and output pricing; rates are subject to change.

## References

- De Sabbata, C. N., et al. (2024). *Rational Metareasoning for Large Language Models*. arXiv preprint. https://arxiv.org/abs/2410.05563
- Lieder, F., & Griffiths, T. L. (2017). *Strategy selection as rational metareasoning*. Psychological Review. https://doi.org/10.1037/rev0000075
