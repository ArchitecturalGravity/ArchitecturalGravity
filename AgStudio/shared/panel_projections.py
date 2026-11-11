"""Detached, Qt-free panel presentations derived in independent feature processes."""
from bisect import bisect_left
from dataclasses import dataclass

from .diagnostics import SEVERITY_ORDER
from .highlighting import highlight_tokens
from .recognition import SourceSpan


@dataclass(frozen=True, slots=True)
class OutlineRow:
    key: tuple
    parent_key: tuple
    fact_id: str
    label: str
    line: str
    tooltip: str
    role: str
    literal: bool
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class OutlineProjection:
    document_id: str
    rows: tuple[OutlineRow, ...]
    line_starts: tuple[int, ...]


def derive_outline(snapshot):
    # Imports remain Qt-free; one parsed snapshot feeds all presentation workers.
    from .analysis_snapshot import (AnalysisSnapshot, DocumentSnapshot, PackedAnalysisSnapshot,
                                    restore_analysis, restore_document, unpack_analysis)
    if isinstance(snapshot, PackedAnalysisSnapshot):
        snapshot = unpack_analysis(snapshot)
    if isinstance(snapshot, AnalysisSnapshot):
        analysis = restore_analysis(snapshot)
        document, tree = analysis.document, analysis.tree
    elif isinstance(snapshot, DocumentSnapshot):
        document = restore_document(snapshot)
        tree = getattr(document, 'syntax', None)
    else:
        analysis = snapshot if hasattr(snapshot, 'document') else None
        document = analysis.document if analysis is not None else snapshot
        tree = analysis.tree if analysis is not None else getattr(document, 'syntax', None)
    facts = document.structural_facts
    spans, hidden = {}, set()
    if tree is not None:
        ends = {node.id: node.span.end for node in tree.nodes}
        for node in reversed(tree.nodes):
            for owner in (node.parent, node.section):
                if owner is not None:
                    ends[owner] = max(ends[owner], ends[node.id])
        by_span = {node.span: node for node in tree.nodes}
        for fact in facts:
            node = by_span.get(fact.span)
            if node is not None:
                if node.kind == 'literal_close':
                    hidden.add(fact.id)
                else:
                    spans[fact.id] = SourceSpan(node.span.start, ends[node.id])
    facts = tuple(fact for fact in facts if fact.id not in hidden)
    by_id = {fact.id: fact for fact in facts}
    parents = {}
    for fact in facts:
        containment = document.relationship(fact.id, 'containment')
        ownership = document.relationship(fact.id, 'ownership')
        parents[fact.id] = (containment.target_fact_id if containment.status == 'supported'
                           else ownership.target_fact_id if ownership.status == 'supported' else None)
    children = {None: []}
    for fact in facts:
        parent = parents[fact.id]
        cursor, seen = parent, {fact.id}
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            cursor = parents.get(cursor)
        if parent not in by_id or cursor is not None:
            parent = None
        children.setdefault(parent, []).append(fact)
    tokens = sorted(highlight_tokens(document), key=lambda token: token.span.start)
    starts = [token.span.start for token in tokens]
    rows = []
    pending = [(None, ())]
    while pending:
        parent, path = pending.pop()
        occurrences = {}
        descendants = []
        for fact in children.get(parent, ()):
            text = ' '.join(fact.span.extract(document.source).split())
            literal = fact.kind == 'literal_open'
            label = 'Literal block' if literal else text[:100] + ('…' if len(text) > 100 else '')
            ordinal = occurrences.get(label, 0)
            occurrences[label] = ordinal + 1
            key = path + ((label, ordinal),)
            index = bisect_left(starts, fact.span.start)
            role = tokens[index].role if index < len(tokens) and tokens[index].span.start < fact.span.end else 'editor'
            tooltip = fact.span.extract(document.source).strip() + f"\n{fact.kind.replace('_', ' ')} · {fact.source_trust}"
            rows.append(OutlineRow(key, path, fact.id, label, str(fact.source_range.start.line),
                                   tooltip, role, literal, spans.get(fact.id, fact.span)))
            descendants.append((fact.id, key))
        pending.extend(reversed(descendants))
    line_starts = [0]
    for line in document.source.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))
    return OutlineProjection(document.document_id, tuple(rows), tuple(line_starts))


@dataclass(frozen=True, slots=True)
class FindingRow:
    key: tuple
    texts: tuple[str, ...]
    finding: object
    tooltip: str


@dataclass(frozen=True, slots=True)
class FindingsProjection:
    document_id: str
    rows: tuple[FindingRow, ...]
    spelling: tuple
    counts: tuple
    severities: tuple
    heading_tooltip: str


def derive_findings(analysis):
    document, diagnostics = analysis.document, analysis.diagnostics
    listed = sorted(diagnostics.findings,
                    key=lambda finding: (-SEVERITY_ORDER[finding.severity], finding.source_range.span.start,
                                         finding.source_range.span.end, finding.rule_id))
    rows, occurrences, severities = [], {}, {}
    counts = dict.fromkeys(('critical', 'error', 'warning', 'information'), 0)
    for finding in listed:
        # Source offsets are deliberately excluded: preceding text can shift a surviving finding.
        base = (finding.rule_id, finding.severity, finding.message,
                finding.source_range.span.extract(document.source))
        ordinal = occurrences.get(base, 0)
        occurrences[base] = ordinal + 1
        key = base + (ordinal,)
        texts = ('Info' if finding.severity == 'information' else finding.severity.capitalize(),
                 finding.rule_id, finding.message, str(finding.source_range.start.line), str(finding.source_range.start.column))
        tooltip = (f'{finding.rule_id}\n{finding.message}\n'
                   f'Contract: {finding.evidence.contract_version} · {finding.evidence.syntax_id}\n'
                   + '\n'.join(finding.evidence.premises) + '\n' + finding.evidence.limits)
        rows.append(FindingRow(key, texts, finding, tooltip))
        counts[finding.severity] += 1
        line = finding.source_range.start.line
        severities[line] = max(severities.get(line, 'information'), finding.severity, key=SEVERITY_ORDER.get)
    # One linear source-coordinate conversion, rather than encoding every growing prefix.
    offsets, offset, previous = [0], 0, ''
    for character in document.source:
        offset += 0 if character == '\n' and previous == '\r' else 2 if ord(character) > 0xffff else 1
        offsets.append(offset)
        previous = character
    spelling = tuple((offsets[f.source_range.span.start], offsets[f.source_range.span.end], f.message)
                     for f in diagnostics.findings if f.rule_id == 'AG-SPELLING')
    tooltip = ('Unsupported language version; no checks run' if diagnostics.status == 'unsupported_version'
               else f'{len(listed)} findings, {len(diagnostics.suppressed_conclusions)} '
                    'suppressed conclusions in supported checks; overall conformance unknown')
    return FindingsProjection(document.document_id, tuple(rows), spelling, tuple(counts.items()),
                              tuple(severities.items()), tooltip)
