"""Causal character coverage with an explicitly declared locality kernel.

A source character is counted once per identity/union. Inclusive parent and
child footprints intentionally overlap. Nothing estimates semantic reactivation,
contradiction, override, attention, or measured language-model behavior.
"""
import math
from bisect import bisect_right
from collections import deque
from dataclasses import replace

from .core import HeatScore, SemanticCoverage, _check_cancelled, _position


def union_spans(spans, *, cancelled=None):
    """Canonical union of half-open spans, merging overlaps and adjacency."""
    def checked():
        for span in spans:
            _check_cancelled(cancelled)
            yield span

    result = []
    for start, end in sorted(checked()):
        _check_cancelled(cancelled)
        if start >= end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return tuple(result)


def subtract_spans(spans, removed):
    """Set difference of canonical interval unions, without expanding characters."""
    removed = union_spans(removed)
    result = []
    index = 0
    for start, end in union_spans(spans):
        while index < len(removed) and removed[index][1] <= start:
            index += 1
        cursor, current = start, index
        while current < len(removed) and removed[current][0] < end:
            left, right = removed[current]
            if cursor < left:
                result.append((cursor, min(left, end)))
            cursor = max(cursor, right)
            if cursor >= end:
                break
            current += 1
        if cursor < end:
            result.append((cursor, end))
    return tuple(result)


def _support_layers(collections, *, cancelled=None):
    """Union and positions supported by multiple distinct identities."""
    events = {}
    for spans in collections:
        _check_cancelled(cancelled)
        for start, end in spans:
            _check_cancelled(cancelled)
            events[start] = events.get(start, 0) + 1
            events[end] = events.get(end, 0) - 1
    merged, shared = [], []
    count, previous = 0, None
    for position, change in sorted(events.items()):
        _check_cancelled(cancelled)
        if previous is not None and previous < position:
            if count:
                merged.append((previous, position))
            if count > 1:
                shared.append((previous, position))
        count += change
        previous = position
    return union_spans(merged), union_spans(shared)


def _intersection_counter(spans):
    """Index a union for logarithmic range-length queries."""
    starts, ends, prefix = [], [], [0]
    for start, end in spans:
        starts.append(start)
        ends.append(end)
        prefix.append(prefix[-1] + end - start)

    def before(position):
        index = bisect_right(starts, position) - 1
        if index < 0:
            return 0
        return prefix[index] + min(position, ends[index]) - starts[index]

    return lambda intervals: sum(before(end) - before(start) for start, end in intervals)


def _clip(spans, point):
    return tuple((start, min(end, point)) for start, end in spans if start < point)


def _size(spans):
    return sum(end - start for start, end in spans)


def _coverage(spans, point, length, decay):
    """Sum exp(-decay*(u-x)/N)/N at each character's right boundary x.

    Uses a stable finite geometric sum; no per-character storage is needed.
    The character [i,i+1) becomes available at i+1, never before it exists.
    """
    if not length:
        return 0.0
    if decay == 0:
        return _size(spans) / length
    rate = decay / length
    if rate == 0:  # subnormal finite settings may underflow after normalization
        return _size(spans) / length
    denominator = -math.expm1(-rate)
    return math.fsum(
        math.exp(-rate * (point - end)) * (-math.expm1(-rate * (end-start)))
        / denominator / length for start, end in spans)


