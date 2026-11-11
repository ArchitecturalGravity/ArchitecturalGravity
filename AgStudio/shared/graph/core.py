"""Pure deterministic scoring over detached relationships and source positions.

Heuristic mode preserves the original graph score. Semantic Triad consumes
declared object footprints and source-character geometry. Nothing here parses text, infers natural-language meaning, accesses
files/networks, or depends on Qt, editor state, or live syntax/analyzer objects.
"""
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
import math


GRAPH_MODES = ('heuristic', 'semantic_triad_1', 'semantic_triad_2')


def normalize_graph_mode(mode):
    """Normalize retired API names to the source-aligned detailed ST2 view.

    The former row-segment ST2 is retired; its identifier now selects the
    source-aligned mode. Former ST3 and unnumbered Triad inputs remain readable.
    Basic/Full are preference-only migrations, not numeric API modes.
    """
    return 'semantic_triad_2' if mode in ('semantic_triad', 'semantic_triad_3') else mode


def _number(value, name, minimum=0.0, maximum=None):
    if type(value) not in (int, float):
        raise TypeError(f'{name} must be a finite number')
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError(f'{name} must be finite') from error
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        bounds = f' >= {minimum}' if maximum is None else f' in [{minimum}, {maximum}]'
        raise ValueError(f'{name} must be finite and{bounds}')
    return value


def _position(value):
    if type(value) is not int or value < 0:
        raise ValueError('position must be a nonnegative integer character offset')
    return value


def _object_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('object must be a nonempty string')
    return value


@dataclass(frozen=True, slots=True)
class SemanticRepresentation:
    """Declared support at a source-character boundary, not inferred meaning."""
    object: str
    position: int
    weight: float = 1.0
    provenance: str = 'explicit'

    def __post_init__(self):
        _object_name(self.object)
        _position(self.position)
        object.__setattr__(self, 'weight', _number(self.weight, 'weight'))
        if self.provenance not in ('explicit', 'declaration', 'resolved_reference'):
            raise ValueError('unknown representation provenance')


@dataclass(frozen=True, slots=True)
class SemanticTransformation:
    """An explicit later operation on influence already present at position."""
    kind: str
    object: str
    position: int
    factor: float
    target: str | None = None
    provenance: str = 'explicit'

    def __post_init__(self):
        if self.kind not in ('reinforce', 'suppress', 'reinterpret'):
            raise ValueError('transformation kind must be reinforce, suppress, or reinterpret')
        _object_name(self.object)
        _position(self.position)
        minimum, maximum = (1.0, None) if self.kind == 'reinforce' else (0.0, 1.0)
        object.__setattr__(self, 'factor', _number(self.factor, 'factor', minimum, maximum))
        if self.kind == 'reinterpret':
            _object_name(self.target)
        elif self.target is not None:
            raise ValueError('target is only valid for reinterpret transformations')
        if self.provenance not in ('explicit', 'repeated_reference',
                                   'structural_competition', 'alias_transfer'):
            raise ValueError('unknown transformation provenance')


def _records(values, record_type, name):
    if not isinstance(values, (tuple, list)):
        raise TypeError(f'{name} must be a list or tuple')
    result = []
    for value in values:
        if isinstance(value, record_type):
            result.append(value)
        elif isinstance(value, Mapping):
            try:
                result.append(record_type(**value))
            except TypeError as error:
                raise TypeError(f'invalid {name} entry: {error}') from error
        else:
            raise TypeError(f'{name} entries must be objects')
    return tuple(result)


@dataclass(frozen=True, slots=True)
class SemanticOptions:
    """Finite, detached JSON-compatible settings for character coverage."""
    decay: float = 1.0
    parser_support: bool = True
    parser_transformations: bool = True
    representations: tuple[SemanticRepresentation, ...] = ()
    transformations: tuple[SemanticTransformation, ...] = ()
    selected_object: str | None = None
    comparison_objects: tuple[str, ...] = ()

    def __post_init__(self):
        if self.selected_object is not None:
            _object_name(self.selected_object)
        if not isinstance(self.comparison_objects, (tuple, list)):
            raise TypeError('comparison_objects must be a list or tuple')
        object.__setattr__(self, 'comparison_objects', tuple(dict.fromkeys(
            _object_name(name) for name in self.comparison_objects)))
        object.__setattr__(self, 'decay', _number(self.decay, 'decay'))
        if type(self.parser_support) is not bool:
            raise TypeError('parser_support must be a boolean')
        if type(self.parser_transformations) is not bool:
            raise TypeError('parser_transformations must be a boolean')
        object.__setattr__(self, 'representations',
                           _records(self.representations, SemanticRepresentation, 'representations'))
        object.__setattr__(self, 'transformations',
                           _records(self.transformations, SemanticTransformation, 'transformations'))


