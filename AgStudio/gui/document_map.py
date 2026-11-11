"""Infer Map silhouettes with fitted-to-1:1 zoom and whole-block heat.

Each visual row belongs to one nearest section, or its owning structural block.
Nested sections partition their parents instead of painting overlapping fills.
Qt supplies glyph/tab/UTF-16 geometry; the existing parser supplies ownership.
"""
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from dataclasses import dataclass
import math
import heapq
import struct
from textwrap import fill

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTextCharFormat, QTextLine
from PySide6.QtWidgets import QApplication, QWidget

from ..shared.lint.syntax import parse
from ..shared.graph.adapter import build_graph_snapshot
from ..shared.lint.block_move import BlockMoveModel
from .inference_heat import MODE_HELP, MODE_LABELS, heat_rgb, normalize_graph_mode
from .map_tooltip import MapTooltip
from .map_colors import MapColors
from .pending_spinner import paint_pending_spinner


MAP_HELP = ('Infer Map\n\n'
            'Relative inferential-influence emphasis heuristic correlations.\n\n'
            'Represents a portrayal of competing\n'
            'semantics to speculate LLM interpretation.\n\n'
            '- Blue is least influential\n'
            '- Red is most influential')
MAP_ACCESSIBLE_HELP = (MAP_HELP + '\n\nStatic local-correlation heuristic, '
                       'not measured model attention. '
                       'Wheel zooms line heights from fit to 1:1; drag divider to scale widths.')
UNOWNED_COLOR = (128, 128, 128)
EDIT_SELECTED_COLOR = (255, 165, 0)
EDIT_ARROW_COLOR = (0, 220, 90)
EDIT_ARROW_RIGHT_INSET = 10  # Screen pixels; leaves room for the head and stroke.
EDIT_INVALID_COLOR = (255, 50, 50)
EDIT_HELP = ('Infer Edit\n\nInference is paused. Click anywhere between the orange lines to select a map object.\n'
             'Green arrows: down for its sources, up for objects using it.\n'
             'Drag vertically to reorder within the same scope. A line marks a valid insertion; a red X cancels the drop.\n'
             'Escape cancels. Click above or below the objects to clear. Arrows show direct resolved correlations.')
PENDING_COLOR = (96, 118, 139)
POSITION_COMMAND_BYTE_LIMIT = 8 * 1024 * 1024
POSITION_COMMAND_ROW_LIMIT = 2048


@dataclass(frozen=True)
class MapRow:
    start: int
    top: float
    height: float
    left: float
    right: float
    owner: int | None
    end: int = 0


@dataclass(frozen=True)
class EditRegion:
    """Full-width selection band in document coordinates, bottom exclusive."""
    owner: int | None
    top: float
    bottom: float


@dataclass(frozen=True)
class PositionSegment:
    """One source-aligned display span with its source start and identity."""
    position: int
    object: str | None
    rect: QRectF
    color: tuple[int, int, int]


@dataclass(frozen=True)
class PositionInterval:
    """Source-defined interval, clipped to one visual row before identity layout."""
    start: int
    end: int
    left: float
    right: float
    objects: tuple[str, ...]


class SourcePositionIndex:
    """Sparse code-point/Qt UTF-16 conversion, including collapsed CRLFs.

    Storage follows encoding exceptions, never characters times identities.
    At a collapsed CRLF boundary, inverse conversion chooses after the LF.
    Qt cannot distinguish those two coincident, nonprinting source boundaries.
    """
    def __init__(self, source):
        self.length = len(source)
        self._stops, self._deltas = [], []
        delta = 0
        previous = ''
        for index, char in enumerate(source):
            change = (-1 if (char == '\n' and previous == '\r')
                      or (index == 0 and char == '\ufeff') else int(ord(char) > 0xffff))
            if change:
                delta += change
                self._stops.append(index + 1)
                self._deltas.append(delta)
            previous = char

    def display(self, source_position):
        index = bisect_right(self._stops, source_position) - 1
        return source_position + (self._deltas[index] if index >= 0 else 0)

    def source(self, display_position):
        if not self._stops:
            return min(self.length, max(0, display_position))
        low, high = 0, self.length
        while low < high:
            middle = (low + high + 1) // 2
            if self.display(middle) <= display_position:
                low = middle
            else:
                high = middle - 1
        return low


@dataclass(frozen=True)
class BlockColorSummary:
    component_count: int
    mean_intensity: float


def display_offsets(source, offsets):
    """Convert sorted source boundaries to Qt positions in one linear pass."""
    result = {}
    previous = ''
    position = 0
    index = 0
    for stop in sorted(set(offsets)):
        while index < stop:
            char = source[index]
            if char != '\n' or previous != '\r':
                position += 2 if ord(char) > 0xffff else 1
            previous = char
            index += 1
        result[stop] = position
    return result


def section_owners(tree):
    """Resolve already observed links once, without inferring new hierarchy."""
    owners = {}
    sections = {}
    for node in tree.nodes:
        # Parser links refer to earlier nodes. Recovered boundaries stay local.
        if node.recovered:
            sections[node.id] = None
            owners[node.id] = node.id
            continue
        section = (node.id if node.kind in ('section_header_candidate', 'section_scalar_candidate')
                   else sections.get(node.section, sections.get(node.parent)))
        sections[node.id] = section
        owners[node.id] = section if section is not None else owners.get(node.parent, node.id)
    return owners


