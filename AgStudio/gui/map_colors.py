"""Display colors carried by exact source slices through validated block moves.

These are paint data, not reusable inference results. Only a validated source
permutation can transfer them; editor undo history owns their lifetime.
"""
from dataclasses import dataclass

from ..shared.recognition import SourceSpan


@dataclass(frozen=True)
class MapColors:
    source: str
    mode: str
    nodes: tuple
    unowned: tuple
    positions: tuple = ()
    colors: tuple = ()

    def moved(self, plan):
        """Carry every colored character, splitting intervals at cut boundaries.

        A node's exact span is its identity here, so repeated declarations and
        equal-looking blocks never get matched by their label or numeric ID.
        ST2 display names remain opaque palette keys, never current evidence.
        """
        mapping = plan.offset_map
        nodes = tuple((mapping.span(span), color) for span, color in self.nodes)
        positions = []
        cuts = (mapping.old_start, mapping.old_end, mapping.destination)
        for start, end, names in self.positions:
            boundaries = sorted({start, end, *(cut for cut in cuts if start < cut < end)})
            for first, last in zip(boundaries, boundaries[1:]):
                span = mapping.span(SourceSpan(first, last))
                positions.append((span.start, span.end, names))
        return MapColors(plan.source, self.mode, nodes, self.unowned,
                         tuple(sorted(positions)), self.colors)