def _readouts(snapshot, points, *, cancelled=None):
    _check_cancelled(cancelled)
    # Legacy record classes remain importable for loading/validation. Mixing
    # arbitrary point masses/operators into character coverage is undefined.
    if (snapshot.options.representations or snapshot.options.transformations
            or snapshot.semantic_evidence or snapshot.semantic_transformations):
        raise ValueError('Semantic Triad now uses semantic_footprints; point representations '
                         'and transformations cannot be mixed with character coverage')
    footprints = snapshot.semantic_footprints if snapshot.options.parser_support else ()
    by_name = {item.object: item for item in footprints}
    definitions = {name: union_spans(item.definitions) for name, item in by_name.items()}
    mentions = {name: union_spans(item.mentions) for name, item in by_name.items()}
    length = snapshot.document_length
    norm = max(1, length)
    scope = snapshot.options.comparison_objects or tuple(sorted(by_name))
    missing = set(scope) - by_name.keys()
    if missing:
        raise ValueError('unknown comparison objects: ' + ', '.join(sorted(missing)))
    selected = snapshot.options.selected_object
    if selected is not None and selected not in by_name:
        raise ValueError('unknown selected object: ' + selected)
    intrinsic = {}
    for name, item in by_name.items():
        _check_cancelled(cancelled)
        children = union_spans(span for child in item.children
                               for span in definitions.get(child, ()))
        intrinsic[name] = (_size(definitions[name]) / norm,
                           _size(subtract_spans(definitions[name], children)) / norm)
    results, by_point = {}, {}
    for block, point in points:
        _check_cancelled(cancelled)
        if point in by_point:
            results[block] = by_point[point]
            continue
        direct, refs, linked = {}, {}, {}
        for name, item in by_name.items():
            _check_cancelled(cancelled)
            direct[name] = _clip(definitions[name], point) if point >= item.available_from else ()
            refs[name] = _clip(mentions[name], point) if point >= item.available_from else ()
            linked[name] = union_spans(direct[name] + refs[name])
        comparison, multiple = _support_layers((linked[name] for name in scope),
                                               cancelled=cancelled)
        comparison_size = _size(comparison)
        comparison_overlap = _intersection_counter(comparison)
        multiple_overlap = _intersection_counter(multiple)
        comparison_weight = comparison_size / norm
        comparison_adjusted = _coverage(comparison, point, length, snapshot.options.decay)
        values = []
        for name in sorted(by_name):
            _check_cancelled(cancelled)
            other_only = comparison_size - comparison_overlap(linked[name])
            shared = (multiple_overlap if name in scope else comparison_overlap)(linked[name])
            inclusive, own = intrinsic[name]
            values.append(SemanticCoverage(
                name, inclusive, own, _size(direct[name])/norm, _size(refs[name])/norm,
                _size(linked[name])/norm,
                _coverage(direct[name], point, length, snapshot.options.decay),
                _coverage(refs[name], point, length, snapshot.options.decay),
                _coverage(linked[name], point, length, snapshot.options.decay),
                comparison_weight, comparison_adjusted, shared/norm, other_only/norm,
                by_name[name].relationships))
        results[block] = by_point[point] = tuple(values)
    _check_cancelled(cancelled)
    return results


def semantic_state(snapshot, position, *, cancelled=None):
    """Sorted per-object locality-adjusted linked coverage at a causal readout."""
    if snapshot.mode not in ('semantic_triad_1', 'semantic_triad_2'):
        raise ValueError('semantic_state requires a semantic graph mode')
    _position(position)
    if position > snapshot.document_length:
        raise ValueError('point of use exceeds document length')
    return tuple((item.object, item.adjusted_linked) for item in
                 _readouts(snapshot, ((0, position),), cancelled=cancelled)[0])


def calculate_semantic_details(snapshot, *, cancelled=None):
    readouts = _readouts(snapshot, snapshot.points, cancelled=cancelled)
    scores, states, details = {}, [], []
    for block, values in sorted(readouts.items()):
        selected = next((item for item in values if item.object == snapshot.options.selected_object),
                        values[0] if values else None)
        scores[block] = HeatScore(selected.adjusted_linked if selected else 0.0)
        states.append((block, tuple((item.object, item.adjusted_linked) for item in values)))
        details.append((block, values))
    return scores, tuple(states), tuple(details)


def calculate_semantic(snapshot, *, cancelled=None):
    """Compatibility pair: selected-object HeatScore and per-object states."""
    scores, states, _ = calculate_semantic_details(snapshot, cancelled=cancelled)
    return scores, states


def score_semantic(snapshot, *, cancelled=None):
    return calculate_semantic(snapshot, cancelled=cancelled)[0]