def validate_options(options=None, source_length=None):
    """Validate user JSON and return frozen settings; never read or change files.

    Positions, including a position at EOF, must be in [0, source_length] when
    a length is supplied. Unknown keys, booleans-as-numbers and NaN are errors.
    """
    if options is None:
        options = SemanticOptions()
    elif isinstance(options, Mapping):
        try:
            options = SemanticOptions(**options)
        except TypeError as error:
            raise TypeError(f'invalid semantic options: {error}') from error
    elif not isinstance(options, SemanticOptions):
        raise TypeError('semantic options must be an object')
    if source_length is not None:
        _position(source_length)
        for event in options.representations + options.transformations:
            if event.position > source_length:
                raise ValueError(f'position {event.position} exceeds source length {source_length}')
    return options


class HeatCancelled(Exception):
    """Cooperative cancellation of disposable graph work, never diagnostics."""


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise HeatCancelled()


def _id_pairs(pairs):
    """Detach caller-owned containers and admit only serializable block IDs."""
    result = tuple(tuple(pair) for pair in pairs)
    if any(len(pair) != 2 or any(type(value) is not int for value in pair)
           for pair in result):
        raise TypeError('graph pairs must contain two integer IDs')
    return result


def _spans(values):
    """Validate and detach half-open character spans; union happens at readout."""
    pairs = _id_pairs(values)
    if any(start < 0 or end < start for start, end in pairs):
        raise ValueError('support spans must satisfy 0 <= start <= end')
    return pairs


@dataclass(frozen=True, slots=True)
class SemanticFootprint:
    """Inclusive definition and resolved mention positions for one identity."""
    object: str
    definitions: tuple[tuple[int, int], ...] = ()
    mentions: tuple[tuple[int, int], ...] = ()
    children: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    available_from: int = 0

    def __post_init__(self):
        _object_name(self.object)
        _position(self.available_from)
        object.__setattr__(self, 'definitions', _spans(self.definitions))
        object.__setattr__(self, 'mentions', _spans(self.mentions))
        object.__setattr__(self, 'children', tuple(dict.fromkeys(
            _object_name(name) for name in self.children)))
        if any(not isinstance(value, str) for value in self.relationships):
            raise TypeError('relationships must contain descriptive strings')
        object.__setattr__(self, 'relationships', tuple(self.relationships))


@dataclass(frozen=True, slots=True)
class SemanticElement:
    """Direct physical support and directed dependencies for one map element.

    Definitions and mentions stay intrinsic to this element. The final map
    unions that support with every reachable dependency's support. Identity is
    opaque: named declarations and detached structural IDs obey the same rules.
    """
    object: str
    definitions: tuple[tuple[int, int], ...] = ()
    mentions: tuple[tuple[int, int], ...] = ()
    dependencies: tuple[str, ...] = ()
    node: int | None = None
    label: str = ''

    def __post_init__(self):
        _object_name(self.object)
        object.__setattr__(self, 'definitions', _spans(self.definitions))
        object.__setattr__(self, 'mentions', _spans(self.mentions))
        if not isinstance(self.dependencies, (tuple, list)):
            raise TypeError('semantic element dependencies must be a list or tuple')
        object.__setattr__(self, 'dependencies', tuple(dict.fromkeys(
            _object_name(name) for name in self.dependencies)))
        if self.node is not None and type(self.node) is not int:
            raise TypeError('semantic element node must be an integer ID or None')
        if not isinstance(self.label, str):
            raise TypeError('semantic element label must be a string')


