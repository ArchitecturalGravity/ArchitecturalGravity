"""Immutable, Qt-free transport for a single parsed source revision.

ParsedDocument deliberately protects its lookup indexes with mapping proxies,
which cannot cross a multiprocessing pipe. These snapshots retain the already
computed facts and canonical relationships as tuples. Restoration only rebuilds
lookup indexes; it never invokes recognition, parsing or semantic resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import pickle
from types import MappingProxyType

from .diagnostics import DiagnosticResult
from .document.model import DocumentFact, ParsedDocument
from .lint import Analysis
from .lint.model import CanonicalDocument
from .lint.semantics import Semantics
from .lint.syntax import SyntaxTree
from .recognition import RecognitionResult, SourceRecovery
from .version import SNAPSHOT_SCHEMA_VERSION


def _restore_snapshot_state(instance, state) -> None:
    """Reject missing fields and unsupported schemas; never upgrade old state."""
    layout = fields(instance)
    if not isinstance(state, (list, tuple)) or len(state) != len(layout):
        raise ValueError('unsupported snapshot pickle layout')
    version = state[next(i for i, field in enumerate(layout) if field.name == 'schema_version')]
    if type(version) is not int or version != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError('unsupported snapshot schema version')
    for field, value in zip(layout, state):
        object.__setattr__(instance, field.name, value)


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    recognition: RecognitionResult
    document_id: str
    line_starts: tuple[int, ...]
    structural_facts: tuple[DocumentFact, ...]
    occurrence_facts: tuple[DocumentFact, ...]
    recoveries: tuple[SourceRecovery, ...]
    facts_by_id: tuple[tuple[str, DocumentFact], ...]
    canonical: bool = False
    syntax: SyntaxTree | None = None
    semantics: Semantics | None = None
    relationships: tuple[tuple[tuple[str, str], str], ...] = ()
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __setstate__(self, state) -> None:
        _restore_snapshot_state(self, state)


@dataclass(frozen=True, slots=True)
class AnalysisSnapshot:
    document: DocumentSnapshot
    tree: SyntaxTree
    semantics: Semantics
    diagnostics: DiagnosticResult
    unresolved: tuple[str, ...]
    conformance: str = 'unknown'
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __setstate__(self, state) -> None:
        _restore_snapshot_state(self, state)


def _validate_document_schema(snapshot: DocumentSnapshot) -> None:
    if not isinstance(snapshot, DocumentSnapshot):
        raise TypeError('document snapshot requires DocumentSnapshot')
    if (type(snapshot.schema_version) is not int
            or snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION):
        raise ValueError('unsupported document snapshot schema version')


def _validate_analysis_schema(snapshot: AnalysisSnapshot) -> None:
    if not isinstance(snapshot, AnalysisSnapshot):
        raise TypeError('analysis snapshot requires AnalysisSnapshot')
    if (type(snapshot.schema_version) is not int
            or snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION):
        raise ValueError('unsupported analysis snapshot schema version')
    _validate_document_schema(snapshot.document)


@dataclass(frozen=True, slots=True)
class PackedAnalysisSnapshot:
    """A parse serialized once in its child, forwarded without object walking."""
    data: bytes


def pack_analysis(snapshot: AnalysisSnapshot) -> PackedAnalysisSnapshot:
    if not isinstance(snapshot, AnalysisSnapshot):
        raise TypeError('analysis packing requires AnalysisSnapshot')
    _validate_analysis_schema(snapshot)
    return PackedAnalysisSnapshot(pickle.dumps(snapshot, protocol=pickle.HIGHEST_PROTOCOL))


def unpack_analysis(snapshot: PackedAnalysisSnapshot | AnalysisSnapshot) -> AnalysisSnapshot:
    """Unpack only internally created worker data, never arbitrary file input."""
    if isinstance(snapshot, PackedAnalysisSnapshot):
        snapshot = pickle.loads(snapshot.data)
    if not isinstance(snapshot, AnalysisSnapshot):
        raise TypeError('analysis unpacking requires a packed or plain AnalysisSnapshot')
    _validate_analysis_schema(snapshot)
    return snapshot


def freeze_document(document: ParsedDocument) -> DocumentSnapshot:
    """Detach mapping indexes without repeating any language derivation."""
    if not isinstance(document, ParsedDocument):
        raise TypeError('document snapshot requires ParsedDocument')
    canonical = isinstance(document, CanonicalDocument)
    return DocumentSnapshot(
        document.recognition, document.document_id, document.line_starts,
        document.structural_facts, document.occurrence_facts,
        document.recoveries, tuple(document._facts_by_id.items()), canonical,
        document.syntax if canonical else None,
        document.semantics if canonical else None,
        tuple(document._relationships.items()) if canonical else (),
    )


def restore_document(snapshot: DocumentSnapshot) -> ParsedDocument:
    """Restore immutable lookup indexes directly, with no parser work."""
    if not isinstance(snapshot, DocumentSnapshot):
        raise TypeError('document restoration requires DocumentSnapshot')
    _validate_document_schema(snapshot)
    cls = CanonicalDocument if snapshot.canonical else ParsedDocument
    document = object.__new__(cls)
    for name in ('recognition', 'document_id', 'line_starts',
                 'structural_facts', 'occurrence_facts', 'recoveries'):
        object.__setattr__(document, name, getattr(snapshot, name))
    object.__setattr__(document, '_facts_by_id',
                       MappingProxyType(dict(snapshot.facts_by_id)))
    if snapshot.canonical:
        object.__setattr__(document, 'syntax', snapshot.syntax)
        object.__setattr__(document, 'semantics', snapshot.semantics)
        object.__setattr__(document, '_relationships',
                           MappingProxyType(dict(snapshot.relationships)))
    return document


def freeze_analysis(analysis: Analysis) -> AnalysisSnapshot:
    """Freeze canonical analysis for transport and deterministic reevaluation."""
    if not isinstance(analysis, Analysis):
        raise TypeError('analysis snapshot requires Analysis')
    return AnalysisSnapshot(
        freeze_document(analysis.document), analysis.tree, analysis.semantics,
        analysis.diagnostics, analysis.unresolved, analysis.conformance,
    )


def restore_analysis(snapshot: AnalysisSnapshot) -> Analysis:
    if not isinstance(snapshot, AnalysisSnapshot):
        raise TypeError('analysis restoration requires AnalysisSnapshot')
    _validate_analysis_schema(snapshot)
    return Analysis(
        restore_document(snapshot.document), snapshot.tree, snapshot.semantics,
        snapshot.diagnostics, snapshot.unresolved, snapshot.conformance,
    )


# Prepared and completed states share one explicitly versioned transport
# layout. prepare() returns pending diagnostics; diagnose() returns findings
# without mutating that snapshot.
PreparedSnapshot = AnalysisSnapshot

__all__ = [
    'DocumentSnapshot', 'AnalysisSnapshot', 'PreparedSnapshot',
    'PackedAnalysisSnapshot', 'freeze_document', 'restore_document',
    'freeze_analysis', 'restore_analysis', 'pack_analysis', 'unpack_analysis',
]
