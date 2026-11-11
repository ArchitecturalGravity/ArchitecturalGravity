"""Studio worker adapters for the standalone ArcGrav Language Engine.

Language snapshots and their trusted in-process transport live in the engine.
This compatibility namespace retains old imports and worker-pickle names; Qt,
process lifecycle, scheduling and presentation projections stay in Studio.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json

import AgStudio.arcgrav_language_engine as engine
from AgStudio.arcgrav_language_engine import AnalysisContext
from AgStudio.arcgrav_language_engine.core import LanguageCore
from AgStudio.arcgrav_language_engine.diagnostics import DiagnosticResult
from AgStudio.arcgrav_language_engine.snapshot import (
    AnalysisSnapshot, DocumentSnapshot, PackedAnalysisSnapshot,
    freeze_analysis, freeze_document, pack_analysis,
    restore_analysis, restore_document, unpack_analysis,
)


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    source: str
    version: str
    profile: str | None
    configuration_json: str


@dataclass(frozen=True, slots=True)
class AnalysisWorkResult:
    snapshot: AnalysisSnapshot
    findings_projection: object


@dataclass(frozen=True, slots=True)
class FindingsUpdate:
    """Only new Findings data; the unchanged parse stays in the UI model."""
    document_id: str
    diagnostics: DiagnosticResult
    findings_projection: object


def calculate_parse_snapshot(request: AnalysisRequest) -> AnalysisSnapshot:
    """One engine prepare per revision, independent of every Studio panel."""
    return engine.prepare(request.source, AnalysisContext(
        arcgrav_version=request.version, profile=request.profile,
        configuration=json.loads(request.configuration_json),
    ))


def calculate_packed_parse(request: AnalysisRequest) -> PackedAnalysisSnapshot:
    """Production parser entry point: serialize the shared parse only once."""
    return pack_analysis(calculate_parse_snapshot(request))


def calculate_analysis_snapshot(snapshot: AnalysisSnapshot | PackedAnalysisSnapshot) -> AnalysisWorkResult:
    """Evaluate engine diagnostics and derive Studio's Findings projection.

    No parsing or semantic resolution happens here. Independent Outline,
    Highlighting and Map consumers retain the same shared source snapshot.
    """
    from .panel_projections import derive_findings

    snapshot = unpack_analysis(snapshot)
    diagnostics = engine.diagnose(snapshot)
    complete = replace(snapshot, diagnostics=diagnostics)
    return AnalysisWorkResult(complete, derive_findings(restore_analysis(complete)))


def calculate_findings_update(snapshot: PackedAnalysisSnapshot | AnalysisSnapshot) -> FindingsUpdate:
    """Production Findings entry point, returning no unchanged parser objects."""
    result = calculate_analysis_snapshot(snapshot)
    return FindingsUpdate(result.snapshot.document.document_id,
                          result.snapshot.diagnostics, result.findings_projection)