@dataclass(frozen=True, slots=True)
class SemanticView:
    """Automatic display identity and causal readout for one syntax node."""
    node: int
    position: int
    objects: tuple[str, ...] = ()
    kind: str = 'all_objects'

    def __post_init__(self):
        if type(self.node) is not int:
            raise TypeError('semantic view node must be an integer ID')
        _position(self.position)
        if not isinstance(self.objects, (tuple, list)):
            raise TypeError('semantic view objects must be a list or tuple')
        names = tuple(dict.fromkeys(_object_name(name) for name in self.objects))
        # Immutable canonical order is shared by all unowned node views rather
        # than retained once per node. Mutable caller containers are detached.
        object.__setattr__(self, 'objects', self.objects if names == self.objects else names)
        if self.kind not in ('named_block', 'named_context', 'reference_use',
                             'alias_use', 'all_objects'):
            raise ValueError('unknown semantic view kind')


@dataclass(frozen=True, slots=True)
class SemanticPosition:
    """One exact source event; many events may belong to one syntax node.

    Python-character boundaries use [0, N]. An event describes display
    association only; it neither adds support nor filters all-object readouts.
    """
    position: int
    objects: tuple[str, ...] = ()
    kind: str = 'object_end'
    node: int | None = None

    def __post_init__(self):
        _position(self.position)
        if self.node is not None and type(self.node) is not int:
            raise TypeError('semantic position node must be an integer ID or None')
        if not isinstance(self.objects, (tuple, list)):
            raise TypeError('semantic position objects must be a list or tuple')
        object.__setattr__(self, 'objects', tuple(dict.fromkeys(
            _object_name(name) for name in self.objects)))
        if self.kind not in ('object_start', 'object_end', 'object_available',
                             'reference_start', 'reference_use', 'alias_use'):
            raise ValueError('unknown semantic position kind')


@dataclass(frozen=True, slots=True)
class SemanticCoverage:
    """Normalized geometry, not semantic reactivation or conflict estimates."""
    object: str
    inclusive_weight: float = 0.0
    own_weight: float = 0.0
    definition: float = 0.0
    mention: float = 0.0
    linked: float = 0.0
    adjusted_definition: float = 0.0
    adjusted_mention: float = 0.0
    adjusted_linked: float = 0.0
    comparison: float = 0.0
    adjusted_comparison: float = 0.0
    shared: float = 0.0
    other_only: float = 0.0
    relationships: tuple[str, ...] = ()

    def __post_init__(self):
        _object_name(self.object)
        for field in ('inclusive_weight', 'own_weight', 'definition', 'mention',
                      'linked', 'adjusted_definition', 'adjusted_mention',
                      'adjusted_linked', 'comparison', 'adjusted_comparison',
                      'shared', 'other_only'):
            object.__setattr__(self, field, _number(getattr(self, field), field))
        if not isinstance(self.relationships, (tuple, list)) or any(
                not isinstance(value, str) for value in self.relationships):
            raise TypeError('relationships must contain descriptive strings')
        object.__setattr__(self, 'relationships', tuple(self.relationships))