def calculate_semantic_views(snapshot, *, cancelled=None, final_details=None):
    """Automatic all-object final states, independent of UI/user selections.

    Primary identities describe only display association, never numerical
    filtering. Every view retains every object's state in declaration order.
    """
    if not snapshot.semantic_views:
        return ()
    if snapshot.semantic_elements:
        if final_details is None:
            final_details = calculate_inherited_details(snapshot, cancelled=cancelled)
        result = []
        for view in sorted(snapshot.semantic_views, key=lambda view: view.node):
            _check_cancelled(cancelled)
            result.append((view.node, final_details))
        return tuple(result)
    automatic = replace(snapshot, options=replace(snapshot.options,
                        selected_object=None, comparison_objects=()))
    readouts = _readouts(automatic, tuple((view.node, snapshot.document_length)
                                        for view in snapshot.semantic_views),
                        cancelled=cancelled)
    order = {item.object: index for index, item in enumerate(snapshot.semantic_footprints)}
    return tuple((node, tuple(sorted(values, key=lambda item: order[item.object])))
                 for node, values in sorted(readouts.items()))


def _inherited_support(elements, definitions, mentions, *, cancelled=None):
    """Union reachable support once per strongly connected component.

    Iterative graph traversals handle deep contexts and cycles without recursive
    paths or a characters-by-elements matrix. A dependency-first condensed DAG
    shares identical interval unions, including all members of a cycle.
    """
    names = tuple(item.object for item in elements)
    adjacency = {item.object: item.dependencies for item in elements}
    reverse = {name: [] for name in names}
    for name, dependencies in adjacency.items():
        _check_cancelled(cancelled)
        for dependency in dependencies:
            _check_cancelled(cancelled)
            reverse[dependency].append(name)

    # Kosaraju's first pass records finishing order with an explicit DFS stack.
    seen, order = set(), []
    for name in names:
        _check_cancelled(cancelled)
        if name in seen:
            continue
        seen.add(name)
        pending = [(name, iter(adjacency[name]))]
        while pending:
            _check_cancelled(cancelled)
            current, dependencies = pending[-1]
            dependency = next(dependencies, None)
            if dependency is None:
                order.append(current)
                pending.pop()
            elif dependency not in seen:
                seen.add(dependency)
                pending.append((dependency, iter(adjacency[dependency])))

    components, membership = [], {}
    for name in reversed(order):
        _check_cancelled(cancelled)
        if name in membership:
            continue
        component = len(components)
        members, pending = [], [name]
        membership[name] = component
        while pending:
            _check_cancelled(cancelled)
            current = pending.pop()
            members.append(current)
            for predecessor in reverse[current]:
                _check_cancelled(cancelled)
                if predecessor not in membership:
                    membership[predecessor] = component
                    pending.append(predecessor)
        components.append(members)

    dependencies = [set() for _ in components]
    dependents = [set() for _ in components]
    for name in names:
        _check_cancelled(cancelled)
        component = membership[name]
        for dependency in adjacency[name]:
            _check_cancelled(cancelled)
            target = membership[dependency]
            if target != component:
                dependencies[component].add(target)
                dependents[target].add(component)

    remaining = [len(items) for items in dependencies]
    pending = deque(index for index, count in enumerate(remaining) if not count)
    support, interned = {}, {}
    while pending:
        _check_cancelled(cancelled)
        component = pending.popleft()

        def spans():
            for name in components[component]:
                _check_cancelled(cancelled)
                yield from definitions[name]
                yield from mentions[name]
            for dependency in dependencies[component]:
                _check_cancelled(cancelled)
                yield from support[dependency]

        union = union_spans(spans(), cancelled=cancelled)
        support[component] = interned.setdefault(union, union)
        for dependent in dependents[component]:
            _check_cancelled(cancelled)
            remaining[dependent] -= 1
            if not remaining[dependent]:
                pending.append(dependent)
    _check_cancelled(cancelled)
    return {name: support[membership[name]] for name in names}


