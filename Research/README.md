<a id="research-index"></a>
# Architectural Gravity Research

ArcGrav is a cross-model agent control language, implemented as a model-native instructional representation built from conventions that language models already encounter across natural language, source code, mathematics, configuration files, markup, and technical documentation.

The broader research thesis behind ArcGrav is **Model-Native Structural Representation (MNSR)**:

> **Broadly trained language models learn reusable internal representations of relational and operational structure across prose, code, mathematics, and other structured formats. External representations that make task-relevant relationships explicit using cues aligned with those learned associations can reduce the interpretive work required to reconstruct the intended structure from less explicit input.**

ArcGrav is treated as one implementation hypothesis within that broader research program rather than as a uniquely optimal prompting representation.

## Research Program

### 1. [Model-Native Structural Representation](./Model_Native_Structural_Representation.md#paper-mnsr)

**Structural Recoverability:** Can familiar external cues expose task-relevant relationships in forms that models can recover from broadly learned associations with relatively little representation-specific explanation?

This paper owns the general MNSR thesis, the structural relationship taxonomy, structural reconstruction tax, learned structural priors, task recognition, associative retrieval, internal task and semantic representations, contextual anchors, explicit binding, and the distinction between general MNSR claims and ArcGrav-specific implementation claims.

### 2. [Instructional Representation & the Prose–Program Boundary](./Instructional_Representation.md#paper-instructional-representation)

**Instructional Representation:** How should relationships such as scope, authority, priority, reference identity, evidence, constraint, and requested transformation be represented when the model can interpret both natural language and code?

This paper owns the distinction between **instruction structure** and **program structure** and the representational continuum:
> **prose → structured documents → instructional representation → pseudocode → code**

### 3. [Representational Capacity Reclamation](./Representational_Capacity_Reclamation.md#paper-rcr)

**Accessible Task Capacity:** How much fixed model-side capacity can be redirected from representation recovery toward useful task reasoning, verification, and execution by reducing representational impedance?

This paper owns the distinction between intrinsic and accessible task capacity, representational capacity reclamation, the effective capacity frontier, frontier multipliers, complexity amplification, and controlled measurements of breadth, depth, and active relational load under fixed model-side resources.

### 4. [ArcGrav & Syntax Efficiency](./ArcGrav_Syntax_Efficiency.md#paper-syntax-efficiency)

**Serialization and Compositional Efficiency:** How many tokens are required to encode a representation once its semantics are assumed, and how efficiently can established context be referenced and reused?

This paper owns tokenizer-level comparisons, syntax overhead, compositional reuse, and the controlled comparisons between ArcGrav, Python-like compact syntax, YAML, Markdown, and XML.

### 5. [ArcGrav & Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md#paper-interpretive-efficiency)

**Interpretive Efficiency:** How much representation-specific information must be supplied before a structured instruction is interpreted correctly?

The paper focuses on acquisition, maintenance, and repair cost, specification requirements, zero-specification interpretation, specification-dose curves, and comparative experiments between familiar and unfamiliar representations.

### 6. [ArcGrav & Reasoning–Interaction Substitution in Agentic Task Completion](./ArcGrav_Reasoning_Interaction_Substitution.md#paper-reasoning-interaction)

**Task-Completion Efficiency:** When does additional model reasoning reduce total cost by preventing repeated human steering, context reconstruction, corrective turns, and redundant tool execution?

This paper owns the reasoning–interaction substitution hypothesis, single-specification completion, state-reconstruction overhead, context-accumulation overhead, the reasoning break-even condition, and the task-level cost framework for reasoning allocation and state reuse.

### 7. [ArcGrav & Operational Leverage](./Operational_Leverage/README.md#paper-operational-leverage)

**Operational Leverage:** How much successful autonomous work can ultimately be induced per unit of human specification and intervention effort?

Operational leverage is studied through independent observational design and analysis of model usage telemetry.

### 8. [Context Triad](./Context_Triad/#paper-context-triad)

Unifies three contextual forces as position, order-sensitive history, and relative semantic magnitude, and owns their shared decomposition, experimental separability, and interaction design.