@dataclass(frozen=True, slots=True)
class HeatScore:
    direct: float = 0.0
    indirect: float = 0.0
    direct_count: int = 0
    indirect_count: int = 0

    @property
    def total(self):
        return self.direct + self.indirect


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """Detached graph input, with no references to a live document.

    Blocks identifies the scoreable whole blocks. Occurrences retains each
    directed (receiver, source) occurrence, including repeated references.
    Owners maps every syntax-node ID to its whole-block ID for later display;
    it is opaque to the scoring algorithm. Ordering and multiplicity are kept.
    Caller-owned sequences are copied to immutable tuples at construction.
    Semantic Triad additionally carries source-character end positions, named
    causal footprints, and all-element direct spans and directed dependencies
    for complete-document inherited map baselines.
    The first three positional arguments retain the original heuristic API.
    """
    blocks: tuple[int, ...]
    occurrences: tuple[tuple[int, int], ...]
    owners: tuple[tuple[int, int], ...]
    mode: str = 'heuristic'
    options: SemanticOptions = SemanticOptions()
    semantic_evidence: tuple[SemanticRepresentation, ...] = ()
    points: tuple[tuple[int, int], ...] = ()
    document_length: int = 0
    semantic_transformations: tuple[SemanticTransformation, ...] = ()
    semantic_footprints: tuple[SemanticFootprint, ...] = ()
    semantic_views: tuple[SemanticView, ...] = ()
    semantic_positions: tuple[SemanticPosition, ...] = ()
    semantic_elements: tuple[SemanticElement, ...] = ()

    def __post_init__(self):
        blocks = tuple(self.blocks)
        if any(type(block) is not int for block in blocks):
            raise TypeError('graph blocks must contain integer IDs')
        object.__setattr__(self, 'blocks', blocks)
        object.__setattr__(self, 'occurrences', _id_pairs(self.occurrences))
        object.__setattr__(self, 'owners', _id_pairs(self.owners))
        mode = normalize_graph_mode(self.mode)
        if mode not in GRAPH_MODES:
            raise ValueError(f'unknown graph mode: {self.mode!r}')
        object.__setattr__(self, 'mode', mode)
        _position(self.document_length)
        object.__setattr__(self, 'options', validate_options(self.options, self.document_length))
        evidence = _records(self.semantic_evidence, SemanticRepresentation, 'semantic_evidence')
        if any(event.position > self.document_length for event in evidence):
            raise ValueError('semantic evidence position exceeds document length')
        object.__setattr__(self, 'semantic_evidence', evidence)
        transforms = _records(self.semantic_transformations, SemanticTransformation,
                              'semantic_transformations')
        if any(event.position > self.document_length for event in transforms):
            raise ValueError('semantic transformation position exceeds document length')
        object.__setattr__(self, 'semantic_transformations', transforms)
        footprints = _records(self.semantic_footprints, SemanticFootprint, 'semantic_footprints')
        if len({item.object for item in footprints}) != len(footprints):
            raise ValueError('semantic footprints require unique object identities')
        if any(item.available_from > self.document_length or any(
                end > self.document_length for _, end in item.definitions + item.mentions)
                for item in footprints):
            raise ValueError('semantic footprint exceeds document length')
        object.__setattr__(self, 'semantic_footprints', footprints)
        elements = _records(self.semantic_elements, SemanticElement, 'semantic_elements')
        element_names = {item.object for item in elements}
        if len(element_names) != len(elements):
            raise ValueError('semantic elements require unique object identities')
        if any(end > self.document_length for item in elements
               for _, end in item.definitions + item.mentions):
            raise ValueError('semantic element exceeds document length')
        if any(set(item.dependencies) - element_names for item in elements):
            raise ValueError('semantic element references unknown dependency identities')
        object.__setattr__(self, 'semantic_elements', elements)
        views = _records(self.semantic_views, SemanticView, 'semantic_views')
        if len({view.node for view in views}) != len(views):
            raise ValueError('semantic views require unique node IDs')
        names = {item.object for item in footprints} | element_names
        if any(view.position > self.document_length for view in views):
            raise ValueError('semantic view exceeds document length')
        if any(set(view.objects) - names for view in views):
            raise ValueError('semantic view references unknown object identities')
        object.__setattr__(self, 'semantic_views', views)
        positions = _records(self.semantic_positions, SemanticPosition, 'semantic_positions')
        if any(event.position > self.document_length for event in positions):
            raise ValueError('semantic position exceeds document length')
        if any(set(event.objects) - names for event in positions):
            raise ValueError('semantic position references unknown object identities')
        object.__setattr__(self, 'semantic_positions', positions)
        points = _id_pairs(self.points)
        if any(position < 0 or position > self.document_length for _, position in points):
            raise ValueError('point of use must be within the document')
        if len({block for block, _ in points}) != len(points):
            raise ValueError('each block must have a single point of use')
        if self.mode != 'heuristic' and {block for block, _ in points} != set(blocks):
            raise ValueError('semantic points must cover exactly the scoreable blocks')
        object.__setattr__(self, 'points', points)


