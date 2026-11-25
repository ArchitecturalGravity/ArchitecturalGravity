<a id="context-triad-portal"></a>

<p align="center">
  <img src="./Assets/triad.svg" alt="Context Triad" width="66%">
</p>

# Context Triad — Research Portal

The Context Triad is a research framework for examining how the placement, subsequent history, and relative support of represented meaning affect language-model behavior. Its central distinction is between meaning that remains present or recoverable in context and meaning that actually governs a later operation.

This directory brings together the theoretical papers, proposed extensions, literature mapping, interactive visualization, and empirical investigations. Each document has its own role in the research program.

<a id="paper-context-triad"></a>
<a id="context-triad"></a>

## Core Framework

Start with the [Context Triad](./Context_Triad.md#paper-context-triad), the main paper defining the shared thesis, semantic objects and representations, points of use, behavioral consistency, and interactions among the three primary dimensions.

| Paper | Role |
| --- | --- |
| [Context Triad](./Context_Triad.md#paper-context-triad) | Unified framework, shared definitions, interactions, and measurement strategy |
| [Semantic Locality](./Semantic_Locality.md#paper-semantic-locality) | Placement and distribution of representations relative to use; positional profiles and response contrasts |
| [Semantic Shadow](./Semantic_Shadow.md#paper-semantic-shadow) | Subsequent semantic context and order-sensitive influence; suppression, reinforcement, reinterpretation, and supersession |
| [Semantic Weight](./Semantic_Weight.md#paper-semantic-weight) | Coherent support relative to competing meanings; support proxies, ratios, and response measurements |

## Extended Framework and Research Atlas

| Document | Role |
| --- | --- |
| [Extended Context Triad](./Extended_Context_Triad.md#paper-extended-context-triad) | Develops six proposed compound and higher-order constructs from the primary dimensions: Continuity, Concentration, Momentum, Anchoring, Trajectory, and Consolidation |
| [Context Triad Research Atlas](./Research_Atlas/README.md#context-triad-research-atlas) | Maps established external research and engineering practices onto the primary and proposed derived constructs, distinguishing direct factor research, related evidence, and applied engineering |

The extended constructs describe conceptual relationships, not established independent mechanisms. The Atlas relates the framework to existing work without treating conceptual overlap as validation.

## Interactive Model

The [Context Triad Model](./Context_Triad_Model/README.md#paper-context-triad-model) provides an interactive visual demonstration of how Locality, Shadow, and Weight may interact.

Open [Context_Triad_Model.html](./Context_Triad_Model/Context_Triad_Model.html) locally in a browser to explore the visualization. Its controls and outputs are illustrative rather than calibrated behavioral predictions.

## Empirical Studies

The [Studies index](./Studies/README.md#context-triad-studies) catalogs investigations, their evidence status, and collection conventions.

| Study | Focus |
| --- | --- |
| [Fox–Leopard Displacement](./Studies/Fox_Leopard_Displacement.md#paper-fox-leopard-answer-displacement) | Semantic weight, pangram inference, and answer displacement across fixed-slot layouts; 360 scored trials |
| [Planetary Chain Activation](./Studies/Planetary_Chain_Activation.md#paper-planetary-chain-activation) | Order-dependent associative recognition; three-condition reported pilot |
| [Glip Preference Anchoring](./Studies/Glip_Preference_Anchoring.md#paper-glip-preference-anchoring) | Label, description, position, and rival-order dependence in criterion-free selection; 360 trials |

Supporting trial records are available in [Studies/Data](./Studies/Data/). Individual reports specify their methods, observations, controls, and limitations; inclusion in the collection does not establish causal validation of the framework.

## Reading Paths

| Goal | Recommended sequence |
| --- | --- |
| Understand the theory | Context Triad → Semantic Locality, Semantic Shadow, and Semantic Weight |
| Explore combined relationships | Context Triad → Extended Context Triad → Research Atlas |
| Visualize the interactions | Context Triad → Context Triad Model |
| Examine empirical evidence | Studies index → individual reports and their supporting data |
| Relate the framework to existing research | Research Atlas → cited publications and component papers |

## Related Resources

- [Architectural Gravity Research](../README.md#research-index) — the wider research program.
- [Research Agent References](../Agent_References/research_agent_reference_index.yaml) — machine-readable research navigation and source-anchored summaries.
- [Triad diagram](./Assets/triad.svg) and [Research Atlas assets](./Research_Atlas/Assets/) — visual resources used by the papers and atlas.