- [Semantic Locality](./Context_Triad/Semantic_Locality.md#paper-semantic-locality): How does position relative to surrounding context and point of use affect behavioral influence?

> Context position, points of use, physical and relative locality, local semantic neighborhoods, beginning/middle/end placement, locality profiles, relocation, refresh, materialization, and controlled measurement of position-sensitive instruction influence.

- [Semantic Shadow](./Context_Triad/Semantic_Shadow.md#paper-semantic-shadow): How does recent context change the effective influence of earlier context?

> Backward contextual influence, interpretation state across conversational history, interpretation regimes, persistent historical dependence, neutral versus competing continuations, interference, mutation and supersession, shadow accumulation, normalization, temporal coupling, restartability, and controlled measurement of later-context effects on earlier semantics.

- [Semantic Weight](./Context_Triad/Semantic_Weight.md#paper-semantic-weight): How does relative semantic mass affect the influence of larger and smaller context structures?

> Semantic mass, competitive and global contextual weight, weight ratios, instruction dominance, reinforcement, dilution, proportional scaling, effective semantic influence, and controlled measurement of semantic-mass asymmetry.

## Shared Operational Baseline

### [External Operational Baseline for Agentic Software Engineering](./Agentic_Software_Engineering_Operational_Baseline.md#paper-operational-baseline)

This representation-neutral baseline uses standardized SWE-rebench software-engineering trajectories to establish external operating references for Codex and other complete coding-agent systems.

It provides reusable reference quantities for delegation episodes, delegation depth, normalized trajectory depth, token load, outcome rate, and specification-normalized operational leverage. Operational-leverage studies can therefore compare an observed workflow against an external Codex reference and a broader coding-agent reference without treating another ArcGrav observation period as the default norm.

## Efficiency Dimensions

<a id="research-efficiency-dimensions"></a>
<a id="research-efficiency-hierarchy"></a>
The research distinguishes five related but non-equivalent dimensions of efficiency:

1. **Serialization Efficiency** — Token cost of encoding a representation with assumed semantics.
2. **Compositional Efficiency** — Reduction in repetition through structure, binding, reference, and reuse.
3. **Interpretive Efficiency** — Representation-specific information required to recover intended semantics.
4. **Operational Leverage** — Successful autonomous work relative to human specification and intervention effort.
5. **Task-Completion Efficiency** — Accepted task completion relative to total model, tool, and human cost.

These dimensions measure different aspects of representation and execution. Improvements in one do not necessarily imply improvements in another.

## Related Representation and Context Concepts

<a id="research-signal-density"></a>
**Signal Density** describes how much execution-relevant structure is carried per unit of external representation.

**Semantic locality** describes where an instruction appears in the context relative to surrounding information and its point of use.

**Semantic shadow** describes how newer context changes the effective influence of earlier context.

**Semantic weight** describes how strongly a semantic object is represented relative to relevant competing semantic structures.

## Research Boundaries

The research distinguishes general representational claims from claims about ArcGrav specifically.

MNSR can remain useful even if ArcGrav's exact representation is later outperformed by another representation. Likewise, evidence that familiar structural cues, task recognition, associative retrieval, explicit binding, structured internal representations, prompt sensitivity, or context management are relevant mechanisms does not establish ArcGrav as uniquely optimal.

The stronger comparative and causal claims remain empirical questions. The individual papers state their own research status, measurement limits, and proposed controlled experiments.

## Core Terminology

<a id="research-model-native"></a>
**Model-Native** describes a representation that uses structural cues aligned with associations learned during model training, rather than relying solely on a bespoke syntax specification.

<a id="research-cross-model"></a>
**Cross-Model** describes the design goal of using the same representation across model families without model-specific syntax or runtimes. Portability is an empirical question, not a guarantee of equal performance.

<a id="research-model-invariant"></a>
**Model-Invariant** is the stronger empirical property of preserving intended interpretation or behavior under model substitution for a specified task and evaluation protocol.

## Canonical Concept Index

The links below are the canonical first substantive destinations for concepts defined by this research program. The index is grouped by conceptual role, providing a complementary view of the research architecture.

### Foundations & Scope

| Concept | Description |
| --- | --- |
| [Model-Native](#research-model-native) | Uses structural cues aligned with learned model associations. |
| [Cross-Model](#research-cross-model) | Works across model families without model-specific syntax. |
| [Model-Invariant](#research-model-invariant) | Preserves interpretation or behavior under model substitution. |
| [Model-Native Structural Representation (MNSR)](./Model_Native_Structural_Representation.md#mnsr) | External structure aligned with learned model representations. |
| [Representation Problem](./Model_Native_Structural_Representation.md#mnsr-representation-problem) | How to expose task-relevant relationships for reliable recovery. |
| [Signal Density](#research-signal-density) | Execution-relevant structure carried per unit of external representation. |

### Representation Structure, Dimensionality & Alignment

| Concept | Description |
| --- | --- |
| [Representation vs. Serialization](./Model_Native_Structural_Representation.md#mnsr-representation-vs-serialization) | Distinguishes semantic structure from its surface encoding. |
| [Channel Dimensionality](./Model_Native_Structural_Representation.md#mnsr-channel-dimensionality) | How communication is physically presented through the interface. |
| [Relational Dimensionality](./Model_Native_Structural_Representation.md#mnsr-relational-dimensionality) | Topology and relationships carried by a representation independent of serialization order. |
| [Latent Dimensionality](./Model_Native_Structural_Representation.md#mnsr-latent-dimensionality) | High-dimensional numerical representation inside the model. |
| [Relational Topology](./Model_Native_Structural_Representation.md#mnsr-relational-topology) | Pattern of task-relevant relationships among elements. |
| [Topology Preservation](./Model_Native_Structural_Representation.md#mnsr-topology-preservation) | Retaining relationships across representation changes. |
| [Learned Structural Priors](./Model_Native_Structural_Representation.md#mnsr-learned-structural-priors) | Structural associations acquired during broad model training. |
| [Model-Native Fit](./Model_Native_Structural_Representation.md#mnsr-model-native-fit) | Degree a representation aligns with learned structural priors for a model, task, and context. |
| [Prior Alignment](./Model_Native_Structural_Representation.md#mnsr-prior-alignment) | Match between representation cues and learned associations. |
| [Semantic Infrastructure](./Model_Native_Structural_Representation.md#mnsr-semantic-infrastructure) | Reusable conventions that carry established structural meaning. |
| [Round-Trip Fidelity](./Model_Native_Structural_Representation.md#mnsr-round-trip-fidelity) | How well consequential structure survives encode–interpret–reencode cycles. |
| [Representation Frontier](./Model_Native_Structural_Representation.md#mnsr-representation-frontier) | Conditional tradeoff frontier among human cost, model impedance, representational loss, and task fit. |
| [Interface Continuum](./Model_Native_Structural_Representation.md#mnsr-interface-continuum) | Continuum of communication interfaces extending beyond ordinary prompting. |
| [Optimal Structural Density](./Model_Native_Structural_Representation.md#mnsr-optimal-structural-density) | Best balance between explicit structure and representation cost. |
| [Minimal Sufficient Structure](./Model_Native_Structural_Representation.md#mnsr-minimal-sufficient-structure) | Practical target of externalizing consequential relationships without unnecessary representational machinery. |
| [Representation-Conditioned Task Performance](./Model_Native_Structural_Representation.md#mnsr-representation-conditioned-task-performance) | Task performance as a function of representation. |

### Representational Cost, Loss & Offloading

| Concept | Description |
| --- | --- |
| [Representational Impedance](./Model_Native_Structural_Representation.md#mnsr-representational-impedance) | Consequential mismatch between communicated structure and structure readily usable by the model. |
| [Encoding Cost](./Model_Native_Structural_Representation.md#mnsr-encoding-cost) | Cost of expressing the intended task in the chosen representation. |
| [Serialization Cost](./Model_Native_Structural_Representation.md#mnsr-serialization-cost) | Burden imposed by the communication channel and serialization. |
| [Acquisition Cost (MNSR)](./Model_Native_Structural_Representation.md#mnsr-acquisition-cost) | Representation-specific semantics that must be learned or established in context. |
| [Reconstruction Cost](./Model_Native_Structural_Representation.md#mnsr-reconstruction-cost) | Cost of inferring consequential relationships left implicit. |
| [Coordination Cost](./Model_Native_Structural_Representation.md#mnsr-coordination-cost) | Burden of maintaining recovered structure during execution. |
| [Representational Loss](./Model_Native_Structural_Representation.md#mnsr-representational-loss) | Consequential difference between intended and recovered structure. |
| [Transformation Distance](./Model_Native_Structural_Representation.md#mnsr-transformation-distance) | Functional transformation required before a representation yields usable task structure. |
| [Linearization Tax](./Model_Native_Structural_Representation.md#mnsr-linearization-tax) | Burden attributable to carrying non-sequential structure through a sequential channel. |
| [Structural Reconstruction Tax](./Model_Native_Structural_Representation.md#mnsr-structural-reconstruction-tax) | Avoidable reconstruction burden from insufficiently explicit task relationships. |
| [Representational Offloading](./Model_Native_Structural_Representation.md#mnsr-representational-offloading) | Encoding structure externally to reduce reconstruction work. |
| [Reduced Interpretive Branching](./Model_Native_Structural_Representation.md#mnsr-reduced-interpretive-branching) | Reduction in behaviorally plausible structural interpretations. |

### Model Recovery Mechanisms

| Concept | Description |
| --- | --- |
| [Representation Recovery Before Reasoning](./Model_Native_Structural_Representation.md#mnsr-representation-recovery-before-reasoning) | Functional separation between recovering task structure, reasoning over it, and executing it. |
| [Task Recognition](./Model_Native_Structural_Representation.md#mnsr-task-recognition) | Recognizing a supported task or structural pattern from current-context evidence. |
| [Associative Retrieval](./Model_Native_Structural_Representation.md#mnsr-associative-retrieval) | Activation or retrieval of learned representational associations from familiar external structure. |
| [Internal Semantic & Task Structure](./Model_Native_Structural_Representation.md#mnsr-internal-semantic-task-structure) | Model-side structured representations associated with semantics, tasks, or operations. |
| [Information Anchors & Binding](./Model_Native_Structural_Representation.md#mnsr-information-anchors-binding) | Repeated labels, references, and local schemas that support identity and contextual binding. |
| [Prompt Sensitivity](./Model_Native_Structural_Representation.md#mnsr-prompt-sensitivity) | Behavioral sensitivity to ordering, lexical form, and representational choices. |

### Instructional & Compositional Structure

| Concept | Description |
| --- | --- |
| [Instructional Representation](./Instructional_Representation.md#ir-instructional-representation) | Structured expression of instructions and their relationships. |
| [Instruction Structure](./Instructional_Representation.md#ir-instruction-structure) | Scope, priority, reference, constraints, and transformations. |
| [Program Structure](./Instructional_Representation.md#ir-program-structure) | Executable control and data relationships characteristic of programs. |
| [Model-Native Instructional Representation](./Instructional_Representation.md#ir-model-native-instructional-representation) | Instruction structure using model-familiar structural cues. |
| [Instructional Primitives](./Instructional_Representation.md#ir-instructional-primitives) | Basic structural units used to express instructions. |
| [Prose–Program Boundary](./Instructional_Representation.md#ir-prose-program-boundary) | Boundary between natural-language instruction and executable structure. |
| [Representational Continuum](./Instructional_Representation.md#ir-representational-continuum) | Spectrum from prose through structured forms to code. |
| [Semantic-Function Matching](./Instructional_Representation.md#ir-semantic-function-matching) | Choosing representation whose learned function matches intended meaning. |
| [Serialization Efficiency](./ArcGrav_Syntax_Efficiency.md#syntax-serialization-efficiency) | Tokens needed to encode assumed semantics. |
| [Compositional Efficiency](./ArcGrav_Syntax_Efficiency.md#syntax-compositional-efficiency) | Reuse achieved through structure, binding, and reference. |
| [Token Minimality](./ArcGrav_Syntax_Efficiency.md#syntax-token-minimality) | Minimizing tokens without losing required semantics. |
| [Symbolic References](./ArcGrav_Syntax_Efficiency.md#syntax-symbolic-reference) | Compact identifiers for established entities or structure. |
| [Reference Amortization](./ArcGrav_Syntax_Efficiency.md#syntax-reference-amortization) | Reusing references to spread setup cost across uses. |

### Interpretation Lifecycle & Context Triad

| Concept | Description |
| --- | --- |
| [Interpretive Efficiency](./ArcGrav_Interpretive_Efficiency.md#interpretive-interpretive-efficiency) | Degree intended representation semantics are recoverable without additional representation-specific specification. |
| [Specification Requirement](./ArcGrav_Interpretive_Efficiency.md#interpretive-specification-requirement) | Minimum representation-specific specification needed to reach a target interpretation accuracy. |
| [Acquisition, Maintenance, and Repair Cost](./ArcGrav_Interpretive_Efficiency.md#interpretive-acquisition-maintenance-repair) | Lifecycle decomposition of representation-specific interpretation cost. |
| [Interpretive Acquisition Cost](./ArcGrav_Interpretive_Efficiency.md#interpretive-acquisition-cost) | Cost to establish representation-specific semantics. |
| [Interpretive Maintenance Cost](./ArcGrav_Interpretive_Efficiency.md#interpretive-maintenance-cost) | Cost to refresh, restate, or normalize representation semantics over time. |
| [Interpretive Repair Cost](./ArcGrav_Interpretive_Efficiency.md#interpretive-repair-cost) | Cost of correcting failures attributable to representation interpretation. |
| [Zero-Specification Interpretability](./ArcGrav_Interpretive_Efficiency.md#interpretive-zero-specification-interpretability) | Correct recovery of intended structural relationships without a local representation specification. |
| [Cold Start](./ArcGrav_Interpretive_Efficiency.md#interpretive-cold-start) | Interpretation from no prior representation-specific context. |
| [Specification Dose](./ArcGrav_Interpretive_Efficiency.md#interpretive-specification-dose) | Amount of representation-specific explanatory information supplied. |
| [Randomized Isomorphic Representations](./ArcGrav_Interpretive_Efficiency.md#interpretive-randomized-isomorphic-representations) | Semantically equivalent structures with randomized unfamiliar surface conventions. |
| [Cross-Model Portability](./ArcGrav_Interpretive_Efficiency.md#interpretive-cross-model-portability) | Usability of the same representation across model families without model-specific syntax or runtimes. |
| [Representation Recognition](./ArcGrav_Interpretive_Efficiency.md#interpretive-representation-recognition) | Recovering representation semantics primarily from model-internalized associations and local structure. |
| [Representation Acquisition](./ArcGrav_Interpretive_Efficiency.md#interpretive-representation-acquisition) | Establishing a new semantic mapping from current-context definitions, demonstrations, or grammar. |
| [Semantic Remappability](./ArcGrav_Interpretive_Efficiency.md#interpretive-semantic-remappability) | Ability to override familiar representational associations with deliberately redefined local semantics. |
| [Lifecycle Amortization](./ArcGrav_Interpretive_Efficiency.md#interpretive-lifecycle-amortization) | Spreading representation acquisition cost across repeated use. |
| [Interpretation Regime](./Context_Triad/Semantic_Shadow.md#shadow-interpretation-regime) | Conventions required to map a representation to intended operational meaning across conversational history. |
| [Model-Internalized Interpretation Regime](./Context_Triad/Semantic_Shadow.md#shadow-model-internalized-regime) | Interpretation supplied primarily by broadly learned model conventions. |
| [Contextual Interpretation Regime](./Context_Triad/Semantic_Shadow.md#shadow-contextual-regime) | Conversation-specific semantic conventions introduced in the current interaction. |
| [Interpretation State](./Context_Triad/Semantic_Shadow.md#shadow-interpretation-state) | Historical state needed to interpret current expressions. |
| [Task State](./Context_Triad/Semantic_Shadow.md#shadow-task-state) | Historical facts about the task being performed rather than how expressions are interpreted. |
| [Persistent Regime Dependence](./Context_Triad/Semantic_Shadow.md#shadow-persistent-regime-dependence) | Reliance on earlier conversation-specific interpretive state. |
| [Physical Locality](./Context_Triad/Semantic_Locality.md#locality-physical-distance) | Absolute distance along the input sequence between an instruction and its point of use. |
| [Relative Locality](./Context_Triad/Semantic_Locality.md#locality-relative-locality) | Instruction-to-use distance normalized by active context length. |
| [Point of Use](./Context_Triad/Semantic_Locality.md#locality-point-of-use) | Position at which a semantic object must affect interpretation or behavior. |
| [Local Semantic Neighborhood](./Context_Triad/Semantic_Locality.md#locality-neighborhood) | Nearby context immediately surrounding an instruction. |
| [Locality Profile](./Context_Triad/Semantic_Locality.md#locality-multiple-support) | Distribution of localities across repeated support for the same semantic object. |
| [Semantic Locality](./Context_Triad/Semantic_Locality.md#locality-semantic-locality) | Position of an instruction in the input sequence relative to surrounding context and its point of use. |
| [Semantic Shadow](./Context_Triad/Semantic_Shadow.md#semantic-shadow) | Change in earlier semantic influence attributable to subsequently introduced context. |
| [Effective Influence](./Context_Triad/Semantic_Shadow.md#semantic-shadow-effective-influence) | Observable behavioral influence of a semantic object under active context. |
| [Semantic Interference](./Context_Triad/Semantic_Shadow.md#semantic-shadow-interference) | Newer context semantically competing with earlier context. |
| [Mutation & Supersession](./Context_Triad/Semantic_Shadow.md#semantic-shadow-mutation) | Newer context intentionally changing or replacing earlier semantic state. |
| [Shadow Accumulation](./Context_Triad/Semantic_Shadow.md#semantic-shadow-accumulation) | Change in earlier influence as subsequent context accumulates across turns. |
| [Frame Normalization](./Context_Triad/Semantic_Shadow.md#semantic-shadow-normalization) | Materializing current valid semantics instead of replaying amendment history. |
| [Temporal Coupling](./Context_Triad/Semantic_Shadow.md#shadow-temporal-coupling) | Dependence of current interpretation or behavior on earlier conversational state. |
| [Semantic Restartability](./Context_Triad/Semantic_Shadow.md#semantic-shadow-restartability) | Ability to transfer current operative semantics into fresh context. |
| [Semantic Mass](./Context_Triad/Semantic_Weight.md#semantic-weight-semantic-mass) | Contextual representation coherently supporting a semantic object. |
| [Relative Semantic Weight](./Context_Triad/Semantic_Weight.md#semantic-weight-relative-semantic-weight) | Semantic mass relative to the competing semantic field. |
| [Global Contextual Weight](./Context_Triad/Semantic_Weight.md#semantic-weight-global-weight) | Share of total active contextual semantic mass supporting an object. |
| [Weight Ratio](./Context_Triad/Semantic_Weight.md#semantic-weight-ratio) | Pairwise semantic-mass ratio between competing semantic objects. |
| [Semantic Reinforcement](./Context_Triad/Semantic_Weight.md#semantic-weight-semantic-reinforcement) | Increase in semantic mass through coherent additional support. |
| [Semantic Dilution](./Context_Triad/Semantic_Weight.md#semantic-weight-semantic-dilution) | Reduction in relative weight as competing semantic mass grows. |
| [Semantic Scale Invariance](./Context_Triad/Semantic_Weight.md#semantic-weight-scale-invariance) | Preservation of relative semantic weight under proportional scaling. |
| [Weight Preservation](./Context_Triad/Semantic_Weight.md#semantic-weight-weight-preservation) | Preservation of relative weight when relevant semantic masses scale proportionally. |
| [Effective Semantic Influence](./Context_Triad/Semantic_Weight.md#semantic-weight-effective-influence) | Observable behavioral effect attributable to a semantic object under a weight condition. |
| [Semantic Weight–Influence Curve](./Context_Triad/Semantic_Weight.md#semantic-weight-influence-curve) | Empirical relationship between relative semantic weight and effective influence. |

### Capacity, Complexity & Performance Frontier

| Concept | Description |
| --- | --- |
| [Intrinsic Capacity](./Representational_Capacity_Reclamation.md#rcr-intrinsic-capacity) | Model and execution-environment capability independent of representation overhead. |
| [Accessible Task Capacity](./Representational_Capacity_Reclamation.md#rcr-accessible-task-capacity) | Portion of capability that can be successfully directed toward the intended task through a representation. |
| [Representational Capacity Reclamation](./Representational_Capacity_Reclamation.md#rcr-representational-capacity-reclamation) | Recovery of model-side execution capacity by reducing representation-recovery and repair burden. |
| [Executional Capacity Efficiency](./Representational_Capacity_Reclamation.md#rcr-executional-capacity-efficiency) | Useful execution obtained from available model capacity. |
| [Effective Capacity Frontier](./Representational_Capacity_Reclamation.md#rcr-effective-capacity-frontier) | Maximum task complexity sustained above a success threshold under fixed resources. |
| [Frontier Multiplier](./Representational_Capacity_Reclamation.md#rcr-frontier-multiplier) | Ratio between effective capacity frontiers under matched conditions. |
| [Residual Frontier Headroom](./Representational_Capacity_Reclamation.md#rcr-residual-frontier-headroom) | Fraction of a representation's supported frontier remaining beyond a task's current complexity. |
| [Capacity Reclamation Ratio](./Representational_Capacity_Reclamation.md#rcr-capacity-reclamation-ratio) | Fraction of a stronger representation's frontier lying beyond a baseline saturation point. |
| [Useful Work Per Budget](./Representational_Capacity_Reclamation.md#rcr-useful-work-per-budget) | Accepted task complexity normalized by model-side execution budget. |
| [Marginal Utility of Reasoning](./Representational_Capacity_Reclamation.md#rcr-marginal-utility-of-reasoning) | Improvement in task quality produced by additional reasoning under a representation. |
| [Complexity Amplification](./Representational_Capacity_Reclamation.md#rcr-complexity-amplification) | Increasing representation-performance difference as relational task complexity rises. |
| [Cascading Reclamation](./Representational_Capacity_Reclamation.md#rcr-cascading-reclamation) | Capacity savings that propagate beyond the direct reduction in reconstruction burden. |
| [Fixed-Budget Breadth](./Representational_Capacity_Reclamation.md#rcr-fixed-budget-breadth) | Number of independent and interacting requirements handled under fixed resources. |
| [Fixed-Budget Depth](./Representational_Capacity_Reclamation.md#rcr-fixed-budget-depth) | Dependency depth, verification, or reasoning depth supported under fixed resources. |
| [Active Relational Load](./Representational_Capacity_Reclamation.md#rcr-active-relational-load) | Number of consequential relationships that must be simultaneously maintained across task elements. |
| [Relational Complexity](./Representational_Capacity_Reclamation.md#rcr-relational-complexity) | Task complexity arising from interacting entities, relationships, depth, precedence, and state. |

### Operational Leverage & Delegation

| Concept | Description |
| --- | --- |
| [Operational Leverage](./Operational_Leverage/README.md#ol-operational-leverage) | Successful autonomous work per unit of human specification and intervention effort. |
| [Useful-Work Leverage](./Operational_Leverage/README.md#ol-useful-work-leverage) | Validated useful autonomous work per unit of human effort. |
| [Activity Leverage](./Operational_Leverage/README.md#ol-activity-leverage) | Downstream model or agent activity per unit of human effort. |
| [Specification Compression](./Operational_Leverage/Studies/ArcGrav_Longitudinal_Operational_Leverage.md#ol-specification-compression) | Reduction in human specification burden while downstream computational activation is preserved. |
| [Delegation-Depth Leverage](./Operational_Leverage/Studies/ArcGrav_Single_Workstream_Delegation_Leverage.md#ol-delegation-depth-leverage) | More autonomous work depth per coherent specification or work packet. |
| [Evidence Hierarchy](./Operational_Leverage/README.md#ol-evidence-hierarchy) | Ordering from raw activity evidence toward validated user or organizational value. |
| [Delegation Episode](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-delegation-episode) | Externally supplied objective followed by autonomous execution to completion, submission, failure, or termination. |
| [Delegation Depth](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-delegation-depth) | Downstream activity per delegated objective. |
| [Specification-Normalized Operational Leverage](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-specification-normalized-leverage) | Downstream activity normalized by human specification burden. |
| [Steering Density](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-steering-density) | Human interventions per delegation episode. |
| [Outcome Rate](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-outcome-rate) | Fraction of delegation episodes reaching the target outcome. |
| [External Codex Reference](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-external-codex-reference) | Standardized Codex operating reference derived from SWE-rebench trajectories. |
| [Normalized Trajectory Depth](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-normalized-trajectory-depth) | Normalized trajectory events per delegation episode. |
| [External Coding-Agent Reference](./Agentic_Software_Engineering_Operational_Baseline.md#baseline-external-coding-agent-reference) | Common-task operating reference across complete coding-agent systems. |

### Task-Completion Economics

| Concept | Description |
| --- | --- |
| [Reasoning–Interaction Substitution](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-reasoning-interaction-substitution) | Trading additional model reasoning for reduced human interaction and repeated state acquisition. |
| [Single-Specification Completion](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-single-specification-completion) | Completing a task from one initial human specification without corrective or clarifying human turns. |
| [Task Trajectory](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-task-trajectory) | Complete model, context, tool, user-intervention, and output sequence from assignment to accepted completion. |
| [Accepted Completion](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-accepted-completion) | Satisfaction of completion criteria without further corrective interaction. |
| [Reasoning Effort](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-reasoning-effort) | Model policy governing internal reasoning allocation for an inference trajectory. |
| [Interaction Burden](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-interaction-burden) | Human work required after the initial specification to keep execution progressing correctly. |
| [State-Reconstruction Overhead](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-state-reconstruction-overhead) | Model and tool work spent reacquiring task-relevant state already acquired earlier. |
| [Correction Overhead](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-correction-overhead) | Full downstream work caused by an earlier trajectory failing to satisfy the task correctly. |
| [Redundant Execution Overhead](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-redundant-execution-overhead) | Tool or model work repeated because an earlier branch did not survive into the accepted solution. |
| [Context-Accumulation Overhead](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-context-accumulation-overhead) | Repeated processing cost caused by retaining increasingly large interaction history. |
| [Task-Completion Cost](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-task-completion-cost) | Total model, tool, and human cost required to reach accepted completion. |
| [Task-Completion Efficiency](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-task-completion-efficiency) | Accepted completion achieved per total task-level cost. |
| [Reasoning Break-Even Condition](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-reasoning-break-even-condition) | Condition under which added reasoning costs less than the downstream reconstruction, correction, redundancy, and interaction it avoids. |
| [Failure Amplification](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-failure-amplification) | Downstream cost growth induced by an early reasoning or task-model error. |
| [State-Compressed Handoff](./ArcGrav_Reasoning_Interaction_Substitution.md#ris-state-compressed-handoff) | Compact transfer of decision-relevant task state between trajectories. |

### Hypotheses & Experimental Constructs

| Construct | Description |
| --- | --- |
| [Structural Recovery Hypothesis](./Model_Native_Structural_Representation.md#mnsr-structural-recovery-hypothesis) | More explicit consequential relationships should reduce relational reconstruction errors. |
| [Complexity Scaling Hypothesis](./Model_Native_Structural_Representation.md#mnsr-complexity-scaling-hypothesis) | Advantages of topology-preserving representation should increase with relational complexity more strongly than raw prompt length. |
| [MNSR Prior-Alignment Hypothesis](./Model_Native_Structural_Representation.md#mnsr-prior-alignment-hypothesis) | Familiar learned conventions should require less representation-specific instruction than randomized isomorphic encodings. |
| [Round-Trip Performance Hypothesis](./Model_Native_Structural_Representation.md#mnsr-round-trip-performance-hypothesis) | More faithful recovery of consequential topology should predict more reliable execution and verification. |
| [Stateful Coordination Hypothesis](./Model_Native_Structural_Representation.md#mnsr-stateful-coordination-hypothesis) | Explicit state, control, and termination structure should reduce longitudinal coordination failures. |
| [Representation-Frontier Hypothesis](./Model_Native_Structural_Representation.md#mnsr-representation-frontier-hypothesis) | No representation should dominate across all tasks; optimal forms should occupy a conditional tradeoff frontier. |
| [Channel-Substitution Hypothesis](./Model_Native_Structural_Representation.md#mnsr-channel-substitution-hypothesis) | Model-supported structured channels should reduce relational errors when they preserve task relations better than diffuse prose. |
| [Learned-Interface Hypothesis](./Model_Native_Structural_Representation.md#mnsr-learned-interface-hypothesis) | Learned structured mappings can outperform hand-authored serialization when they preserve task relations with lower total impedance. |
| [Representation-Cost Hypothesis](./ArcGrav_Interpretive_Efficiency.md#interpretive-representation-cost-hypothesis) | Isomorphic representations can require different amounts of context-specific information to reach matched interpretation accuracy. |
| [Interpretive Prior-Alignment Hypothesis](./ArcGrav_Interpretive_Efficiency.md#interpretive-prior-alignment-hypothesis) | Model-internalized, mutually compatible cues should require less local specification than randomized isomorphic encodings. |
| [Interpretation-Cost / Performance Frontier](./ArcGrav_Interpretive_Efficiency.md#interpretive-interpretation-cost-frontier) | Comparative frontier relating representation-specific interpretation cost to achieved performance. |
| [Operational-Value Hypothesis](./ArcGrav_Interpretive_Efficiency.md#interpretive-operational-value-hypothesis) | Lower interpretation cost is useful only when recovered semantics preserve or improve downstream execution. |
| [ArcGrav Design Hypothesis](./ArcGrav_Interpretive_Efficiency.md#interpretive-arcgrav-design-hypothesis) | ArcGrav should obtain compositional structure with little representation-specific teaching in the current interaction. |
| [Semantic Locality Hypothesis](./Context_Triad/Semantic_Locality.md#locality-position-hypothesis) | Moving an instruction to a different context position can change its influence when semantic content and weight are controlled. |
| [Relative-Position Hypothesis](./Context_Triad/Semantic_Locality.md#locality-relative-position-hypothesis) | Normalized instruction position may explain behavior not captured by absolute instruction-to-use distance alone. |
| [Non-Uniform Position Hypothesis](./Context_Triad/Semantic_Locality.md#locality-middle-hypothesis) | Instruction influence across context positions should be non-uniform rather than obeying a universal monotonic distance law. |
| [Local Refresh Hypothesis](./Context_Triad/Semantic_Locality.md#locality-refresh-hypothesis) | Restating an instruction near use should improve adherence when remote placement is limiting, after weight and shadow are controlled. |
| [Locality-Profile Hypothesis](./Context_Triad/Semantic_Locality.md#locality-profile-hypothesis) | Distributed support can behave differently from single support when locality profiles differ at similar semantic mass. |
| [Semantic Shadow Hypothesis](./Context_Triad/Semantic_Shadow.md#semantic-shadow-hypothesis) | Later context can change earlier semantic influence when locality and weight are controlled. |
| [Shadow Recency Hypothesis](./Context_Triad/Semantic_Shadow.md#semantic-shadow-recency-hypothesis) | Competing context nearer the point of use should generally exert greater backward influence than equivalent less-recent competition. |
| [Shadow Competition Hypothesis](./Context_Triad/Semantic_Shadow.md#semantic-shadow-interference-hypothesis) | Competing later context should produce greater shadow than neutral later context of comparable size and locality. |
| [Shadow Accumulation Hypothesis](./Context_Triad/Semantic_Shadow.md#semantic-shadow-accumulation-hypothesis) | Unrefreshed earlier instructions should change in effective influence as subsequent context accumulates. |
| [Shadow Normalization Hypothesis](./Context_Triad/Semantic_Shadow.md#semantic-shadow-normalization-hypothesis) | Materializing current valid rules should reduce stale-history errors after repeated revisions. |
| [Semantic Weight Hypothesis](./Context_Triad/Semantic_Weight.md#semantic-weight-hypothesis) | At matched locality and recency, influence depends partly on semantic mass relative to competing semantic objects. |
| [Instruction-Dominance Hypothesis](./Context_Triad/Semantic_Weight.md#semantic-weight-dominance-hypothesis) | Increasing one competing instruction structure's relative semantic mass should increase its behavioral influence. |
| [Semantic Reinforcement Hypothesis](./Context_Triad/Semantic_Weight.md#semantic-weight-reinforcement-hypothesis) | Coherent additional semantic support should increase effective weight more reliably than equal unrelated text. |
| [Proportional-Scaling Hypothesis](./Context_Triad/Semantic_Weight.md#semantic-weight-scale-invariance-hypothesis) | Proportionally scaled competing semantic masses should preserve relative influence more than one-sided scaling. |
| [Semantic Weight Restoration Hypothesis](./Context_Triad/Semantic_Weight.md#semantic-weight-restoration-hypothesis) | Restoring a diluted semantic-mass ratio should restore influence toward its earlier level. |
| [Specification Ablation](./ArcGrav_Interpretive_Efficiency.md#interpretive-specification-ablation) | Tests whether explicitly explaining ArcGrav semantics changes interpretation or performance. |
| [Prior-Conflict Remapping](./ArcGrav_Interpretive_Efficiency.md#interpretive-prior-conflict-remapping) | Tests the cost of overriding familiar model associations with deliberately conflicting local meanings. |
| [Semantic Cue Ablation](./ArcGrav_Interpretive_Efficiency.md#interpretive-semantic-cue-ablation) | Replaces individual structural cues to isolate their interpretive contribution. |
| [Capacity Reclamation Hypothesis](./Representational_Capacity_Reclamation.md#rcr-capacity-reclamation-hypothesis) | Lower representation-recovery cost should free capacity for task reasoning, verification, and execution. |
| [Effective Capacity Frontier Hypothesis](./Representational_Capacity_Reclamation.md#rcr-effective-capacity-frontier-hypothesis) | Lower-impedance representations should sustain acceptable execution to higher task complexity under fixed resources. |
| [Complexity-Amplification Hypothesis](./Representational_Capacity_Reclamation.md#rcr-complexity-amplification) | Representation-performance differences should increase as relational task complexity rises. |
| [Cascading Reclamation Hypothesis](./Representational_Capacity_Reclamation.md#rcr-cascading-reclamation) | Avoiding an early reconstruction error can save all dependent downstream computation, not only the initial recovery work. |
| [Fixed-Budget Breadth Hypothesis](./Representational_Capacity_Reclamation.md#rcr-fixed-budget-breadth) | Lower-impedance representations should support more simultaneous requirements under fixed execution budgets. |
| [Fixed-Budget Depth Hypothesis](./Representational_Capacity_Reclamation.md#rcr-fixed-budget-depth) | Reclaimed capacity should permit deeper dependency traversal or verification when breadth is held constant. |

## Editorial conventions

All substantive papers follow the [Research Manuscript Style Guide](./Style_Guide/README.md): standalone construct definitions, concise evidence-status statements, consistent section roles, and author–year references. External scholarly sources are indexed in the [reference catalog](./Style_Guide/reference_catalog.json). Experimental records and software documentation retain task-appropriate structures.
