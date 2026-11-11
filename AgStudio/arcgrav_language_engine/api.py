"""Prepare source once; evaluate all diagnostics through one local rule runner.

Snapshots retain canonical facts, syntax and semantics. diagnose() restores
lookup indexes only; it never repeats recognition, parsing or resolution.
"""
from __future__ import annotations

from dataclasses import replace

from .context import AnalysisContext
from .version import LANGUAGE_CONTRACT_VERSION
from .core import LanguageCore
from .diagnostics import DiagnosticResult
from .lint import Analysis
from .lint.model import CanonicalDocument
from .lint.semantics import resolve
from .lint.syntax import parse
from .snapshot import (
    AnalysisSnapshot, DocumentSnapshot, _validate_analysis_schema,
    freeze_document, restore_analysis, restore_document,
)


def prepare(source: str, context: AnalysisContext) -> AnalysisSnapshot:
    """Parse/resolve source using explicit context, without running checks.

    The result is an immutable, pickle-compatible derived snapshot, not a new
    source authority or a safe serialization format for untrusted data.
    """
    if not isinstance(context, AnalysisContext):
        raise TypeError('analysis requires an explicit AnalysisContext')
    session = LanguageCore.open_source(
        source, arcgrav_version=context.arcgrav_version,
        profile=context.profile, configuration=context.configuration,
    )
    document = LanguageCore.parse_document(session)
    tree = parse(document)
    semantics = resolve(document, tree)
    canonical = CanonicalDocument(document, tree, semantics)
    pending = DiagnosticResult(document.document_id, session.arcgrav_version, (),
                               'pending')
    return AnalysisSnapshot(
        freeze_document(canonical), tree, semantics, pending,
        tuple(sorted({condition for fact in canonical.facts() for condition in fact.limitations}
                     | {recovery.kind for recovery in canonical.recoveries}
                     | ({'unsupported_version'} if session.arcgrav_version != LANGUAGE_CONTRACT_VERSION else set()))),
    )


def _validate_snapshot(snapshot: AnalysisSnapshot) -> DocumentSnapshot:
    if not isinstance(snapshot, AnalysisSnapshot):
        raise TypeError('diagnostics require an AnalysisSnapshot')
    _validate_analysis_schema(snapshot)
    document = snapshot.document
    if not isinstance(document, DocumentSnapshot) or not document.canonical:
        raise ValueError('diagnostics require a canonical document from prepare()')
    if (document.syntax != snapshot.tree or document.semantics != snapshot.semantics
            or snapshot.diagnostics.document_id != document.document_id
            or snapshot.diagnostics.arcgrav_version != document.recognition.session.arcgrav_version):
        raise ValueError('analysis snapshot document and context must agree')
    return document


def diagnose(snapshot: AnalysisSnapshot) -> DiagnosticResult:
    """Run checks over prepare()'s canonical model; never reparse.

    The supplied snapshot is unchanged. Dictionary loading remains optional and
    lazy; disabled spelling checks do not load the spelling dictionary.
    """
    document = _validate_snapshot(snapshot)
    from .lint.findings import assemble_diagnostics

    return assemble_diagnostics(restore_document(document), snapshot.tree, snapshot.semantics)


def analyze(source: str, context: AnalysisContext) -> Analysis:
    """Compose preparation and diagnostics into the established Analysis view."""
    prepared = prepare(source, context)
    return restore_analysis(replace(prepared, diagnostics=diagnose(prepared)))


__all__ = ['prepare', 'diagnose', 'analyze']