def calculate_inherited_details(snapshot, *, cancelled=None):
    """Complete-document baselines over directed transitive physical support.

    S(e) is the union of direct definitions and resolved mentions of e and each
    reachable dependency. B(e) applies the existing character-locality kernel
    once to S(e) at N. Paths, repeats, cycles, and diamonds add no multipliers.
    Intrinsic definition/mention fields and the named causal API stay separate.
    """
    _check_cancelled(cancelled)
    if snapshot.mode not in ('semantic_triad_1', 'semantic_triad_2'):
        raise ValueError('calculate_inherited_details requires a semantic graph mode')
    if (snapshot.options.representations or snapshot.options.transformations
            or snapshot.semantic_evidence or snapshot.semantic_transformations):
        raise ValueError('Semantic Triad now uses semantic_footprints; point representations '
                         'and transformations cannot be mixed with character coverage')
    if not snapshot.semantic_elements:
        return PreparedSemantic(snapshot, cancelled=cancelled).details_at(
            snapshot.document_length, cancelled=cancelled)
    elements = snapshot.semantic_elements if snapshot.options.parser_support else ()
    definitions, mentions = {}, {}
    for item in elements:
        _check_cancelled(cancelled)
        definitions[item.object] = union_spans(item.definitions, cancelled=cancelled)
        mentions[item.object] = union_spans(item.mentions, cancelled=cancelled)
    linked = _inherited_support(elements, definitions, mentions, cancelled=cancelled)
    comparison, multiple = _support_layers(linked.values(), cancelled=cancelled)
    comparison_size = _size(comparison)
    multiple_overlap = _intersection_counter(multiple)
    length, decay = snapshot.document_length, snapshot.options.decay
    norm = max(1, length)
    comparison_adjusted = _coverage(comparison, length, length, decay)
    footprints = {item.object: item for item in snapshot.semantic_footprints}
    result = []
    for item in elements:
        _check_cancelled(cancelled)
        name = item.object
        direct, refs, inherited = definitions[name], mentions[name], linked[name]
        footprint = footprints.get(name)
        children = (union_spans((span for child in footprint.children
                                 for span in definitions.get(child, ())),
                                cancelled=cancelled) if footprint else ())
        size = _size(inherited)
        result.append(SemanticCoverage(
            name, _size(direct)/norm, _size(subtract_spans(direct, children))/norm,
            _size(direct)/norm, _size(refs)/norm, size/norm,
            _coverage(direct, length, length, decay),
            _coverage(refs, length, length, decay),
            _coverage(inherited, length, length, decay),
            comparison_size/norm, comparison_adjusted,
            multiple_overlap(inherited)/norm, (comparison_size-size)/norm,
            footprint.relationships if footprint else ()))
    _check_cancelled(cancelled)
    return tuple(result)


class _CoverageIndex:
    """Linear interval storage and logarithmic arbitrary-position readouts.

    Prefix weighted sums are stored at their own interval ends and decayed
    forward when queried. This avoids exp(+decay*u/N), including overflow at
    large but valid decay settings.
    """
    __slots__ = ('spans', 'starts', 'prefix', 'weighted', 'length', 'rate')

    def __init__(self, spans, length, decay, *, cancelled=None):
        self.spans = spans
        self.starts = tuple(start for start, _ in spans)
        self.length = length
        self.rate = decay / length if length else 0.0
        prefix, weighted = [0], []
        previous_end, previous_weight = 0, 0.0
        for start, end in spans:
            _check_cancelled(cancelled)
            previous_weight = (previous_weight * math.exp(-self.rate * (end - previous_end))
                               + self._segment(end - start))
            weighted.append(previous_weight)
            prefix.append(prefix[-1] + end - start)
            previous_end = end
        self.prefix, self.weighted = tuple(prefix), tuple(weighted)

    def _segment(self, count):
        if not self.length or count <= 0:
            return 0.0
        if self.rate == 0:
            return count / self.length
        return (-math.expm1(-self.rate * count)
                / -math.expm1(-self.rate) / self.length)

    def at(self, position):
        index = bisect_right(self.starts, position) - 1
        if index < 0 or not self.length:
            return 0.0, 0.0
        start, end = self.spans[index]
        clipped_end = min(position, end)
        raw = (self.prefix[index] + clipped_end - start) / self.length
        if self.rate == 0:
            return raw, raw
        if position >= end:
            return raw, self.weighted[index] * math.exp(-self.rate * (position - end))
        previous = (self.weighted[index - 1]
                    * math.exp(-self.rate * (position - self.spans[index - 1][1]))
                    if index else 0.0)
        return raw, previous + self._segment(position - start)


