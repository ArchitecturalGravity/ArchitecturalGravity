"""Qt-free map process input; parser adaptation and scoring share one child."""
from dataclasses import dataclass
import json

from ..analysis_snapshot import (AnalysisSnapshot, DocumentSnapshot, PackedAnalysisSnapshot,
                                 restore_document, unpack_analysis)
from .adapter import build_graph_snapshot
from .core import GraphSnapshot, calculate_graph


@dataclass(frozen=True, slots=True)
class MapRequest:
    analysis: AnalysisSnapshot | DocumentSnapshot | PackedAnalysisSnapshot
    mode: str = 'heuristic'
    options_json: str = '{}'


def calculate_map_request(request):
    # Injected calculations and existing graph fixtures can still pass a pure
    # numeric snapshot to the same process manager.
    if isinstance(request, GraphSnapshot):
        return calculate_graph(request)
    if not isinstance(request, MapRequest):
        raise TypeError('map calculation requires MapRequest')
    analysis = unpack_analysis(request.analysis) if isinstance(request.analysis, PackedAnalysisSnapshot) else request.analysis
    if isinstance(analysis, AnalysisSnapshot):
        tree, semantics = analysis.tree, analysis.semantics
    else:
        document = restore_document(analysis)
        from ..lint.syntax import parse
        from ..lint.semantics import resolve
        tree = parse(document)
        semantics = resolve(document, tree)
    options = json.loads(request.options_json)
    kwargs = {} if request.mode == 'heuristic' and not options else {
        'mode': request.mode, 'options': options}
    return calculate_graph(build_graph_snapshot(tree, semantics, **kwargs))