def silhouette(rows):
    """Trace both stepped edges; no enclosing bounding-box substitution."""
    if not rows:
        return QPainterPath()
    points = []
    for row in rows:
        points.extend((QPointF(row.right, row.top), QPointF(row.right, row.top + row.height)))
    for row in reversed(rows):
        points.extend((QPointF(row.left, row.top + row.height), QPointF(row.left, row.top)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    return path


class _MapSpinner(QWidget):
    """Tiny transparent overlay composited over the retained map frame."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('mapPendingSpinner')
        self.setFixedSize(20, 20)
        self.move(4, 4)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Let Qt restore the parent pixels between frames. Opaque/no-background
        # attributes would either hide the map or leave trails behind the arc.
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName('Map update in progress')
        self.hide()

    def paintEvent(self, event):  # noqa: N802
        view = self.parentWidget()
        paint_pending_spinner(self, view.editor, view._spinner_phase)


class DocumentMap(QWidget):
    # Qt's QString conversion strips a leading BOM. Keep exact source in Python.
    moveRequested = Signal(object, object)
    objectSelected = Signal(object, object)

    def __init__(self, editor, *, enabled=True, mode='heuristic'):
        super().__init__()
        self.analysis_enabled = enabled
        self.edit_mode = False
        self.selected_owner = None
        self._edit_owners = {}
        self._edit_relations = ()
        self._edit_regions = ()
        self._edit_semantics = None
        self._move_model = None
        self._selection_restore = None
        self._committing_move = False
        self._navigation_owner = None
        self._drag_press = None
        self._drag_point = None
        self._drag_active = False
        self._drag_block = None
        self._drag_plan = None
        self._drag_destination = None
        self._drag_plans = {}
        self._drag_index = None
        self._drag_grab_fraction = 0.5
        self._drag_scroll = QTimer(self)
        self._drag_scroll.setInterval(40)
        self._drag_scroll.timeout.connect(self._scroll_drag)
        self.editor = editor
        mode = normalize_graph_mode(mode)
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError('Expected a supported inference mode.')
        self.mode = mode
        self.setObjectName('documentMap')
        self._tooltip = MapTooltip(self)
        self.setAccessibleName('Infer Map')
        self.setMinimumWidth(48)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rows = ()
        self.shapes = ()
        self.path = QPainterPath()
        self.extent = QRectF(0, 0, 1, 1)
        self.block_tops = ()
        self.scale = 1.0
        self._fit = True
        self._document = None
        self._tree = None
        self.heat = None
        self.error = None
        self._heat_ready = False
        self._heat_range = (0, 0)
        self._block_summaries = {}
        self._document_influence = 0.0
        self._geometry_ready = False
        # Current evidence and retained pixels have separate lifetimes. A text
        # edit invalidates the former immediately without erasing the latter.
        self._pending = True
        self._retaining_display = False
        self._display_heat = None
        self._edit_palette = None
        self._display_colors = {}
        self._display_segments = {}
        self._source_index = None
        self._position_colors = {}
        self._position_events = ()
        self._position_event_objects = {}
        self._position_context_starts = ()
        self._position_context_objects = ()
        self._position_named_nodes = frozenset()
        self._position_cache = OrderedDict()
        self._position_cache_cells = 0
        self._position_frame = QImage()
        self._position_frame_key = None
        self._position_edit_frame = QImage()
        self._position_edit_frame_key = None
        self._position_commands = OrderedDict()
        self._position_command_bytes = 0
        self._row_tops = ()
        self._row_starts = ()
        self._display_viewport = QRectF()
        self._model_revision = None
        self._source_revision = 0
        self._requested_revision = None
        self.rebuild_count = 0
        self._geometry_cache = OrderedDict()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self.rebuild)
        self._spinner_phase = 0
        self._spinner = _MapSpinner(self)
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._advance_spinner)
        self._update_help()
        editor.document().contentsChange.connect(self._source_changed)
        editor.updateRequest.connect(lambda *_: self.update())
        editor.colorSchemeChanged.connect(self.update)
        editor.colorSchemeChanged.connect(self._spinner.update)
        editor.horizontalScrollBar().valueChanged.connect(self.update)
        editor.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        editor.viewport().installEventFilter(self)
        editor.installEventFilter(self)
        self.schedule_rebuild()

    def _update_help(self):
        self.setToolTip(self.mode_help)
        description = (EDIT_HELP if self.edit_mode else MAP_ACCESSIBLE_HELP if self.mode == 'heuristic' else self.mode_help +
                       '\n\nSpeculative, uncalibrated source-coverage proxy. '
                       'Not a probability or measured attention. '
                       'Wheel zooms line heights from fit to 1:1; drag divider to scale widths.')
        if self.status_text:
            description += '\n\n' + self.status_text + '. Block details are unavailable.'
        self.setAccessibleDescription(description)
        self._sync_spinner()

    def _sync_spinner(self):
        running = (self.analysis_enabled and not self.edit_mode and self._pending and not self.error
                   and self.isVisible())
        if running:
            self._spinner.show()
            self._spinner.raise_()
            if not self._spinner_timer.isActive():
                self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
            self._spinner.hide()

    def _advance_spinner(self):
        if not (self.analysis_enabled and not self.edit_mode and self._pending and not self.error and self.isVisible()):
            self._sync_spinner()
            return
        self._spinner_phase = (self._spinner_phase + 30) % 360
        # Only this 20×20 child is dirty. Qt composites the parent underneath
        # within that region, without rebuilding or relaying out map geometry.
        self._spinner.update()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._sync_spinner()

    def hideEvent(self, event):  # noqa: N802
        self._clear_edit_selection()
        self._spinner_timer.stop()
        self._spinner.hide()
        super().hideEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self.cancel_drag()
        self._spinner_timer.stop()
        self._spinner.hide()
        super().closeEvent(event)

    @property
    def stale(self):
        return self._pending and self._retaining_display

    @property
    def status_text(self):
        if self.edit_mode or not self.analysis_enabled or not self._pending:
            return ''
        status = 'Unavailable' if self.error else 'Pending'
        return status + (' · stale' if self.stale else '')

    def _source_changed(self, position, removed, added):
        # Syntax-format changes have no source delta. Invalidating on those
        # notifications would discard a just-published matching map.
        if removed or added:
            if not self._committing_move:
                self._selection_restore = None
            self._source_revision += 1
            self.invalidate()

    def invalidate(self, revision=None):
        """Retain the last frame, but make its source evidence unusable."""
        if not self.analysis_enabled:
            return
        self._clear_edit_selection(clear_model=True)
        self._timer.stop()
        self._requested_revision = revision
        self._model_revision = None
        self._retaining_display = self._geometry_ready
        self._pending = True
        self._document = self._tree = self.heat = None
        self._display_heat = None
        self._edit_palette = None
        self._position_named_nodes = frozenset()
        self.error = None
        self._heat_ready = False
        self._heat_range = (0, 0)
        self._document_influence = 0.0
        self._tooltip.hide()
        self._update_help()
        self.update()

    @property
    def mode_help(self):
        if self.edit_mode:
            return EDIT_HELP
        if self.mode == 'heuristic':
            return MAP_HELP
        rendering = ('Every whole block has one mean ST2 component color.\n'
                     'Source node/object components are equally weighted once each.\n'
                     'Wrapping and pixel area do not change the mean; extremes are hidden.\n'
                     if self.mode == 'semantic_triad_1' else
                     'Actual source spans show their element’s inherited final baseline B.\n'
                     'References show their resolved target; other text keeps its body context.\n'
                     'AS colors only its alias name; expression words keep their body context.\n'
                     'Named bodies, plain sections and nested structural bodies have baselines.\n'
                     'Source geometry, including whitespace, determines placement only.\n')
        text = (f'Infer Map · {MODE_LABELS[self.mode]}\n\n' + MODE_HELP[self.mode] +
                '\n\nEach source character has weight 1 / document length N.\n'
                'Own source and reachable utilized support are united, not added twice.\n'
                + rendering +
                'Hover shows compact context and support, or the ST1 block summary.\n'
                'All occurrences use one final value per element at document end.\n\n'
                'Speculative structural proxy; not a probability or measured model attention.\n\n'
                '- Blue is zero locality-adjusted inherited support\n'
                '- Red is the document-wide maximum inherited support\n'
                'One document-wide color scale covers all final element values.\n'
                + ('Source span widths are geometry, not object weights.'
                   if self.mode == 'semantic_triad_2' else
                   'Block means weight each source-defined component once.'))
        return '\n'.join(fill(line, width=80) for line in text.splitlines())

    def set_mode(self, mode):
        mode = normalize_graph_mode(mode)
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError('Expected a supported inference mode.')
        if self.mode == mode:
            return
        self._clear_edit_selection()
        self._selection_restore = None
        self.mode = mode
        # A different scoring model must not inherit the old model's palette.
        self._edit_palette = None
        self._display_heat = None
        self._display_colors.clear()
        self._display_segments.clear()
        self._clear_position_display()
        self._pending = True
        self._retaining_display = self._geometry_ready
        self.heat = None
        self.error = None
        self._heat_ready = False
        self._heat_range = (0, 0)
        self._document_influence = 0.0
        self._update_help()
        self._tooltip.hide()
        self.update()

    def set_edit_mode(self, enabled):
        if self.edit_mode == enabled:
            return
        self.edit_mode = enabled
        self._selection_restore = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus)
        self._clear_edit_selection(clear_model=True)
        self.setAccessibleName('Infer Edit' if enabled else 'Infer Map')
        # Pause scoring in the controller, not the already matching display.
        # ST2 still needs its detached result to lay out exact spans on resize.
        self.error = None
        self._tooltip.hide()
        self._update_help()
        self.schedule_rebuild()
        self.update()

    def set_analysis_enabled(self, enabled):
        if self.analysis_enabled == enabled:
            return
        self.analysis_enabled = enabled
        if not enabled:
            self._selection_restore = None
            self._clear_edit_selection(clear_model=True)
            self._timer.stop()
            self._document = self._tree = self.heat = None
            self._display_heat = None
            self._edit_palette = None
            self.error = None
            self._heat_ready = False
            self._geometry_ready = False
            self.rows = self.shapes = self.block_tops = ()
            self.path = QPainterPath()
            self._geometry_cache.clear()
            self._display_colors.clear()
            self._display_segments.clear()
            self._clear_position_display()
            self._display_viewport = QRectF()
            self._retaining_display = False
            self._pending = True
            self._model_revision = self._requested_revision = None
            self._tooltip.hide()
            self._update_help()
        else:
            self.schedule_rebuild()
        self._sync_spinner()

    def set_model(self, document, tree=None, *, heat=None, revision=None, semantics=None, colors=None):
        if not self.analysis_enabled:
            return
        if document is None:
            self.invalidate(revision)
            return
        if (revision is not None and self._requested_revision is not None
                and revision != self._requested_revision):
            return
        palette = colors or self._edit_palette
        if heat is not None and not self.edit_mode:
            palette = None
        self._edit_palette = (palette if palette is not None and palette.mode == self.mode
                              and palette.source == document.source else None)
        retained_heat = (self.heat if self.edit_mode and self._document is document
                         and self._model_revision == self._source_revision else None)
        if (self.edit_mode and retained_heat is None and self._display_heat is not None
                and self._display_heat[0] is document
                and self._display_heat[1] == self._source_revision):
            # A quick Edit → Map → Edit round trip can cancel the replacement
            # scorer before it publishes. The same displayed snapshot survives.
            retained_heat = self._display_heat[2]
        self._clear_edit_selection(clear_model=True)
        self._heat_ready = False
        self.error = None
        self._pending = True
        self._retaining_display = self._geometry_ready
        self._document = document
        self._tree = tree if tree is not None else parse(document)
        self._model_revision = self._source_revision
        if self.edit_mode and semantics is not None:
            snapshot = build_graph_snapshot(self._tree, semantics)
            self._edit_owners = dict(snapshot.owners)
            self._edit_relations = tuple(sorted(set(snapshot.occurrences)))
            self._edit_semantics = semantics
            if self._selection_restore and self._selection_restore[0] == document.source:
                start = self._selection_restore[1]
                node = next((node for node in self._tree.nodes if node.span.start == start), None)
                if node is not None:
                    self.selected_owner = self._edit_owners.get(node.id, node.id)
        # Numeric evidence belongs only to this exact snapshot. Validated moves
        # carry separate paint colors by exact source spans, never stale IDs.
        self.heat = retained_heat if self.edit_mode else heat
        self._refresh_heat_scale()
        self._refresh_block_summaries()
        self._tooltip.hide()
        self._update_help()
        self.update()
        # The first load may show neutral geometry. Once a frame exists, only
        # the complete matching result can replace it; no neutral flash on edits.
        self.schedule_rebuild()

    def set_error(self, message):
        """A failed replacement keeps the previous frame explicitly stale."""
        self._clear_edit_selection(clear_model=True)
        self.error = message
        self.heat = None
        self._heat_ready = False
        self._pending = True
        self._retaining_display = self._geometry_ready
        self._timer.stop()
        self._tooltip.hide()
        self._update_help()
        self.update()

    def color_for_owner(self, owner):
        # This accessor describes displayed pixels, never current evidence.
        if self._owner_selected(owner):
            return QColor(*EDIT_SELECTED_COLOR)
        return QColor(*self._display_colors.get(owner, PENDING_COLOR))

    def _owner_selected(self, owner):
        return (self.edit_mode and self.selected_owner is not None
                and self._edit_owners.get(owner, owner) == self.selected_owner)

    def _refresh_heat_scale(self):
        if self.mode != 'heuristic':
            values = self.heat.final_values.values() if self.heat else ()
            # One shared document-wide numeric scale makes different identities
            # comparable. A weak object's maximum must not become red by itself.
            self._heat_range = (0.0, max(values, default=0.0))
            self._document_influence = 0.0
        else:
            scores = [score.total for score in self.heat.scores.values()] if self.heat else []
            self._heat_range = (min(scores, default=0), max(scores, default=0))
            self._document_influence = sum(scores)

    def _refresh_block_summaries(self):
        """Mean source-defined components once, never visual rows or pixels."""
        self._block_summaries = {}
        if self.mode in ('heuristic', 'semantic_triad_2') or self.heat is None or self._tree is None:
            return
        maximum = self._heat_range[1]
        components = {}
        for node in self._tree.nodes:
            if not any(token.text.strip() for token in node.tokens):
                continue
            view = self.heat.views.get(node.id)
            if view is None or not view.objects:
                continue
            owner = self.heat.owners.get(node.id)
            if owner is None:
                continue
            values = {detail.object: detail.adjusted_linked
                      for detail in self.heat.view_details.get(node.id, ())}
            components.setdefault(owner, []).extend(
                max(0.0, min(1.0, values.get(name, 0.0) / maximum)) if maximum > 0 else 0.0
                for name in view.objects)
        self._block_summaries = {
            owner: BlockColorSummary(len(values), math.fsum(values) / len(values))
            for owner, values in components.items()}

    def _refresh_colors(self):
        if self.mode == 'semantic_triad_2':
            self._display_segments = {}
            self._display_colors = {row.owner: heat_rgb(0, *self._heat_range) for row in self.rows}
            self._prepare_position_display()
        elif self.mode != 'heuristic':
            segments = {}
            for node in self.heat.views:
                summary = self._block_summaries.get(self.heat.owners.get(node))
                intensity = summary.mean_intensity if summary else 0.0
                segments[node] = ((None, heat_rgb(intensity, 0.0, 1.0)),)
            self._display_segments = segments
            self._display_colors = {node: values[0][1] for node, values in segments.items()}
        else:
            self._display_segments = {}
            self._display_colors = {
                owner: heat_rgb(self.heat.scores[block].total, *self._heat_range)
                if block in self.heat.scores else heat_rgb(0, *self._heat_range)
                for owner, block in self.heat.owners.items()}
        self._display_colors[None] = heat_rgb(0, *self._heat_range)

    def freeze_colors(self):
        """Snapshot the current base palette, excluding orange selection paint."""
        if self._edit_palette is not None:
            return self._edit_palette
        if not self._heat_ready or self._document is None:
            return None
        positions = ()
        if self.mode == 'semantic_triad_2':
            boundaries = sorted({0, len(self._document.source), *self._position_events,
                                 *self._position_context_starts})
            positions = tuple((start, end, self._objects_at_position(start, event=False))
                              for start, end in zip(boundaries, boundaries[1:]))
        unowned = self._display_colors[None]
        return MapColors(self._document.source, self.mode,
                         tuple((node.span, self._display_colors.get(node.id, unowned))
                               for node in self._tree.nodes), unowned, positions,
                         tuple(self._position_colors.items()))

    def _restore_colors(self):
        """Rebind saved paint to current nodes and source geometry, without scoring."""
        palette = self._edit_palette
        by_span = dict(palette.nodes)
        self._display_colors = {node.id: by_span[node.span] for node in self._tree.nodes}
        self._display_colors[None] = palette.unowned
        self._display_segments = ({node: ((None, color),) for node, color in self._display_colors.items()}
                                  if self.mode == 'semantic_triad_1' else {})
        self._clear_position_display()
        if self.mode == 'semantic_triad_2':
            self._source_index = SourcePositionIndex(self._document.source)
            self._position_context_starts = tuple(start for start, _, _ in palette.positions)
            self._position_context_objects = tuple(names for _, _, names in palette.positions)
            self._position_colors = dict(palette.colors)

    @property
    def _position_display_ready(self):
        return (self._source_index is not None
                and (self._heat_ready or (self.edit_mode and self._edit_palette is not None)))

    def row_segments(self, row):
        """Source-aligned spans or whole-block fills; retained frames need no evidence."""
        if self._owner_selected(row.owner):
            return ((None, QRectF(row.left, row.top, row.right - row.left, row.height), self.color_for_owner(row.owner).getRgb()[:3]),)
        if self.mode == 'semantic_triad_2' and self._position_display_ready:
            return tuple((item.object, item.rect, item.color) for item in self.position_segments(row))
        segments = self._display_segments.get(row.owner)
        if not segments:
            segments = ((None, self._display_colors.get(row.owner, PENDING_COLOR)),)
        width = (row.right - row.left) / len(segments)
        return tuple((name, QRectF(row.left + index * width, row.top, width, row.height), color)
                     for index, (name, color) in enumerate(segments))

    def _clear_position_display(self):
        self._source_index = None
        self._position_colors = {}
        self._position_events = ()
        self._position_event_objects = {}
        self._position_context_starts = ()
        self._position_context_objects = ()
        self._position_named_nodes = frozenset()
        self._position_cache.clear()
        self._position_cache_cells = 0
        self._position_frame = QImage()
        self._position_frame_key = None
        self._position_edit_frame = QImage()
        self._position_edit_frame_key = None
        self._position_commands = OrderedDict()
        self._position_command_bytes = 0

    def _prepare_position_display(self):
        """Prepare source geometry/associations; final values are already cached."""
        self._clear_position_display()
        self._source_index = SourcePositionIndex(self._document.source)
        snapshot = self.heat.position_snapshot
        if snapshot is None:
            return
        # The causal evaluator intentionally contains named objects only. Map
        # baselines also include plain structural elements and are already final.
        canonical = self.heat.final_values
        self._position_colors = {name: heat_rgb(value, *self._heat_range)
                                 for name, value in canonical.items()}
        order = {name: index for index, name in enumerate(canonical)}
        events = {}
        for event in snapshot.semantic_positions:
            events.setdefault(event.position, set()).update(
                name for name in event.objects if name in order)
        # Preserve syntax boundaries geometrically. Within a body, punctuation
        # and ordinary prose retain that element's inherited baseline.
        for node in self._tree.nodes:
            for token in node.tokens:
                if token.kind not in ('text', 'whitespace', 'newline', 'symbol'):
                    events.setdefault(token.span.start, set())
                    events.setdefault(token.span.end, set())
        self._position_events = tuple(sorted(events))
        self._position_event_objects = {
            position: tuple(sorted(names, key=order.__getitem__))
            for position, names in events.items()}

        # Retain the named-ancestry marker for callers that inspect geometry;
        # display ownership itself comes from the element interval sweep below.
        nodes = self._tree.nodes
        bodies = {event.node for event in snapshot.semantic_positions
                  if event.kind == 'object_start' and event.node is not None
                  and nodes[event.node].symbol_body_span is not None
                  and event.position == nodes[event.node].span.start}
        named = set()
        for node in nodes:
            if (node.id in bodies
                    or node.parent in named or node.section in named):
                named.add(node.id)
        self._position_named_nodes = frozenset(named)

        # AS evidence covers a whole expression, but its display ownership is
        # only the alias token. Reconstruct genuine named bodies separately so
        # an alias later used as a body header still owns that complete body.
        # The detached events supply resolved identities; no re-resolution or
        # scoring occurs while preparing or painting this geometry.
        alias_tokens, body_starts, body_ends = {}, {}, {}
        for event in snapshot.semantic_positions:
            if event.node is None:
                continue
            node = nodes[event.node]
            for name in event.objects:
                if name not in order:
                    continue
                key = (event.node, name)
                if (event.kind == 'alias_use' and node.alias_target_span is not None
                        and event.position == node.alias_target_span.end):
                    span = node.alias_target_span
                    alias_tokens.setdefault(name, []).append((span.start, span.end))
                elif (event.kind == 'object_start' and node.symbol_body_span is not None
                      and event.position == node.span.start):
                    body_starts[key] = event.position
                elif event.kind == 'object_end':
                    body_ends[key] = max(body_ends.get(key, 0), event.position)
        display_definitions = {name: list(spans) for name, spans in alias_tokens.items()}
        for key, start in body_starts.items():
            if key[1] in display_definitions and body_ends.get(key, start) > start:
                display_definitions[key[1]].append((start, body_ends[key]))

        # Sweep local display spans, never the transitive support they inherit.
        # References override the containing baseline only on their exact spans;
        # otherwise the smallest enclosing body supplies its own context.
        changes, records = {}, []
        elements = getattr(snapshot, 'semantic_elements', ()) or snapshot.semantic_footprints
        for footprint in elements:
            if footprint.object not in order:
                continue
            for kind, spans in (('definition', display_definitions.get(
                                    footprint.object, footprint.definitions)),
                                ('mention', footprint.mentions)):
                for start, end in spans:
                    if start == end:
                        continue
                    number = len(records)
                    records.append((kind, footprint.object, start, end))
                    changes.setdefault(start, []).append((True, number))
                    changes.setdefault(end, []).append((False, number))
        active, references, definitions = set(), {}, []
        starts, contexts = [], []
        for position in sorted({0, *changes}):
            for entering, number in changes.get(position, ()):
                kind, name, start, end = records[number]
                if entering:
                    active.add(number)
                    if kind == 'mention':
                        references[number] = name
                    else:
                        heapq.heappush(definitions, (end - start, -start, order[name], number, name))
                else:
                    active.discard(number)
                    references.pop(number, None)
            while definitions and definitions[0][3] not in active:
                heapq.heappop(definitions)
            if references:
                names = tuple(sorted(set(references.values()), key=order.__getitem__))
            elif definitions:
                names = (definitions[0][4],)
            else:
                names = ()
            if not contexts or names != contexts[-1]:
                starts.append(position)
                contexts.append(names)
        self._position_context_starts = tuple(starts)
        self._position_context_objects = tuple(contexts)

    def _objects_at_position(self, position, *, event=True):
        if event and position in self._position_event_objects:
            return self._position_event_objects[position]
        index = bisect_right(self._position_context_starts, position) - 1
        return self._position_context_objects[index] if index >= 0 else ()

    def _position_line(self, row):
        block = self.editor.document().findBlock(row.start)
        # Repeated-text geometry can come from our cache while Qt has never
        # laid out this offscreen block. Cursor queries require a real line.
        if not block.layout().lineCount():
            self.editor.blockBoundingRect(block)
        return block, block.layout().lineForTextPosition(row.start - block.position())

    def _position_intervals(self, row):
        """Split at semantic events/context changes, never at display samples."""
        block, line = self._position_line(row)
        first = self._source_index.source(row.start)
        last = self._source_index.source(row.end)
        boundaries = {first, last}
        for points in (self._position_events, self._position_context_starts):
            boundaries.update(points[bisect_right(points, first):bisect_left(points, last)])
        boundaries = sorted(boundaries)
        result = []
        for start, end in zip(boundaries, boundaries[1:]):
            left = max(row.left, min(row.right, line.cursorToX(
                self._source_index.display(start) - block.position())[0]))
            right = (row.right if end == last else max(row.left, min(row.right, line.cursorToX(
                self._source_index.display(end) - block.position())[0])))
            if right <= left:
                continue
            # Indentation is outside the silhouette and must not be expanded
            # into a visible object segment.
            offset = line.xToCursor(left, QTextLine.CursorPosition.CursorBetweenCharacters)
            start = max(start, self._source_index.source(block.position() + offset))
            names = self._objects_at_position(start, event=False)
            result.append(PositionInterval(start, end, left, right, names))
        return tuple(result)

    def _interval_position(self, row, interval, fraction, geometry=None):
        """Source hit testing uses Qt's shaped source cursor geometry."""
        if fraction <= 1e-10:
            return interval.start
        if fraction >= 1 - 1e-10:
            return interval.end
        block, line = geometry or self._position_line(row)
        x = interval.left + fraction * (interval.right - interval.left)
        offset = line.xToCursor(x, QTextLine.CursorPosition.CursorBetweenCharacters)
        return max(interval.start, min(interval.end,
                   self._source_index.source(block.position() + offset)))

    def _position_hit(self, position):
        """Return exact source boundary, identity and source interval under x."""
        if (self.mode != 'semantic_triad_2' or not self._position_display_ready
                or self._source_index is None or not self.rows):
            return None
        origin = self.map_origin()
        point = QPointF((position.x() - origin.x()) / self.horizontal_scale,
                        (position.y() - origin.y()) / self.scale)
        index = bisect_right(self._row_tops, point.y()) - 1
        if index < 0:
            return None
        row = self.rows[index]
        if (point.y() >= row.top + row.height
                or not row.left <= point.x() <= row.right):
            return None
        intervals = self._position_intervals(row)
        for number, interval in enumerate(intervals):
            if point.x() < interval.right - 1e-9 or number == len(intervals) - 1:
                fraction = min(1., max(0., (point.x() - interval.left)
                                           / (interval.right - interval.left)))
                name = interval.objects[0] if interval.objects else None
                return self._interval_position(row, interval, fraction), name, interval
        return None

    def source_position_at(self, position):
        """Exact source boundary from uncompressed source geometry."""
        hit = self._position_hit(position)
        return hit[0] if hit else None

    def _positional_tooltip(self, position):
        hit = self._position_hit(position)
        if hit is None:
            return self.mode_help
        point, name, _interval = hit
        location = self._document.position(point)
        return (f'Infer Map · {MODE_LABELS[self.mode]}\n\n'
                f'Line {location.line}, column {location.column} · source {point}\n'
                + self._semantic_breakdown(None, position=point,
                                           objects=(name,) if name is not None else ()))

    def position_segments(self, row):
        """Actual source spans, colored from cached complete-document values."""
        if not self._position_display_ready:
            return ()
        dpr = self.devicePixelRatioF()
        xscale, yscale = self.horizontal_scale * dpr, self.scale * dpr
        key = (row.start, row.end, xscale, yscale)
        cached = self._position_cache.get(key)
        if cached is not None:
            self._position_cache.move_to_end(key)
            return cached
        result = []
        for interval in self._position_intervals(row):
            name = interval.objects[0] if interval.objects else None
            result.append(PositionSegment(interval.start, name,
                          QRectF(interval.left, row.top, interval.right - interval.left, row.height),
                          self._position_colors[name] if name is not None else UNOWNED_COLOR))
        segments = tuple(result)
        if len(segments) <= 16384:
            while self._position_cache and (len(self._position_cache) >= 128
                    or self._position_cache_cells + len(segments) > 16384):
                _, expired = self._position_cache.popitem(last=False)
                self._position_cache_cells -= len(expired)
            self._position_cache[key] = segments
            self._position_cache_cells += len(segments)
        return segments

    def _paint_positional_frame(self, *, edit=False):
        """Reuse content pixels independently of the moving viewport overlay.

        A fitted map has the same transform throughout editor scrolling. Its
        bounded row cache cannot retain an entire large document, so repainting
        those rows would repeatedly evict and rebuild their source-span commands.
        Keep a viewport-sized base raster instead; only a changed transform or
        freshly prepared source geometry/evidence requires sampling again.
        """
        dpr = self.devicePixelRatioF()
        origin = self.map_origin()
        key = (self.width(), self.height(), dpr, self.horizontal_scale, self.scale,
               origin.x(), origin.y())
        if edit:
            key = (key, self.selected_owner, self._drag_active)
            if key == self._position_edit_frame_key and not self._position_edit_frame.isNull():
                return
            # A single bounded edit raster leaves the retained base untouched.
            # Reuse its exact winning compressed rows and physical-pixel edges:
            # a fractional vector overlay can miss/steal a boundary pixel.
            frame = self._position_frame.copy()
            frame.setDevicePixelRatio(1.0)
        else:
            if key == self._position_frame_key and not self._position_frame.isNull():
                return
            frame = QImage(max(1, math.ceil(self.width() * dpr)),
                           max(1, math.ceil(self.height() * dpr)), QImage.Format.Format_ARGB32_Premultiplied)
            frame.fill(Qt.GlobalColor.transparent)
        # Paint integer physical rectangles. Independently transformed fractional
        # fillRect heights can round differently at an otherwise shared edge.
        # Set the image DPR only after painting, to avoid a second transform.
        painter = QPainter(frame)
        xscale, yscale = self.horizontal_scale * dpr, self.scale * dpr
        xorigin, yorigin = origin.x() * dpr, origin.y() * dpr
        first = max(0, bisect_right(self._row_tops, -origin.y() / self.scale) - 1)
        bottom = (self.height() - origin.y()) / self.scale
        visible_rows = []
        # Do not copy the remaining document on each zoomed scroll.
        for index in range(first, len(self.rows)):
            row = self.rows[index]
            if row.top >= bottom:
                break
            pixel = math.floor((origin.y() + row.top * self.scale) * dpr)
            if (visible_rows and row.height * self.scale * dpr < 1
                    and pixel == visible_rows[-1][0]):
                visible_rows[-1] = (pixel, row)
            else:
                visible_rows.append((pixel, row))
        colors = {}
        for pixel, row in visible_rows:
            if edit:
                dragged = self._shape_dragged(row.owner)
                if not dragged and not self._owner_selected(row.owner):
                    continue
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear if dragged
                                           else QPainter.CompositionMode.CompositionMode_SourceOver)
            commands = self._position_commands_for_row(row, dpr)
            xedges, yedges = {}, {}

            def edge(value, scale, offset, edges):
                result = edges.get(value)
                if result is None:
                    mapped = value * scale + offset
                    # Equivalent shared endpoints can differ by a few ULPs
                    # (top + height versus the next top), especially after a
                    # large scrolled document offset cancels against origin.
                    # Resolve only that arithmetic uncertainty toward +infinity
                    # at half pixels; do not enlarge every rectangle.
                    tolerance = 4 * (math.ulp(value) * abs(scale)
                                     + math.ulp(value * scale) + math.ulp(offset))
                    result = edges[value] = math.floor(mapped + .5 + tolerance)
                return result

            for left, top, width, height, red, green, blue in struct.iter_unpack('=ddddBBB', commands):
                x0 = edge(left, xscale, xorigin, xedges)
                x1 = edge(left + width, xscale, xorigin, xedges)
                if row.height * yscale < 1:
                    # Preserve the one-physical-pixel compressed-row silhouette.
                    y0, y1 = pixel, pixel + 1
                else:
                    y0 = edge(top, yscale, yorigin, yedges)
                    y1 = edge(top + height, yscale, yorigin, yedges)
                rgb = EDIT_SELECTED_COLOR if edit else (red, green, blue)
                color = colors.get(rgb)
                if color is None:
                    color = colors[rgb] = QColor(*rgb)
                painter.fillRect(QRect(x0, y0, x1 - x0, y1 - y0), color)
        painter.end()
        frame.setDevicePixelRatio(dpr)
        if edit:
            self._position_edit_frame = frame
            self._position_edit_frame_key = key
        else:
            self._position_frame = frame
            self._position_frame_key = key

    def _position_commands_for_row(self, row, dpr):
        """Bounded exact paint commands survive scrolling beyond the cell LRU.

        Pack original double-precision rectangles and RGB bytes, not semantic
        vectors or quantized geometry. Snap shared edges only when replaying,
        using the current origin and physical-pixel transform.
        """
        key = (row.start, row.end, self.horizontal_scale * dpr, self.scale * dpr)
        commands = self._position_commands.get(key)
        if commands is not None:
            self._position_commands.move_to_end(key)
            return commands
        data = bytearray()
        for segment in self.position_segments(row):
            rect = segment.rect
            data.extend(struct.pack('=ddddBBB', rect.left(), rect.top(), rect.width(), rect.height(),
                                    *segment.color))
        commands = bytes(data)
        # Fixed display-only storage, independent of document length. Oversized
        # rows are rendered directly and are never retained in either cache.
        size = len(commands)
        if size <= POSITION_COMMAND_BYTE_LIMIT:
            while self._position_commands and (len(self._position_commands) >= POSITION_COMMAND_ROW_LIMIT
                    or self._position_command_bytes + size > POSITION_COMMAND_BYTE_LIMIT):
                _, expired = self._position_commands.popitem(last=False)
                self._position_command_bytes -= len(expired)
            self._position_commands[key] = commands
            self._position_command_bytes += size
        return commands

    def tooltip_at(self, position):
        if self.edit_mode:
            return EDIT_HELP
        if self.error:
            return f"{self.mode_help}\n\nInfluence calculation unavailable: {self.error}"
        if self.heat is None or not self._heat_ready:
            return self.mode_help
        if self.mode == 'semantic_triad_2':
            return self._positional_tooltip(position)
        origin = self.map_origin()
        point = QPointF((position.x() - origin.x()) / self.horizontal_scale,
                        (position.y() - origin.y()) / self.scale)
        owner = next((owner for owner, shape in self.shapes if shape.contains(point)), None)
        if self.mode != 'heuristic':
            view = self.heat.views.get(owner)
            if view is None:
                return self.mode_help
            node_id = self.heat.owners.get(owner, owner)
        else:
            node_id = self.heat.owners.get(owner)
            score = self.heat.scores.get(node_id)
            if score is None:
                return self.mode_help
        node = self._tree.nodes[node_id]
        label_span = node.symbol_body_span or node.span
        label = label_span.extract(self._document.source).strip().splitlines()[0]
        label = label[:100] + ('…' if len(label) > 100 else '')
        line = self._document.source_range(node.span).start.line
        if self.mode != 'heuristic':
            return (f'Infer Map · {MODE_LABELS[self.mode]}\n\n'
                    f'{label}, line {line}\n' + self._semantic_breakdown(owner))
        return (f'Infer Map - ({self._document_influence:.2f} total inf)\n\n'
                f'{label}, line {line}\n'
                f'Inheritances: {score.direct_count}x ({score.direct:.2f} inf)\n'
                f'Propagations: {score.indirect_count}x ({score.indirect:.2f} inf)')

    def _semantic_breakdown(self, node, *, position=None, objects=()):
        """Compact readout of the hovered context, matching the H tooltip."""
        view = self.heat.views.get(node) if self.heat else None
        if self.mode == 'semantic_triad_1' and view is not None:
            summary = self._block_summaries.get(self.heat.owners.get(node), BlockColorSummary(0, 0.0))
            return (f'Mean intensity: {summary.mean_intensity:.1%}\n'
                    f'Components: {summary.component_count}')
        if position is not None:
            details = self.heat.final_details if self.heat else ()
            names = objects
        elif view is not None:
            details = self.heat.view_details.get(node, ())
            names = view.objects
        else:
            return 'Current coverage details unavailable.'
        if not details or not names:
            return ('No attributed semantic object.' if position is not None
                    else 'No declared object support.')
        by_name = {detail.object: detail for detail in details}
        rows = []
        for name in names[:3]:
            label = ' '.join(self.heat.final_labels.get(name, name).split())
            label = label[:100] + ('…' if len(label) > 100 else '')
            heading = label if label.endswith(':') else f'{label}:'
            detail = by_name.get(name)
            if detail is None:
                rows.append(f'{heading} support unavailable')
                continue
            share = (f'{detail.adjusted_linked / detail.adjusted_comparison:.1%}'
                     if detail.adjusted_comparison > 0 else 'n/a')
            rows.append(f'{heading} baseline B {detail.adjusted_linked:.3g} · '
                        f'source {detail.adjusted_definition:.3g} · share {share}')
        if len(names) > 3:
            rows.append(f'+ {len(names) - 3} more elements')
        return '\n'.join(rows)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            if self._drag_press is not None:
                event.accept()
                return True
            if self._timer.isActive():
                self.rebuild()
            self._tooltip.show_text(self.tooltip_at(event.pos()), event.globalPos())
            event.accept()
            return True
        return super().event(event)

    def schedule_rebuild(self):
        # Do not restart: a stream of changes still gets bounded refreshes.
        if (self.analysis_enabled
                and (self.edit_mode or self.heat is not None or not self._retaining_display)
                and not self._timer.isActive()):
            self._timer.start()

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self._drag_press is not None:
            self.cancel_drag()
            return True
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.schedule_rebuild()
        elif event.type() == QEvent.Type.Resize:
            self.schedule_rebuild()
        return super().eventFilter(watched, event)

    def _geometry(self, block):
        text = block.text()
        formats = tuple((f.start, f.length, QTextCharFormat(f.format)) for f in block.layout().formats())
        key = (text, not block.next().isValid(), self.editor.font().key(),
               self.editor.viewport().width(), self.editor.document().documentMargin(),
               self.editor.tabStopDistance())
        cached = self._geometry_cache.get(key)
        if cached is not None and cached[0] == formats:
            self._geometry_cache.move_to_end(key)
            return cached[1]
        height = self.editor.blockBoundingRect(block).height()
        layout = block.layout()
        encoded = text.encode('utf-16-le')
        lines = []
        for number in range(layout.lineCount()):
            line = layout.lineAt(number)
            start = line.textStart()
            content = encoded[2 * start:2 * (start + line.textLength())].decode('utf-16-le')
            if not content.strip():
                continue
            indent = len(content) - len(content.lstrip())
            indent_utf16 = len(content[:indent].encode('utf-16-le')) // 2
            left = line.cursorToX(start + indent_utf16)[0]
            right = max(line.cursorToX(start + line.textLength())[0], line.naturalTextRect().right())
            lines.append((start, line.y(), line.height(), min(left, right), max(left + 1.0, right),
                          start + line.textLength()))
        result = (height, tuple(lines))
        # Single-line NoWrap blocks have the same Qt line-count without forcing
        # layout. Multiline blocks still need layout to update Qt's scroll model.
        if layout.lineCount() == 1:
            self._geometry_cache[key] = (formats, result)
            if len(self._geometry_cache) > 2048:
                self._geometry_cache.popitem(last=False)
        return result

    def rebuild(self):
        self._timer.stop()
        if (not self.analysis_enabled
                or (self._retaining_display and self._document is None)
                or (not self.edit_mode and self._retaining_display and self.heat is None)):
            return
        if self._document is not None and self._model_revision != self._source_revision:
            self.invalidate(self._requested_revision)
            return
        self.rebuild_count += 1
        starts, ends, owners = [], [], []
        if self._document is not None:
            nodes = self._tree.nodes
            boundaries = [p for n in nodes for p in (n.span.start, n.span.end)]
            if self.edit_mode or self.mode == 'semantic_triad_2':
                index = SourcePositionIndex(self._document.source)
                offsets = {position: index.display(position) for position in boundaries}
            else:
                offsets = display_offsets(self._document.source, boundaries)
            ownership = ({node.id: node.id for node in nodes} if self.mode != 'heuristic'
                         else section_owners(self._tree))
            # A supported symbolic list body can start a whole context without
            # starting a section. Split that paint partition at its real body.
            whole_owners = self._edit_owners if self.edit_mode else (self.heat.owners if self.heat else {})
            if whole_owners and self.mode == 'heuristic':
                for node in nodes:
                    whole = whole_owners[node.id]
                    if whole != whole_owners.get(ownership[node.id]):
                        ownership[node.id] = whole
            starts = [offsets[n.span.start] for n in nodes]
            ends = [offsets[n.span.end] for n in nodes]
            owners = [ownership[n.id] for n in nodes]
        rows, tops = [], []
        block = self.editor.document().begin()
        top = 0.0
        width = 1.0
        while block.isValid():
            tops.append(top)
            height, lines = self._geometry(block)
            for start, y, line_height, left, right, end in lines:
                position = block.position() + start
                index = bisect_right(starts, position) - 1
                owner = owners[index] if index >= 0 and position < ends[index] else None
                rows.append(MapRow(position, top + y, line_height, left, right, owner,
                                   block.position() + end))
                width = max(width, right)
            top += height
            block = block.next()
        self.rows = tuple(rows)
        self._row_tops = tuple(row.top for row in rows)
        self._row_starts = tuple(row.start for row in rows)
        self.block_tops = tuple(tops)
        self.extent = QRectF(0, 0, width, max(1.0, top))
        groups, current = [], []
        for row in rows:
            if current and (row.owner != current[-1].owner
                            or abs(row.top - current[-1].top - current[-1].height) > 0.1):
                groups.append(tuple(current))
                current = []
            current.append(row)
        if current:
            groups.append(tuple(current))
        self.shapes = tuple((group[0].owner, silhouette(group)) for group in groups)
        self._rebuild_edit_regions()
        self._heat_ready = self.heat is not None
        self._pending = not self.edit_mode and not self._heat_ready
        self._retaining_display = False
        self._geometry_ready = True
        if self._heat_ready:
            self._display_heat = (self._document, self._source_revision, self.heat)
            self._refresh_colors()
        elif self.edit_mode and self._edit_palette is not None:
            self._display_heat = None
            self._restore_colors()
        else:
            self._display_heat = None
            self._display_colors = {}
            self._display_segments = {}
            self._clear_position_display()
        self._update_help()
        self.path = QPainterPath()
        for _, shape in self.shapes:
            self.path.addPath(shape)
        self._clamp_scale()
        self.update()

    @property
    def minimum_scale(self):
        # Width never shrinks the document into a strip with empty space below.
        return min(1.0, max(1.0, self.height()) / self.extent.height())

    @property
    def horizontal_scale(self):
        # Normalize to the furthest-right silhouette point, not blank editor width.
        return self.width() / max(1.0, self.extent.width())

    def _clamp_scale(self):
        if not self.analysis_enabled or not self._geometry_ready:
            return
        self.scale = self.minimum_scale if self._fit else max(self.minimum_scale, min(1.0, self.scale))

    def viewport_rect(self):
        # Old block numbers must not be mapped onto a newly edited document.
        if self.stale:
            return QRectF(self._display_viewport)
        first = self.editor.firstVisibleBlock()
        number = first.blockNumber()
        if not 0 <= number < len(self.block_tops):
            return QRectF()
        screen = self.editor.blockBoundingGeometry(first).translated(self.editor.contentOffset())
        self._display_viewport = QRectF(
            -self.editor.contentOffset().x(), self.block_tops[number] - screen.top(),
            self.editor.viewport().width(), self.editor.viewport().height())
        return QRectF(self._display_viewport)

    def map_origin(self):
        visible = self.viewport_rect()
        if self.scale == 1.0:
            # Exact editor pixels, including its real top margin and blank rows.
            top = visible.top()
        else:
            h = max(1.0, self.height()) / self.scale
            top = max(0.0, min(max(0.0, self.extent.height() - h), visible.center().y() - h / 2))
        return QPointF(0, -top * self.scale)

    def mapped_viewport(self):
        rect = self.viewport_rect()
        origin = self.map_origin()
        return QRectF(0, origin.y() + rect.y() * self.scale,
                      self.width(), rect.height() * self.scale)

    def _clear_edit_selection(self, *, clear_model=False):
        self.cancel_drag()
        self.selected_owner = None
        if clear_model:
            self._edit_owners = {}
            self._edit_relations = ()
            self._edit_regions = ()
            self._edit_semantics = None
            self._move_model = None
        self.update()

    def _rebuild_edit_regions(self):
        """Split gaps halfway between whole objects, not their nested partitions."""
        self._edit_regions = ()
        if (not self.edit_mode or self._document is None
                or self._model_revision != self._source_revision):
            return
        groups = []
        for row in self.rows:
            owner = self._edit_owners.get(row.owner, row.owner)
            if groups and groups[-1][0] == owner:
                groups[-1][2] = row.top + row.height
            else:
                groups.append([owner, row.top, row.top + row.height])
        boundaries = [(previous[2] + following[1]) / 2
                      for previous, following in zip(groups, groups[1:])]
        self._edit_regions = tuple(
            EditRegion(owner, boundaries[index - 1] if index else top,
                       boundaries[index] if index < len(boundaries) else bottom)
            for index, (owner, top, bottom) in enumerate(groups))

    def edit_owner_at(self, point):
        """Use the same bands as the dividers; a shared boundary belongs below."""
        if (not self.edit_mode or self._document is None
                or self._model_revision != self._source_revision
                or not 0 <= point.x() < self.width()):
            return None
        origin = self.map_origin().y()
        return next((region.owner for region in self._edit_regions
                     if origin + region.top * self.scale <= point.y()
                     < origin + region.bottom * self.scale), None)

    def _paint_edit_dividers(self, painter):
        if not self.edit_mode:
            return
        origin = self.map_origin()
        painter.save()
        painter.setPen(QPen(QColor(*EDIT_SELECTED_COLOR), 1, Qt.PenStyle.DotLine))
        for region in self._edit_regions[1:]:
            y = origin.y() + region.top * self.scale
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        painter.restore()

    def _navigate_owner(self, owner):
        if (owner is not None and self._document is not None
                and self._model_revision == self._source_revision):
            self.objectSelected.emit(self._document, self._tree.nodes[owner].span)

    def owner_at(self, position):
        """Select the current painted object, never retained or blank pixels."""
        if (self._document is None or not self._heat_ready or self._pending
                or self._model_revision != self._source_revision):
            return None
        origin = self.map_origin()
        point = QPointF((position.x() - origin.x()) / self.horizontal_scale,
                        (position.y() - origin.y()) / self.scale)
        owner = next((owner for owner, shape in self.shapes if shape.contains(point)), None)
        return self.heat.owners.get(owner, owner) if owner is not None else None

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._timer.isActive():
            self.rebuild()
        if not self.edit_mode:
            self._navigate_owner(self.owner_at(event.position()))
            self._tooltip.hide()
            event.accept()
            return
        # Retained pixels are not selectable evidence after an edit.
        self.cancel_drag()
        self._selection_restore = None
        self.selected_owner = self.edit_owner_at(event.position())
        self._navigation_owner = self.selected_owner
        if self.selected_owner is not None and self._edit_semantics is not None:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if self._move_model is None:
                self._move_model = BlockMoveModel(self._document, self._tree, self._edit_semantics, self._edit_owners)
            self._drag_block = self._move_model.blocks.get(self.selected_owner)
            if self._drag_block is not None:
                self._drag_index = SourcePositionIndex(self._document.source)
                self._drag_press = QPointF(event.position())
                self._drag_point = QPointF(event.position())
                rect = self._drag_source_rect()
                if rect.height() > 0:
                    self._drag_grab_fraction = (event.position().y() - rect.top()) / rect.height()
        self._tooltip.hide()
        self.update()
        event.accept()

    def cancel_drag(self):
        """Discard only the preview; no editor operation or undo entry occurs."""
        self._drag_scroll.stop()
        self._navigation_owner = None
        self._drag_press = self._drag_point = None
        self._drag_block = self._drag_plan = self._drag_destination = None
        self._drag_active = False
        self._drag_plans = {}
        self._drag_index = None
        self._tooltip.hide()
        self.update()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._drag_press is not None:
            self.cancel_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):  # noqa: N802
        self.cancel_drag()
        super().focusOutEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_press is None:
            super().mouseMoveEvent(event)
            return
        self._drag_point = QPointF(event.position())
        if not self._drag_active:
            # Vertical movement alone starts a vertical block move.
            if abs(self._drag_point.y() - self._drag_press.y()) < QApplication.startDragDistance():
                event.accept()
                return
            self._drag_active = True
            self._drag_scroll.start()
        self._update_drag_target()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if (event.button() != Qt.MouseButton.LeftButton
                or (self._drag_press is None and self._navigation_owner is None)):
            super().mouseReleaseEvent(event)
            return
        if self._drag_active:
            self._drag_point = QPointF(event.position())
            self._update_drag_target()
        plan = self._drag_plan if self._drag_active and self.rect().contains(event.position().toPoint()) else None
        source = self._document.source if self._document is not None else None
        # Center only a completed selection, so a drag keeps its original geometry.
        owner = (self._navigation_owner if not self._drag_active
                 and self.rect().contains(event.position().toPoint()) else None)
        self.cancel_drag()
        self._navigate_owner(owner)
        if plan is not None and source is not None and plan.source != source:
            self.moveRequested.emit(source, plan)
        event.accept()

    def _boundary_y(self, offset):
        """Source insertion offset to its visual divider, never the reverse."""
        position = self._drag_index.display(offset)
        index = bisect_left(self._row_starts, position)
        previous = self.rows[index - 1] if index else None
        if index < len(self.rows):
            row = self.rows[index]
            top = row.top if previous is None else (previous.top + previous.height + row.top) / 2
            return self.map_origin().y() + top * self.scale
        bottom = previous.top + previous.height if previous is not None else 0
        return self.map_origin().y() + bottom * self.scale

    def _drag_source_rect(self):
        if self._drag_block is None or self._document is None:
            return QRectF()
        start = self._drag_index.display(self._drag_block.start)
        end = self._drag_index.display(self._drag_block.end)
        rows = self.rows[bisect_left(self._row_starts, start):bisect_left(self._row_starts, end)]
        if not rows:
            return QRectF()
        top, bottom = rows[0].top, rows[-1].top + rows[-1].height
        return QRectF(0, self.map_origin().y() + top * self.scale,
                      self.width(), (bottom - top) * self.scale)

    def drag_rect(self):
        rect = self._drag_source_rect()
        if self._drag_point is not None:
            rect.moveTop(self._drag_point.y() - self._drag_grab_fraction * rect.height())
        return rect

    def _update_drag_target(self):
        if not self._drag_active or self._drag_block is None or self._document is None:
            return
        self._drag_plan = self._drag_destination = None
        block = self._drag_block
        y = self._drag_point.y()
        if not (0 <= self._drag_point.x() < self.width() and 0 <= y < self.height()):
            self.update()
            return
        # Root first/last gaps may be approached through outer whitespace. A
        # nested block must stay inside its existing containing source scope.
        if ((block.scope_start > len(self._document.source) - len(self._document.source.lstrip('\ufeff'))
             and y < self._boundary_y(block.scope_start))
                or (block.scope_end < len(self._document.source) and y > self._boundary_y(block.scope_end))):
            self.update()
            return
        slots = self._move_model.slots(block.owner)
        if slots:
            target = min(slots, key=lambda offset: abs(self._boundary_y(offset) - y))
            self._drag_destination = target
            if target not in self._drag_plans:
                self._drag_plans[target] = self._move_model.plan(block.owner, target)
            self._drag_plan = self._drag_plans[target]
        self.update()

    def _scroll_changed(self, *_):
        if self._drag_active:
            self._update_drag_target()
        self.update()

    def _scroll_drag(self):
        if not self._drag_active or self._drag_point is None:
            return
        y = self._drag_point.y()
        direction = -1 if y < 18 else 1 if y > self.height() - 18 else 0
        if direction:
            bar = self.editor.verticalScrollBar()
            bar.setValue(bar.value() + direction * max(1, bar.singleStep() * 2))

    def _shape_dragged(self, owner):
        if not self._drag_active or self._drag_block is None or owner is None:
            return False
        return self._drag_block.start <= self._tree.nodes[owner].span.start < self._drag_block.end

    def _paint_drag(self, painter):
        if not self._drag_active:
            return
        source_rect, rect = self._drag_source_rect(), self.drag_rect()
        painter.save()
        painter.translate(self.map_origin() + QPointF(0, rect.top() - source_rect.top()))
        painter.scale(self.horizontal_scale, self.scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*EDIT_SELECTED_COLOR))
        for owner, shape in self.shapes:
            if self._shape_dragged(owner):
                painter.drawPath(shape)
        painter.restore()
        painter.save()
        if self._drag_plan is not None:
            painter.setPen(QPen(QColor(*EDIT_SELECTED_COLOR), 2))
            y = self._boundary_y(self._drag_destination)
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        else:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(*EDIT_INVALID_COLOR), 3))
            rect = rect.adjusted(2, 1, -2, -1)
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())
        painter.restore()

    def edit_arrows(self):
        """(whole owner, direction, screen center); one marker per direct neighbor.

        Direction follows the graph's receiver/source contract, never row order.
        Geometry is derived at paint time so zoom, scroll and resize stay aligned.
        The fixed right inset keeps the full marker clear of the map boundary.
        """
        if not self.edit_mode or self.selected_owner is None:
            return ()
        directions = set()
        for receiver, source in self._edit_relations:
            if receiver == self.selected_owner:
                directions.add((source, 'down'))
            if source == self.selected_owner:
                directions.add((receiver, 'up'))
        bounds = {}
        for owner, shape in self.shapes:
            whole = self._edit_owners.get(owner, owner)
            rect = shape.boundingRect()
            bounds[whole] = bounds[whole].united(rect) if whole in bounds else rect
        origin = self.map_origin()
        return tuple((owner, direction,
                      QPointF(self.width() - EDIT_ARROW_RIGHT_INSET,
                              origin.y() + bounds[owner].center().y() * self.scale))
                     for owner, direction in sorted(directions) if owner in bounds)

    def _paint_edit_arrows(self, painter):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(*EDIT_ARROW_COLOR), 2.5,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        for _, direction, center in self.edit_arrows():
            sign = 1 if direction == 'down' else -1
            x, y = center.x(), center.y()
            painter.drawLine(QPointF(x, y - sign * 6), QPointF(x, y + sign * 6))
            painter.drawPolyline(QPolygonF([QPointF(x - 4, y + sign * 2),
                                           QPointF(x, y + sign * 6),
                                           QPointF(x + 4, y + sign * 2)]))
        painter.restore()

    def wheelEvent(self, event):  # noqa: N802
        if self._timer.isActive():
            self.rebuild()
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if event.inverted():
            delta = -delta
        if delta:
            self.scale = max(self.minimum_scale, min(1.0, self.scale * math.pow(1.25, max(-20, min(20, delta / 120)))))
            self._fit = self.scale <= self.minimum_scale + 1e-12
            self._update_drag_target()
            self.update()
        event.accept()

    def resizeEvent(self, event):  # noqa: N802
        if not self.analysis_enabled or not self._geometry_ready:
            super().resizeEvent(event)
            return
        old = event.oldSize()
        if not self._fit and self.scale < 1.0 and old.height() > 0:
            old_fit = min(1.0, old.height() / self.extent.height())
            # Height changes preserve relative zoom; width has its own scale.
            self.scale *= self.minimum_scale / old_fit
        self._clamp_scale()
        self.update()
        super().resizeEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(*self.editor.color_scheme['editor']['background']))
        painter.setClipRect(self.rect())
        position_frame = self._position_frame
        if self.mode == 'semantic_triad_2' and self._position_display_ready:
            self._paint_positional_frame()
            position_frame = self._position_frame
            if self.edit_mode and self.selected_owner is not None:
                self._paint_positional_frame(edit=True)
                position_frame = self._position_edit_frame
        if self.mode == 'semantic_triad_2' and not position_frame.isNull():
            painter.drawImage(QRectF(self.rect()), position_frame)
        else:
            painter.save()
            painter.translate(self.map_origin())
            painter.scale(self.horizontal_scale, self.scale)
            painter.setPen(Qt.PenStyle.NoPen)
            if self._display_segments:
                # ST1 rows retain their original whole-block summary fill.
                for row in self.rows:
                    if self._shape_dragged(row.owner):
                        continue
                    for _, rect, color in self.row_segments(row):
                        painter.fillRect(rect, QColor(*color))
            else:
                for owner, shape in self.shapes:
                    if self._shape_dragged(owner):
                        continue
                    painter.setBrush(self.color_for_owner(owner))
                    painter.drawPath(shape)
            painter.restore()
        viewport_style = self.editor.color_scheme['map_viewport']
        painter.setPen(QPen(QColor(*viewport_style['foreground']), 1))
        painter.setBrush(QColor(*viewport_style['background']))
        # viewport_rect freezes the last display coordinates while stale.
        painter.drawRect(self.mapped_viewport())
        self._paint_edit_dividers(painter)
        self._paint_edit_arrows(painter)
        self._paint_drag(painter)
        if self.error and self.status_text:
            label = self.status_text
            metrics = painter.fontMetrics()
            if self.stale and metrics.horizontalAdvance(label) + 12 > self.width():
                label = 'Stale'
            height = metrics.height() + 8
            width = min(self.width(), metrics.horizontalAdvance(label) + 12)
            status_rect = QRectF(self.width() - width, 0, width, height)
            painter.fillRect(status_rect, QColor(24, 29, 35, 235))
            painter.setPen(QColor(235, 220, 177))
            painter.drawText(status_rect.adjusted(4, 0, -4, 0),
                             Qt.AlignmentFlag.AlignCenter,
                             metrics.elidedText(label, Qt.TextElideMode.ElideRight,
                                                max(1, width - 8)))
        painter.end()