class PreparedSemantic:
    """Detached, indexed positional readouts with a bounded full-vector cache.

    Preparation retains interval geometry, never characters × objects. Painting
    can request only its source-associated objects using values_at; full hover
    details are calculated on demand and kept for at most cache_size positions.
    The default automatic view ignores legacy selection/comparison settings.
    """
    MAX_CACHE_SIZE = 64

    def __init__(self, snapshot, *, automatic=True, cache_size=16, cancelled=None):
        from collections import OrderedDict
        _check_cancelled(cancelled)
        if snapshot.mode not in ('semantic_triad_1', 'semantic_triad_2'):
            raise ValueError('PreparedSemantic requires a semantic graph mode')
        if type(cache_size) is not int or not 0 <= cache_size <= self.MAX_CACHE_SIZE:
            raise ValueError(f'cache_size must be an integer in [0, {self.MAX_CACHE_SIZE}]')
        if (snapshot.options.representations or snapshot.options.transformations
                or snapshot.semantic_evidence or snapshot.semantic_transformations):
            raise ValueError('Semantic Triad now uses semantic_footprints; point representations '
                             'and transformations cannot be mixed with character coverage')
        self.document_length = snapshot.document_length
        self.decay = snapshot.options.decay
        self.cache_size = cache_size
        self._cache = OrderedDict()
        footprints = snapshot.semantic_footprints if snapshot.options.parser_support else ()
        self._by_name = {item.object: item for item in footprints}
        self.object_names = tuple(self._by_name)
        self._scope = (self.object_names if automatic else
                       snapshot.options.comparison_objects or tuple(sorted(self._by_name)))
        if set(self._scope) - self._by_name.keys():
            raise ValueError('unknown comparison objects: ' + ', '.join(
                sorted(set(self._scope) - self._by_name.keys())))
        if not automatic and snapshot.options.selected_object is not None and (
                snapshot.options.selected_object not in self._by_name):
            raise ValueError('unknown selected object: ' + snapshot.options.selected_object)
        self._definitions, self._mentions, self._linked = {}, {}, {}
        self._indexes, self._intrinsic = {}, {}
        for name, item in self._by_name.items():
            _check_cancelled(cancelled)
            definitions, mentions = union_spans(item.definitions), union_spans(item.mentions)
            linked = union_spans(definitions + mentions)
            self._definitions[name], self._mentions[name], self._linked[name] = definitions, mentions, linked
            self._indexes[name] = tuple(_CoverageIndex(spans, self.document_length, self.decay,
                                                      cancelled=cancelled)
                                        for spans in (definitions, mentions, linked))
        for name, item in self._by_name.items():
            _check_cancelled(cancelled)
            children = union_spans(span for child in item.children
                                   for span in self._definitions.get(child, ()))
            norm = max(1, self.document_length)
            self._intrinsic[name] = (_size(self._definitions[name]) / norm,
                                    _size(subtract_spans(self._definitions[name], children)) / norm)
        _check_cancelled(cancelled)

    @property
    def cached_positions(self):
        """Oldest-to-newest cached source boundaries; bounded independently of N."""
        return tuple(self._cache)

    def _check_position(self, position):
        _position(position)
        if position > self.document_length:
            raise ValueError('point of use exceeds document length')

    def values_at(self, position, objects=None, *, cancelled=None):
        """Exact linked values for requested identities; no vector is cached."""
        _check_cancelled(cancelled)
        self._check_position(position)
        names = self.object_names if objects is None else tuple(dict.fromkeys(objects))
        result = []
        for name in names:
            _check_cancelled(cancelled)
            if name not in self._by_name:
                raise ValueError('unknown object: ' + str(name))
            value = (self._indexes[name][2].at(position)[1]
                     if position >= self._by_name[name].available_from else 0.0)
            result.append((name, value))
        return tuple(result)

    def details_at(self, position, *, cancelled=None):
        """All identities in declaration order, including unavailable zeroes."""
        _check_cancelled(cancelled)
        self._check_position(position)
        if position in self._cache:
            self._cache.move_to_end(position)
            return self._cache[position]
        direct, refs, linked = {}, {}, {}
        for name, item in self._by_name.items():
            _check_cancelled(cancelled)
            available = position >= item.available_from
            direct[name] = _clip(self._definitions[name], position) if available else ()
            refs[name] = _clip(self._mentions[name], position) if available else ()
            linked[name] = _clip(self._linked[name], position) if available else ()
        comparison, multiple = _support_layers((linked[name] for name in self._scope),
                                               cancelled=cancelled)
        norm, length = max(1, self.document_length), self.document_length
        comparison_size = _size(comparison)
        comparison_overlap = _intersection_counter(comparison)
        multiple_overlap = _intersection_counter(multiple)
        comparison_weight = comparison_size / norm
        comparison_adjusted = _coverage(comparison, position, length, self.decay)
        values = []
        scope = set(self._scope)
        for name, item in self._by_name.items():
            _check_cancelled(cancelled)
            inclusive, own = self._intrinsic[name]
            other_only = comparison_size - comparison_overlap(linked[name])
            shared = (multiple_overlap if name in scope else comparison_overlap)(linked[name])
            values.append(SemanticCoverage(
                name, inclusive, own, _size(direct[name])/norm, _size(refs[name])/norm,
                _size(linked[name])/norm,
                _coverage(direct[name], position, length, self.decay),
                _coverage(refs[name], position, length, self.decay),
                _coverage(linked[name], position, length, self.decay),
                comparison_weight, comparison_adjusted, shared/norm, other_only/norm,
                item.relationships))
        _check_cancelled(cancelled)
        result = tuple(values)
        if self.cache_size:
            self._cache[position] = result
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return result

    def maximum(self, *, cancelled=None):
        """Document-wide scale from every object's possible extrema.

        Coverage increases on support and decays between support spans. Thus
        support ends plus declaration availability cover every possible maximum,
        including values needed at unsampled intermediate hover positions.
        """
        _check_cancelled(cancelled)
        maximum = 0.0
        for name, item in self._by_name.items():
            _check_cancelled(cancelled)
            index = self._indexes[name][2]
            points = (item.available_from,) + tuple(end for _, end in self._linked[name]
                                                    if end >= item.available_from)
            for position in points:
                _check_cancelled(cancelled)
                maximum = max(maximum, index.at(position)[1])
        _check_cancelled(cancelled)
        return maximum