@dataclass(frozen=True, slots=True)
class GraphResult:
    """Immutable result; scores are sorted by block ID.

    Owners and relations preserve the snapshot's original ordering. Relations
    are occurrences, not grouped edges: their multiplicity remains available
    to consumers even though scoring groups them internally.
    Semantic states preserve each object's adjusted coverage at every block readout;
    heuristic mode leaves this optional field empty for legacy compatibility.
    """
    owners: tuple[tuple[int, int], ...]
    scores: tuple[tuple[int, HeatScore], ...]
    relations: tuple[tuple[int, int], ...]
    states: tuple[tuple[int, tuple[tuple[str, float], ...]], ...] = ()
    details: tuple[tuple[int, tuple[SemanticCoverage, ...]], ...] = ()
    semantic_views: tuple[SemanticView, ...] = ()
    view_details: tuple[tuple[int, tuple[SemanticCoverage, ...]], ...] = ()
    position_values: tuple[tuple[int, tuple[tuple[str, float], ...]], ...] = ()
    position_maximum: float = 0.0
    position_snapshot: GraphSnapshot | None = None
    final_details: tuple[SemanticCoverage, ...] = ()

    def __post_init__(self):
        scores = tuple(tuple(pair) for pair in self.scores)
        if any(len(pair) != 2 or type(pair[0]) is not int
               or not isinstance(pair[1], HeatScore) for pair in scores):
            raise TypeError('graph scores must contain integer IDs and HeatScore values')
        object.__setattr__(self, 'owners', _id_pairs(self.owners))
        object.__setattr__(self, 'scores', scores)
        object.__setattr__(self, 'relations', _id_pairs(self.relations))
        states = []
        for block, values in self.states:
            if type(block) is not int:
                raise TypeError('semantic state block IDs must be integers')
            detached = tuple((_object_name(name), _number(value, 'influence'))
                             for name, value in values)
            if len({name for name, _ in detached}) != len(detached):
                raise ValueError('semantic states must contain unique object names')
            states.append((block, detached))
        if len({block for block, _ in states}) != len(states):
            raise ValueError('semantic states must contain unique block IDs')
        object.__setattr__(self, 'states', tuple(states))
        details = tuple((block, _records(values, SemanticCoverage, 'details'))
                        for block, values in self.details)
        if any(type(block) is not int for block, _ in details):
            raise TypeError('semantic detail block IDs must be integers')
        if len({block for block, _ in details}) != len(details):
            raise ValueError('semantic details must contain unique block IDs')
        if any(len({item.object for item in values}) != len(values) for _, values in details):
            raise ValueError('semantic details must contain unique object identities')
        object.__setattr__(self, 'details', details)
        views = _records(self.semantic_views, SemanticView, 'semantic_views')
        if len({view.node for view in views}) != len(views):
            raise ValueError('semantic views require unique node IDs')
        object.__setattr__(self, 'semantic_views', views)
        view_details = tuple((node, _records(values, SemanticCoverage, 'view_details'))
                             for node, values in self.view_details)
        if any(type(node) is not int for node, _ in view_details):
            raise TypeError('semantic view detail IDs must be integers')
        if len({node for node, _ in view_details}) != len(view_details):
            raise ValueError('semantic view details require unique node IDs')
        if any(len({item.object for item in values}) != len(values)
               for _, values in view_details):
            raise ValueError('semantic view details require unique object identities')
        object.__setattr__(self, 'view_details', view_details)
        positions = []
        for position, values in self.position_values:
            _position(position)
            detached = tuple((_object_name(name), _number(value, 'influence'))
                             for name, value in values)
            if len({name for name, _ in detached}) != len(detached):
                raise ValueError('semantic position values require unique objects')
            positions.append((position, detached))
        if len({position for position, _ in positions}) != len(positions):
            raise ValueError('semantic position values require unique positions')
        object.__setattr__(self, 'position_values', tuple(positions))
        object.__setattr__(self, 'position_maximum',
                           _number(self.position_maximum, 'position_maximum'))
        snapshot = self.position_snapshot
        if isinstance(snapshot, Mapping):
            snapshot = GraphSnapshot(**snapshot)
        if snapshot is not None and not isinstance(snapshot, GraphSnapshot):
            raise TypeError('position_snapshot must be a GraphSnapshot or None')
        if snapshot is not None:
            names = {item.object for item in snapshot.semantic_footprints}
            names.update(item.object for item in snapshot.semantic_elements)
            if any(position > snapshot.document_length for position, _ in positions):
                raise ValueError('semantic position values exceed document length')
            if any(name not in names for _, values in positions for name, _ in values):
                raise ValueError('semantic position values reference unknown objects')
        object.__setattr__(self, 'position_snapshot', snapshot)
        final = _records(self.final_details, SemanticCoverage, 'final_details')
        if len({item.object for item in final}) != len(final):
            raise ValueError('final details require unique object identities')
        object.__setattr__(self, 'final_details', final)


