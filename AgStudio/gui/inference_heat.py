"""Document-map compatibility and color presentation for detached graph scores.

Graph calculation lives in shared.graph; syntax adaptation lives in its adapter.
This facade preserves the existing GUI-facing names without adding a Qt import.
"""
from dataclasses import dataclass, field

from ..shared.graph import (
    HeatCancelled, HeatScore, SemanticCoverage, SemanticView, calculate_graph, score_relations,
    normalize_graph_mode, GraphSnapshot,
)
from ..shared.graph.adapter import build_graph_snapshot, whole_block_owners


MODE_LABELS = {
    'heuristic': 'Heuristic',
    'semantic_triad_1': 'Semantic Triad 1',
    'semantic_triad_2': 'Semantic Triad 2',
}
MODE_CODES = {'heuristic': 'H', 'semantic_triad_1': 'ST1', 'semantic_triad_2': 'ST2'}
SEMANTIC_HELP = ('Semantic Triad source-character inherited-baseline proxy:\n'
                 '- Every named or structural element has one final baseline B\n'
                 '- B covers its source and all reachable utilized support\n'
                 '- Overlapping and repeated support spans count only once\n'
                 '- Complete-document support is locality-weighted at the end\n'
                 '- Source readout is the element\'s inclusive definition coverage\n'
                 '- Shadow/conflict is not inferred from plain text')
MODE_HELP = {
    'heuristic': ('Heuristic based LLM inference speculation:\n'
                 '- Direct and indirect local-reference reinforcement'),
    'semantic_triad_1': (SEMANTIC_HELP + '\n\nWhole-block color: the arithmetic mean of its ST2 '
                         'source-defined component intensities; a visual summary, not total support.'),
    'semantic_triad_2': (SEMANTIC_HELP + '\n\nSource-aligned color: element baselines with resolved '
                         'reference spans showing their targets; exact source-position hover.'),
}


@dataclass(frozen=True)
class HeatModel:
    owners: dict[int, int]
    scores: dict[int, HeatScore]
    relations: tuple[tuple[int, int], ...]
    mode: str = "heuristic"
    states: dict[int, dict[str, float]] = field(default_factory=dict)
    details: dict[int, tuple[SemanticCoverage, ...]] = field(default_factory=dict)
    decay: float = 1.0
    views: dict[int, SemanticView] = field(default_factory=dict)
    view_details: dict[int, tuple[SemanticCoverage, ...]] = field(default_factory=dict)

    position_values: dict[int, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    position_maximum: float = 0.0
    position_snapshot: GraphSnapshot | None = None
    final_details: tuple[SemanticCoverage, ...] = ()
    final_values: dict[str, float] = field(default_factory=dict, init=False)
    final_labels: dict[str, str] = field(default_factory=dict, init=False)
    position_evaluator: object = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'mode', normalize_graph_mode(self.mode))
        details = self.final_details or next(iter(self.view_details.values()), ())
        object.__setattr__(self, 'final_values', {item.object: item.adjusted_linked for item in details})
        elements = getattr(self.position_snapshot, 'semantic_elements', ())
        object.__setattr__(self, 'final_labels', {item.object: item.label or item.object
                                               for item in elements})
        if self.mode == 'semantic_triad_2' and self.position_snapshot is not None:
            from ..shared.graph.semantic import PreparedSemantic
            object.__setattr__(self, 'position_evaluator',
                               PreparedSemantic(self.position_snapshot, automatic=True, cache_size=16))



def compute_heat(tree, semantics, *, mode="heuristic", options=None, cancelled=None):
    """Preserve the legacy dictionary view over the detached graph pipeline."""
    mode = normalize_graph_mode(mode)
    kwargs = {} if mode == "heuristic" and not options else {"mode": mode, "options": options}
    snapshot = build_graph_snapshot(tree, semantics, cancelled=cancelled, **kwargs)
    result = calculate_graph(snapshot, cancelled=cancelled)
    return HeatModel(dict(result.owners), dict(result.scores), result.relations, mode,
                     {block: dict(values) for block, values in result.states},
                     details=dict(result.details), decay=snapshot.options.decay,
                     views={view.node: view for view in result.semantic_views},
                     view_details=dict(result.view_details),
                     position_values=dict(result.position_values),
                     position_maximum=result.position_maximum,
                     position_snapshot=result.position_snapshot, final_details=result.final_details)


def heat_rgb(score, minimum, maximum):
    """Normalize an uncapped raw score against all blocks in the document."""
    if maximum <= 0:
        return (0, 0, 255)
    if maximum == minimum:
        return (128, 0, 128)
    fraction = max(0.0, min(1.0, (score - minimum) / (maximum - minimum)))
    return (round(255 * fraction), 0, round(255 * (1.0 - fraction)))