def calculate_semantic_positions(snapshot, *, cancelled=None, prepared=None, final_details=None):
    """Sparse source associations carrying one complete-document state."""
    prepared = prepared or PreparedSemantic(snapshot, cancelled=cancelled)
    if final_details is None:
        final_details = (calculate_inherited_details(snapshot, cancelled=cancelled)
                         if snapshot.semantic_elements else
                         prepared.details_at(snapshot.document_length, cancelled=cancelled))
    final_values = {item.object: item.adjusted_linked for item in final_details}
    by_position = {}
    order = {item.object: index for index, item in enumerate(final_details)}
    for event in snapshot.semantic_positions:
        _check_cancelled(cancelled)
        names = tuple(name for name in event.objects if name in order)
        if names:
            by_position.setdefault(event.position, set()).update(names)
    values = []
    for position, names in sorted(by_position.items()):
        _check_cancelled(cancelled)
        values.append((position, tuple((name, final_values[name]) for name in sorted(names, key=order.__getitem__))))
    # Preserve the legacy selected-object scalar scores without materializing
    # block × object vectors. They do not drive automatic map colors.
    selected = snapshot.options.selected_object
    if selected is None:
        selected = min(prepared.object_names, default=None)
    elif selected not in prepared.object_names:
        raise ValueError('unknown selected object: ' + selected)
    missing = set(snapshot.options.comparison_objects) - set(prepared.object_names)
    if missing:
        raise ValueError('unknown comparison objects: ' + ', '.join(sorted(missing)))
    scores = {}
    for block, position in sorted(snapshot.points):
        _check_cancelled(cancelled)
        value = (prepared.values_at(position, (selected,), cancelled=cancelled)[0][1]
                 if selected is not None else 0.0)
        scores[block] = HeatScore(value)
    return scores, tuple(values), max(final_values.values(), default=0.0)