def score_relations(blocks, occurrences, *, cancelled=None):
    """Return uncapped direct/indirect scores, counting no path more than once.

Each directed (receiver, source) pair contributes 1 to its receiver and its
occurrence count to its source. Each other block gets the nearer endpoint's
weight / 2**distance in the undirected graph; equal distances use the larger
weight once. Endpoints never receive reflected heat from their own relation.
Breadth-first traversal makes cycles finite and avoids enumerating paths.
Direct counts follow the same asymmetric occurrence/deduplication rule as
direct weights. Indirect counts record contributing grouped relationships,
not their weights, the number of hops, or the number of possible paths.
    """
    _check_cancelled(cancelled)
    blocks = set(blocks)
    counts = Counter()
    for receiver, source in occurrences:
        _check_cancelled(cancelled)
        if receiver != source and receiver in blocks and source in blocks:
            counts[receiver, source] += 1
    adjacency = {block: set() for block in blocks}
    direct = dict.fromkeys(blocks, 0)
    indirect = dict.fromkeys(blocks, 0.0)
    direct_counts = dict.fromkeys(blocks, 0)
    indirect_counts = dict.fromkeys(blocks, 0)
    relations = sorted(counts.items())
    for (receiver, source), count in relations:
        _check_cancelled(cancelled)
        adjacency[receiver].add(source)
        adjacency[source].add(receiver)
        direct[receiver] += 1
        direct[source] += count
        direct_counts[receiver] += 1
        direct_counts[source] += count
    adjacency = {block: tuple(sorted(neighbors)) for block, neighbors in adjacency.items()}
    for (receiver, source), count in relations:
        _check_cancelled(cancelled)
        distances = {receiver: 0, source: 0}
        weights = {receiver: 1, source: count}
        pending = deque((receiver, source))
        while pending:
            _check_cancelled(cancelled)
            block = pending.popleft()
            distance = distances[block] + 1
            for neighbor in adjacency[block]:
                if neighbor not in distances:
                    distances[neighbor] = distance
                    weights[neighbor] = weights[block]
                    pending.append(neighbor)
                elif distances[neighbor] == distance:
                    weights[neighbor] = max(weights[neighbor], weights[block])
            if block not in (receiver, source):
                indirect[block] += math.ldexp(float(weights[block]), -distances[block])
                indirect_counts[block] += 1
    return {block: HeatScore(direct[block], indirect[block],
                             direct_counts[block], indirect_counts[block])
            for block in sorted(blocks)}



def calculate_graph(snapshot: GraphSnapshot, *, cancelled=None) -> GraphResult:
    """Calculate exact scores using only a detached graph snapshot.

    Cancellation raises HeatCancelled and never publishes a partial result.
    Self-relations and endpoints outside snapshot.blocks do not affect scores,
    matching score_relations; the original occurrence records are retained.
    """
    _check_cancelled(cancelled)
    states, details, view_details, final_details = (), (), (), ()
    if snapshot.mode == 'heuristic':
        scores = score_relations(snapshot.blocks, snapshot.occurrences, cancelled=cancelled)
    elif snapshot.mode == 'semantic_triad_2':
        from .semantic import (calculate_semantic_positions, calculate_inherited_details,
                               PreparedSemantic)
        prepared = PreparedSemantic(snapshot, cancelled=cancelled)
        final_details = (calculate_inherited_details(snapshot, cancelled=cancelled)
                         if snapshot.semantic_elements else
                         prepared.details_at(snapshot.document_length, cancelled=cancelled))
        scores, position_values, maximum = calculate_semantic_positions(
            snapshot, cancelled=cancelled, prepared=prepared, final_details=final_details)
        _check_cancelled(cancelled)
        return GraphResult(snapshot.owners, tuple(scores.items()), snapshot.occurrences,
                           semantic_views=snapshot.semantic_views,
                           position_values=position_values, position_maximum=maximum,
                           position_snapshot=snapshot, final_details=final_details)
    else:
        from .semantic import (calculate_semantic_details, calculate_semantic_views,
                               calculate_inherited_details)
        scores, states, details = calculate_semantic_details(snapshot, cancelled=cancelled)
        if snapshot.semantic_elements:
            final_details = calculate_inherited_details(snapshot, cancelled=cancelled)
        view_details = calculate_semantic_views(snapshot, cancelled=cancelled,
                                                final_details=final_details
                                                if snapshot.semantic_elements else None)
        if not snapshot.semantic_elements and view_details:
            final_details = view_details[0][1]
    _check_cancelled(cancelled)
    return GraphResult(snapshot.owners, tuple(scores.items()), snapshot.occurrences, states, details,
                       snapshot.semantic_views, view_details,
                       position_snapshot=snapshot if snapshot.semantic_elements else None,
                       final_details=final_details)
